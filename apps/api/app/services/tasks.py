from __future__ import annotations

from infer.spec import (
    BATCH_REFERENCE_DISCLAIMER,
    BUILTIN_DISPLAY_NAMES,
    CAM_DISCLAIMER,
    COMPARE_BASELINE_LIMIT,
    DEMO_CATALOG_KIND,
    ERROR_LEGEND,
    EVAL_BASELINE_LIMIT,
    NEU_LEGEND,
    OFFICIAL_SPLIT_DISCLAIMER,
    OFFICIAL_SPLIT_SCOPE,
)
from infer.task_io import metrics_response
from sqlalchemy.orm import Session, selectinload

from app.cache import invalidate_after_write, rq_connection
from app.config import Settings, get_settings
from app.db.models import (
    Dataset,
    DatasetVersion,
    Model,
    ModelVersion,
    PreprocessSpecRow,
    Sample,
    Task,
    TaskModel,
    TaskSample,
    User,
)
from app.errors import AppError
from app.services.task_artifacts import GT_NOTICE, TaskArtifacts
from app.services.models import assert_model_role_access
from app.services.dispatch import enqueue, apply_task_delivery
from app.services.input_freeze import lock_version, freeze_inputs, current_samples
from app.services.submission import request_id, lock_user, existing_task
from app.util_time import new_id, utcnow

TASK_TYPE_LABELS = {
    "compare": "快速对比",
    "eval": "正式评测",
    "demo": "公开演示",
    "classification": "钢铁缺陷分类",
}


def _can_view_task(task: Task, user: User) -> bool:
    if task.creator_id == user.id:
        return True
    if user.role != "advisor":
        return False
    # Logged-in demo access keeps its existing creator/advisor policy.
    if task.type == "demo":
        return True
    return task.type in {"compare", "eval", "classification"} and task.submitted_to_advisor_at is not None


def get_visible_task(db: Session, task_id: str, user: User) -> Task:
    task = (
        db.query(Task)
        .options(
            selectinload(Task.models),
            selectinload(Task.samples),
            selectinload(Task.artifacts),
            selectinload(Task.metric_set),
        )
        .filter(Task.id == task_id)
        .one_or_none()
    )
    if task is None or not _can_view_task(task, user):
        raise AppError("任务不存在", code="NOT_FOUND", stage="auth", status_code=404)
    return task


def _assert_baseline_count(baseline_version_ids: list[str], *, max_baselines: int) -> None:
    if not 1 <= len(baseline_version_ids) <= max_baselines:
        raise AppError(
            f"请选择 1–{max_baselines} 个内置 baseline",
            code="BASELINE_COUNT",
            stage="protocol",
            status_code=400,
        )
    if len(set(baseline_version_ids)) != len(baseline_version_ids):
        raise AppError("baseline 不能重复", code="DUP_BASELINE", stage="protocol", status_code=400)


