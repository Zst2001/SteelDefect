from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from app.cache import invalidate_after_write
from app.config import Settings, get_settings
from app.db.models import (
    DatasetVersion,
    Model,
    ModelVersion,
    PreprocessSpecRow,
    Sample,
    Task,
    TaskModel,
    TaskSample,
)
from app.errors import AppError
from app.services.demo_identity import DemoIdentity
from app.services.demo_quota import raise_demo_quota, release_guest_quota, reserve_guest_quota
from app.services.tasks import TASK_TYPE_LABELS, _attach_models_and_samples, _enqueue_task
from app.util_time import new_id, utcnow
from infer.spec import CAM_DISCLAIMER, DEMO_CATALOG_KIND, DEMO_DISCLAIMER, DEMO_MODEL_SLUGS, NEU_LEGEND

GT_LEAK_KEYS = ("mask_uri", "mask", "has_mask", "has_gt", "origin_uri", "gt")
METRIC_LEAK_TOKENS = ("metrics", "miou", "mdice", "acc", "metric_set", "available")
GT_FIELD_TOKENS = ("mask_uri", "has_mask", "has_gt", "metrics", "miou", "mdice", "acc")
DEMO_ARTIFACT_KINDS = {"origin", "pred_color", "overlay", "boundary", "cam", "montage", "bundle", "log"}


def get_demo_version(db: Session) -> DatasetVersion:
    version = (
        db.query(DatasetVersion)
        .filter(DatasetVersion.kind == DEMO_CATALOG_KIND)
        .order_by(DatasetVersion.created_at.asc())
        .one_or_none()
    )
    if version is None:
        raise AppError("公开演示样例尚未发布", code="DEMO_CATALOG_MISSING", stage="file", status_code=503)
    return version


def serialize_demo_sample(sample: Sample) -> dict:
    payload = {
        "sample_key": sample.sample_key,
        "width": sample.width,
        "height": sample.height,
        "preview_url": f"/api/demo/samples/{sample.sample_key}/preview",
    }
    for key in GT_LEAK_KEYS:
        payload.pop(key, None)
    return payload


def list_demo_catalog(db: Session) -> dict:
    version = get_demo_version(db)
    samples = (
        db.query(Sample)
        .filter(Sample.version_id == version.id)
        .order_by(Sample.sample_key.asc())
        .all()
    )
    items = [serialize_demo_sample(row) for row in samples]
    return {
        "disclaimer": DEMO_DISCLAIMER,
        "n": len(items),
        "items": items,
        "legend": NEU_LEGEND,
    }


def get_demo_sample(db: Session, sample_key: str) -> Sample:
    version = get_demo_version(db)
    sample = (
        db.query(Sample)
        .filter(Sample.version_id == version.id, Sample.sample_key == sample_key)
        .one_or_none()
    )
    if sample is None:
        raise AppError("预备样例不存在", code="SAMPLE_NOT_FOUND", stage="file", status_code=404)
    return sample


def is_demo_model(model: Model, version: ModelVersion) -> bool:
    return (
        model.source == "builtin"
        and version.slug in DEMO_MODEL_SLUGS
        and version.status == "runnable"
        and not version.requires_cuda
    )


def serialize_demo_model(model: Model, version: ModelVersion) -> dict:
    return {
        "id": version.id,
        "name": model.name,
        "slug": version.slug,
        "source": "builtin",
        "num_classes": version.num_classes,
        "input_size": [version.input_h, version.input_w],
        "requires_cuda": False,
        "runnable_here": True,
    }


def list_demo_models(db: Session) -> dict:
    rows = (
        db.query(ModelVersion)
        .options(selectinload(ModelVersion.model))
        .all()
    )
    items = []
    for version in rows:
        model = version.model
        if model is None or not is_demo_model(model, version):
            continue
        items.append(serialize_demo_model(model, version))
    items.sort(key=lambda row: DEMO_MODEL_SLUGS.index(row["slug"]) if row["slug"] in DEMO_MODEL_SLUGS else 99)
    return {"disclaimer": DEMO_DISCLAIMER, "items": items}