def _resolve_runnable_models(
    db: Session,
    user: User,
    *,
    baseline_version_ids: list[str],
    student_version_id: str | None,
    version: DatasetVersion,
    max_baselines: int = COMPARE_BASELINE_LIMIT,
) -> tuple[list[ModelVersion], ModelVersion | None]:
    if version.kind == "classification_batch":
        raise AppError("分类批次不能进入分割任务", code="TASK_KIND_MISMATCH", stage="protocol", status_code=400)
    _assert_baseline_count(baseline_version_ids, max_baselines=max_baselines)

    baselines = []
    for vid in baseline_version_ids:
        mv = db.get(ModelVersion, vid)
        if mv is None:
            raise AppError("baseline 不存在", code="MODEL_NOT_FOUND", stage="protocol", status_code=404)
        assert_model_role_access(user, db.get(Model, mv.model_id), mv, "baseline")
        from app.services.models import is_classification_version
        if is_classification_version(db, mv):
            raise AppError("分类模型不能进入分割任务", code="TASK_KIND_MISMATCH", stage="protocol", status_code=400)
        if mv.status != "runnable":
            raise AppError(
                f"模型当前不能加入任务（状态 {mv.status}）",
                code="MODEL_NOT_RUNNABLE",
                stage="protocol",
                status_code=400,
            )
        if mv.requires_cuda:
            raise AppError(
                "当前环境为 CPU，CUDA-only 模型不可运行",
                code="CUDA_REQUIRED",
                stage="resource",
                status_code=400,
            )
        baselines.append(mv)

    student = None
    if student_version_id:
        student = db.get(ModelVersion, student_version_id)
        if student is None or student.status != "runnable":
            raise AppError("学生模型尚未通过检查，不能加入任务", code="STUDENT_NOT_RUNNABLE", stage="protocol", status_code=400)
        assert_model_role_access(user, db.get(Model, student.model_id), student, "student_under_test")
        if student.requires_cuda:
            raise AppError(
                "当前环境为 CPU，CUDA-only 模型不可运行",
                code="CUDA_REQUIRED",
                stage="resource",
                status_code=400,
            )

    check_list = list(baselines) + ([student] if student else [])
    proto = {(m.num_classes, m.in_channels, m.input_h, m.input_w, m.preprocess_id) for m in check_list}
    if len(proto) != 1:
        raise AppError(
            "类别数 / 通道 / 输入尺寸 / 预处理协议不一致，已阻止入队",
            code="PROTOCOL_MISMATCH",
            stage="protocol",
            status_code=400,
        )
    if version.preprocess_id != baselines[0].preprocess_id:
        raise AppError(
            "数据批次与模型预处理协议不一致",
            code="PREPROCESS_MISMATCH",
            stage="protocol",
            status_code=400,
        )
    return baselines, student


def _enqueue_task(settings: Settings, job_name: str, task_id: str, timeout: int) -> None:
    return enqueue(settings, job_name, task_id, timeout, job_id=f"task-{task_id}")


def _attach_models_and_samples(
    db: Session,
    task: Task,
    baselines: list[ModelVersion],
    student: ModelVersion | None,
    samples: list[Sample],
) -> None:
    for index, mv in enumerate(baselines):
        db.add(
            TaskModel(
                id=new_id(),
                task_id=task.id,
                model_version_id=mv.id,
                role="baseline",
                sort_order=index,
                status="queued",
            )
        )
    if student:
        db.add(
            TaskModel(
                id=new_id(),
                task_id=task.id,
                model_version_id=student.id,
                role="student_under_test",
                sort_order=len(baselines),
                status="queued",
            )
        )
    for index, sample in enumerate(samples):
        db.add(TaskSample(id=new_id(), task_id=task.id, sample_id=sample.id, sort_order=index))


def create_compare_task(
    db: Session,
    user: User,
    *,
    batch_id: str,
    baseline_version_ids: list[str],
    student_version_id: str | None,
    settings: Settings | None = None,
    idempotency_key: str | None = None,
) -> Task:
    settings = settings or get_settings()
    lock_user(db, user)
    version = lock_version(db, batch_id)
    if version is None:
        raise AppError("上传批次不存在", code="BATCH_NOT_FOUND", stage="file", status_code=404)
    dataset = db.get(Dataset, version.dataset_id)
    if dataset is None:
        raise AppError("数据集不存在", code="NOT_FOUND", stage="file", status_code=404)
    if dataset.visibility == "private" and dataset.owner_id != user.id and user.role != "advisor":
        raise AppError("无权使用该批次", code="FORBIDDEN", stage="auth", status_code=403)
    if version.kind == DEMO_CATALOG_KIND:
        raise AppError(
            "公开演示请使用 /api/demo/tasks，不能走快速对比",
            code="DEMO_USE_DEMO_API",
            stage="protocol",
            status_code=400,
        )

    task_id = request_id("compare", user.id, idempotency_key)
    previous = existing_task(db, task_id, "compare", version.id, baseline_version_ids, student_version_id)
    if previous is not None:
        return previous

    samples = current_samples(db, version.id)
    if not samples:
        raise AppError("该批次没有图片", code="NO_SAMPLES", stage="file", status_code=400)
    if len(samples) > settings.max_upload_images and version.kind == "upload_batch":
        raise AppError("超过快速对比 50 张上限", code="TOO_MANY_IMAGES", stage="protocol", status_code=400)

    has_gt = all(s.mask_uri for s in samples)
    if not all(s.mask_uri for s in samples):
        has_gt = False

    baselines, student = _resolve_runnable_models(
        db,
        user,
        baseline_version_ids=baseline_version_ids,
        student_version_id=student_version_id,
        version=version,
    )
    task = Task(
        id=task_id,
        type="compare",
        creator_id=user.id,
        dataset_version_id=version.id,
        preprocess_id=baselines[0].preprocess_id,
        status="queued",
        has_gt=has_gt,
        error_summary="QUEUE_PENDING: 已保存，尚未确认入队",
        updated_at=utcnow(),
    )
    try:
        db.add(task)
        db.flush()
        _attach_models_and_samples(db, task, baselines, student, samples)
        freeze_inputs(db, task, samples, settings)
        db.commit()
    except Exception:
        # Callers such as the assistant may catch AppError and commit their own
        # turn. Never leave a partially created task in that transaction.
        db.rollback()
        raise
    invalidate_after_write(task.id, user.id)
    delivery = _enqueue_task(settings, "apps.worker.jobs.run_compare", task.id, settings.compare_job_timeout_sec)
    apply_task_delivery(db, task, delivery)
    return task