def _banned_field_names(payload: object, banned: set[str]) -> bool:
    """True when a leak token appears as a JSON key, not as a UUID/status substring."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in banned:
                return True
            if _banned_field_names(value, banned):
                return True
        return False
    if isinstance(payload, (list, tuple)):
        return any(_banned_field_names(item, banned) for item in payload)
    return False


def catalog_has_no_gt_fields(payload: dict) -> bool:
    return not _banned_field_names(payload, set(GT_FIELD_TOKENS))


def payload_has_no_metric_fields(payload: dict) -> bool:
    return not _banned_field_names(payload, set(METRIC_LEAK_TOKENS))


def _resolve_demo_models(db: Session, baseline_version_ids: list[str], version: DatasetVersion) -> list[ModelVersion]:
    if not 1 <= len(baseline_version_ids) <= 3:
        raise AppError("请选择 1–3 个内置模型", code="BASELINE_COUNT", stage="protocol", status_code=400)
    if len(set(baseline_version_ids)) != len(baseline_version_ids):
        raise AppError("模型不能重复", code="DUP_BASELINE", stage="protocol", status_code=400)
    baselines: list[ModelVersion] = []
    for vid in baseline_version_ids:
        mv = db.get(ModelVersion, vid)
        if mv is None:
            raise AppError("模型不存在", code="MODEL_NOT_FOUND", stage="protocol", status_code=404)
        model = db.get(Model, mv.model_id)
        if model is None or not is_demo_model(model, mv):
            raise AppError(
                "公开演示仅支持内置 UNet / DeepLabV3+ / UNet++",
                code="DEMO_MODEL_FORBIDDEN",
                stage="protocol",
                status_code=400,
            )
        baselines.append(mv)
    proto = {(m.num_classes, m.in_channels, m.input_h, m.input_w, m.preprocess_id) for m in baselines}
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
    return baselines


def _resolve_demo_samples(db: Session, version: DatasetVersion, sample_keys: list[str]) -> list[Sample]:
    keys = [key.strip() for key in sample_keys if str(key).strip()]
    if not 1 <= len(keys) <= 5:
        raise AppError("请点选 1–5 张预备样例", code="SAMPLE_COUNT", stage="protocol", status_code=400)
    if len(set(keys)) != len(keys):
        raise AppError("预备样例不能重复", code="DUP_SAMPLE", stage="protocol", status_code=400)
    rows = (
        db.query(Sample)
        .filter(Sample.version_id == version.id, Sample.sample_key.in_(keys))
        .all()
    )
    by_key = {row.sample_key: row for row in rows}
    missing = [key for key in keys if key not in by_key]
    if missing:
        raise AppError("预备样例不存在", code="SAMPLE_NOT_FOUND", stage="file", status_code=400)
    ordered = [by_key[key] for key in keys]
    if any(row.mask_uri for row in ordered):
        raise AppError("演示样例配置错误", code="DEMO_GT_FORBIDDEN", stage="protocol", status_code=500)
    return ordered


def create_demo_task(
    db: Session,
    identity: DemoIdentity,
    *,
    sample_keys: list[str],
    baseline_version_ids: list[str],
    settings: Settings | None = None,
) -> Task:
    settings = settings or get_settings()
    version = get_demo_version(db)
    samples = _resolve_demo_samples(db, version, sample_keys)
    baselines = _resolve_demo_models(db, baseline_version_ids, version)
    user = identity.user
    task_id = new_id()
    reserved = False
    if user is None:
        reserved = reserve_guest_quota(identity, task_id, settings)
        if not reserved:
            raise_demo_quota()
    try:
        task = Task(
            id=task_id,
            type="demo",
            creator_id=user.id if user is not None else None,
            guest_sid=None if user is not None else identity.sid,
            guest_ip_hash=None if user is not None else identity.ip_hash,
            dataset_version_id=version.id,
            preprocess_id=baselines[0].preprocess_id,
            status="queued",
            has_gt=False,
            error_summary=None,
            updated_at=utcnow(),
        )
        db.add(task)
        db.flush()
        _attach_models_and_samples(db, task, baselines, None, samples)
        db.commit()
    except Exception:
        if reserved:
            release_guest_quota(identity, task_id)
        raise
    invalidate_after_write(task.id, user.id if user is not None else None)
    _enqueue_task(settings, "apps.worker.jobs.run_demo", task.id, settings.demo_job_timeout_sec)
    return task


def _load_demo_task(db: Session, task_id: str) -> Task | None:
    return (
        db.query(Task)
        .options(
            selectinload(Task.models),
            selectinload(Task.samples),
            selectinload(Task.artifacts),
            selectinload(Task.metric_set),
        )
        .filter(Task.id == task_id, Task.type == "demo")
        .one_or_none()
    )


def can_view_demo_task(task: Task, identity: DemoIdentity) -> bool:
    if task.type != "demo":
        return False
    user = identity.user
    if user is not None:
        if user.role == "advisor":
            return True
        if task.creator_id and task.creator_id == user.id:
            return True
        return False
    return bool(task.guest_sid) and task.guest_sid == identity.sid


def get_visible_demo_task(db: Session, task_id: str, identity: DemoIdentity) -> Task:
    task = _load_demo_task(db, task_id)
    if task is None or not can_view_demo_task(task, identity):
        raise AppError("任务不存在", code="NOT_FOUND", stage="auth", status_code=404)
    return task


def serialize_demo_task(db: Session, task: Task) -> dict:
    if task.type != "demo":
        raise AppError("不是公开演示任务", code="NOT_FOUND", stage="auth", status_code=404)
    preprocess = db.get(PreprocessSpecRow, task.preprocess_id)
    model_rows = (
        db.query(TaskModel, ModelVersion)
        .join(ModelVersion, ModelVersion.id == TaskModel.model_version_id)
        .filter(TaskModel.task_id == task.id)
        .order_by(TaskModel.sort_order.asc())
        .all()
    )
    models_out = []
    for tm, mv in model_rows:
        model = db.get(Model, mv.model_id)
        models_out.append(
            {
                "task_model_id": tm.id,
                "model_version_id": mv.id,
                "role": "baseline",
                "slug": mv.slug,
                "name": model.name if model else mv.slug,
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
            samples.append(
                {
                    "id": sample.id,
                    "sample_key": sample.sample_key,
                    "width": sample.width,
                    "height": sample.height,
                    "preview_url": f"/api/demo/samples/{sample.sample_key}/preview",
                }
            )
    artifacts = []
    for artifact in task.artifacts:
        if artifact.kind not in DEMO_ARTIFACT_KINDS:
            continue
        artifacts.append(
            {
                "id": artifact.id,
                "sample_key": artifact.sample_key,
                "model_version_id": artifact.model_version_id,
                "kind": artifact.kind,
                "url": f"/api/demo/tasks/{task.id}/file/{artifact.rel_path}",
            }
        )
    preview_keys = sorted(
        {row["sample_key"] for row in artifacts if row["kind"] == "montage" and row["sample_key"]}
    )
    payload = {
        "id": task.id,
        "type": "demo",
        "type_label": TASK_TYPE_LABELS["demo"],
        "status": task.status,
        "disclaimer": DEMO_DISCLAIMER,
        "error_summary": task.error_summary,
        "created_at": task.created_at.isoformat() + "Z",
        "preprocess": {
            "id": preprocess.id if preprocess else task.preprocess_id,
            "name": preprocess.name if preprocess else None,
            "height": preprocess.height if preprocess else None,
            "width": preprocess.width if preprocess else None,
        },
        "models": models_out,
        "samples": samples,
        "n": len(samples),
        "preview_sample_keys": preview_keys,
        "artifacts": artifacts,
        "legend": NEU_LEGEND,
        "cam_disclaimer": CAM_DISCLAIMER,
        "bundle_ready": task.status in {"success", "partial_success"},
        "bundle_url": f"/api/demo/tasks/{task.id}/bundle" if task.status in {"success", "partial_success"} else None,
    }
    for key in GT_LEAK_KEYS:
        payload.pop(key, None)
    return payload


def assert_demo_worker_contract(db: Session, task: Task) -> None:
    if task.type != "demo":
        raise RuntimeError("run_demo refused non-demo task")
    if task.has_gt:
        raise RuntimeError("demo has_gt must be false")
    sample_links = (
        db.query(TaskSample).filter(TaskSample.task_id == task.id).order_by(TaskSample.sort_order.asc()).all()
    )
    if not sample_links:
        raise RuntimeError("demo task has no samples")
    for link in sample_links:
        sample = db.get(Sample, link.sample_id)
        if sample is None:
            raise RuntimeError("demo sample missing")
        if sample.mask_uri:
            raise RuntimeError("demo worker refused sample with mask_uri")
    model_links = (
        db.query(TaskModel).filter(TaskModel.task_id == task.id).order_by(TaskModel.sort_order.asc()).all()
    )
    if not model_links:
        raise RuntimeError("demo task has no models")
    for tm in model_links:
        if tm.role != "baseline":
            raise RuntimeError("demo forbids student models")
        mv = db.get(ModelVersion, tm.model_version_id)
        model = db.get(Model, mv.model_id) if mv else None
        if mv is None or model is None or not is_demo_model(model, mv):
            raise RuntimeError("demo model not in whitelist")