def assert_eval_version(version: DatasetVersion) -> None:
    if version.kind != "preset" or not version.is_fixed_test:
        raise AppError(
            "正式评测仅开放固定测试集（当前为预置 NEU-20）",
            code="EVAL_DATASET_FORBIDDEN",
            stage="protocol",
            status_code=400,
        )


def assert_eval_samples(samples: list[Sample]) -> None:
    if not samples:
        raise AppError("该数据版本没有图片", code="NO_SAMPLES", stage="file", status_code=400)
    if not all(s.mask_uri for s in samples):
        raise AppError("无掩码数据不能进入正式评测", code="EVAL_NO_GT", stage="protocol", status_code=400)


def create_eval_task(
    db: Session,
    user: User,
    *,
    dataset_version_id: str,
    baseline_version_ids: list[str],
    student_version_id: str | None,
    settings: Settings | None = None,
    idempotency_key: str | None = None,
) -> Task:
    settings = settings or get_settings()
    lock_user(db, user)
    version = lock_version(db, dataset_version_id)
    if version is None:
        raise AppError("数据版本不存在", code="BATCH_NOT_FOUND", stage="file", status_code=404)
    dataset = db.get(Dataset, version.dataset_id)
    if dataset is None:
        raise AppError("数据集不存在", code="NOT_FOUND", stage="file", status_code=404)
    if dataset.visibility == "private" and dataset.owner_id != user.id and user.role != "advisor":
        raise AppError("无权使用该数据版本", code="FORBIDDEN", stage="auth", status_code=403)
    assert_eval_version(version)

    task_id = request_id("eval", user.id, idempotency_key)
    previous = existing_task(db, task_id, "eval", version.id, baseline_version_ids, student_version_id)
    if previous is not None:
        return previous

    samples = current_samples(db, version.id)
    assert_eval_samples(samples)

    baselines, student = _resolve_runnable_models(
        db,
        user,
        baseline_version_ids=baseline_version_ids,
        student_version_id=student_version_id,
        version=version,
        max_baselines=EVAL_BASELINE_LIMIT,
    )
    task = Task(
        id=task_id,
        type="eval",
        creator_id=user.id,
        dataset_version_id=version.id,
        preprocess_id=baselines[0].preprocess_id,
        status="queued",
        has_gt=True,
        error_summary="QUEUE_PENDING: 已保存，尚未确认入队",
        updated_at=utcnow(),
    )
    try:
        db.add(task)
        db.flush()
        _attach_models_and_samples(db, task, baselines, student, samples)
        freeze_inputs(db, task, samples, settings)
        db.commit()
    except Exception:
        # Callers such as the assistant may catch AppError and commit their own
        # turn. Never leave a partially created task in that transaction.
        db.rollback()
        raise
    invalidate_after_write(task.id, user.id)
    delivery = _enqueue_task(settings, "apps.worker.jobs.run_eval", task.id, settings.eval_job_timeout_sec)
    apply_task_delivery(db, task, delivery)
    return task


def serialize_task(db: Session, task: Task) -> dict:
    if task.type == "classification":
        from app.services.classification import serialize_classification_task
        return serialize_classification_task(db, task)
    policy = TaskArtifacts(db, task, get_settings())
    bundle_state = policy.bundle_state()
    preprocess = db.get(PreprocessSpecRow, task.preprocess_id)
    model_rows = (
        db.query(TaskModel, ModelVersion)
        .join(ModelVersion, ModelVersion.id == TaskModel.model_version_id)
        .filter(TaskModel.task_id == task.id)
        .order_by(TaskModel.sort_order.asc())
        .all()
    )
    from app.db.models import Model

    models_out = []
    for tm, mv in model_rows:
        model = db.get(Model, mv.model_id)
        models_out.append(
            {
                "task_model_id": tm.id,
                "model_version_id": mv.id,
                "role": tm.role,
                "slug": mv.slug,
                "name": model.name if model else BUILTIN_DISPLAY_NAMES.get(mv.slug, mv.slug),
                "status": tm.status,
                "fail_stage": tm.fail_stage,
                "fail_message": tm.fail_message,
            }
        )
    sample_ids = [row.sample_id for row in sorted(task.samples, key=lambda r: r.sort_order)]
    samples = []
    if sample_ids:
        by_id = {s.id: s for s in db.query(Sample).filter(Sample.id.in_(sample_ids)).all()}
        for sid in sample_ids:
            sample = by_id[sid]
            samples.append({"id": sample.id, "sample_key": sample.sample_key, "width": sample.width, "height": sample.height})

    artifacts = [
        {
            "id": a.id,
            "sample_key": a.sample_key,
            "model_version_id": a.model_version_id,
            "kind": a.kind,
            "url": f"/api/tasks/{task.id}/file/{a.rel_path}",
        }
        for a in policy.downloadable(bundle_ready=bundle_state["bundle_ready"])
    ]
    preview_keys = sorted(
        {a["sample_key"] for a in artifacts if a["kind"] == "origin" and a["sample_key"]}
    )
    version = db.get(DatasetVersion, task.dataset_version_id)
    dataset = db.get(Dataset, version.dataset_id) if version else None
    return {
        "id": task.id,
        "type": task.type,
        "type_label": TASK_TYPE_LABELS.get(task.type, task.type),
        "status": task.status,
        "has_gt": task.has_gt,
        "error_summary": task.error_summary,
        "created_at": task.created_at.isoformat() + "Z",
        "dataset": {
            "id": dataset.id if dataset else None,
            "name": dataset.name if dataset else None,
            "version_id": version.id if version else task.dataset_version_id,
            "is_fixed_test": bool(version.is_fixed_test) if version else False,
        },
        "preprocess": {
            "id": preprocess.id if preprocess else task.preprocess_id,
            "name": preprocess.name if preprocess else None,
            "height": preprocess.height if preprocess else None,
            "width": preprocess.width if preprocess else None,
            "apply_clahe": preprocess.apply_clahe if preprocess else None,
            "sp_threshold": preprocess.sp_threshold if preprocess else None,
        },
        "models": models_out,
        "samples": samples,
        "n": len(samples),
        "preview_sample_keys": preview_keys,
        "artifacts": artifacts,
        "legend": NEU_LEGEND,
        "error_legend": ERROR_LEGEND if task.has_gt else [],
        "cam_disclaimer": CAM_DISCLAIMER,
        **bundle_state,
        "artifact_notice": GT_NOTICE if policy.gt_sensitive and not policy.allow_gt else None,
    }


def serialize_metrics(task: Task) -> dict:
    if task.type == "classification":
        from app.services.classification import serialize_classification_metrics
        return serialize_classification_metrics(task)
    if task.type == "demo":
        raise AppError("公开演示不提供精度", code="DEMO_NO_METRICS", stage="protocol", status_code=404)
    if not task.has_gt:
        return metrics_response(has_gt=False)
    if task.metric_set is None:
        return metrics_response(has_gt=True, payload=None)
    payload = dict(task.metric_set.payload_json)
    payload["scope"] = task.metric_set.scope
    payload["n"] = task.metric_set.n
    if task.metric_set.scope == OFFICIAL_SPLIT_SCOPE or task.type == "eval":
        payload["disclaimer"] = OFFICIAL_SPLIT_DISCLAIMER
    else:
        payload["disclaimer"] = BATCH_REFERENCE_DISCLAIMER
    return metrics_response(has_gt=True, payload=payload)
