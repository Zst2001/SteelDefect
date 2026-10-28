from __future__ import annotations

import logging
import math
from redis.exceptions import RedisError

from sqlalchemy.orm import Session, selectinload

from app.cache import invalidate_after_write
from app.config import Settings, get_settings
from app.db.models import (
    DatasetVersion,
    Model,
    ModelPerfProfile,
    ModelVersion,
    PreprocessSpecRow,
    Sample,
    Task,
    TaskModel,
    TaskSample,
)
from app.errors import AppError
from app.services.task_artifacts import TaskArtifacts
from app.services.demo_identity import DemoIdentity
from app.services.demo_quota import raise_demo_quota, release_guest_quota, reserve_guest_quota
from app.services.tasks import TASK_TYPE_LABELS, _attach_models_and_samples, _enqueue_task
from app.util_time import new_id, utcnow
from app.services.dispatch import apply_task_delivery
from app.services.input_freeze import freeze_inputs
from app.services.submission import request_id, existing_task, lock_user
from infer.spec import CAM_DISCLAIMER, DEMO_CATALOG_KIND, DEMO_DISCLAIMER, DEMO_MODEL_SLUGS, NEU_LEGEND
from admit.perf import fps_from_latency_ms

GT_LEAK_KEYS = ("mask_uri", "mask", "has_mask", "has_gt", "origin_uri", "gt")
logger = logging.getLogger(__name__)


def _release_reservation(identity, task_id):
    try:
        release_guest_quota(identity, task_id)
    except RedisError as exc:
        # Financial/quota semantics are not cache bypass: retain an explicit diagnostic.
        logger.error("demo quota compensation unconfirmed task=%s error=%s", task_id, type(exc).__name__)
METRIC_LEAK_TOKENS = ("metrics", "miou", "mdice", "acc", "metric_set", "available")
GT_FIELD_TOKENS = ("mask_uri", "has_mask", "has_gt", "metrics", "miou", "mdice", "acc")
DEMO_ARTIFACT_KINDS = {"origin", "pred_color", "overlay", "boundary", "cam", "montage", "bundle", "log"}


def get_demo_version(db: Session, *, for_update: bool = False) -> DatasetVersion:
    query = (
        db.query(DatasetVersion)
        .filter(DatasetVersion.kind == DEMO_CATALOG_KIND)
        .order_by(DatasetVersion.created_at.asc())
    )
    if for_update:
        query = query.populate_existing().with_for_update()
    version = query.one_or_none()
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


def serialize_demo_model(
    model: Model, version: ModelVersion, *, profile: ModelPerfProfile | None = None
) -> dict:
    # Public catalog reads persisted facts only. Do not trigger measurement or
    # serialize the private profile (environment, paths and failure details).
    weight = version.weights[0] if version.weights else None
    param_count = weight.param_count if weight else None
    if profile and profile.status == "success" and profile.param_count is not None:
        param_count = profile.param_count
    fps = None
    if (
        profile is not None
        and profile.status == "success"
        and profile.device == "cpu"
        and profile.batch == 1
        and profile.input_kind == "dummy"
        and (profile.input_h, profile.input_w) == (version.input_h, version.input_w)
        and profile.latency_ms_per_image is not None
        and math.isfinite(profile.latency_ms_per_image)
        and profile.latency_ms_per_image > 0
    ):
        fps = fps_from_latency_ms(profile.latency_ms_per_image, batch=1)
    return {
        "id": version.id,
        "name": model.name,
        "slug": version.slug,
        "source": "builtin",
        "num_classes": version.num_classes,
        "input_size": [version.input_h, version.input_w],
        "requires_cuda": False,
        "runnable_here": True,
        "param_count": int(param_count) if param_count is not None and param_count >= 0 else None,
        "fps_per_image": fps,
    }


def list_demo_models(db: Session) -> dict:
    rows = (
        db.query(ModelVersion)
        .options(
            selectinload(ModelVersion.model),
            selectinload(ModelVersion.weights),
            selectinload(ModelVersion.perf_profile),
        )
        .all()
    )
    items = []
    for version in rows:
        model = version.model
        if model is None or not is_demo_model(model, version):
            continue
        items.append(serialize_demo_model(model, version, profile=version.perf_profile))
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
        .order_by(Sample.sample_key).populate_existing().with_for_update()
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
    idempotency_key: str | None = None,
) -> Task:
    settings = settings or get_settings()
    if identity.user is not None:
        lock_user(db, identity.user)
    version = get_demo_version(db, for_update=True)
    task_id = request_id("demo", identity.user.id if identity.user else identity.sid, idempotency_key)
    previous = existing_task(db, task_id, "demo", version.id, baseline_version_ids, None, sample_keys)
    if previous is not None:
        return previous
    samples = _resolve_demo_samples(db, version, sample_keys)
    baselines = _resolve_demo_models(db, baseline_version_ids, version)
    user = identity.user
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
            error_summary="QUEUE_PENDING: 已保存，尚未确认入队",
            updated_at=utcnow(),
        )
        db.add(task)
        db.flush()
        _attach_models_and_samples(db, task, baselines, None, samples)
        freeze_inputs(db, task, samples, settings)
        db.commit()
    except Exception:
        db.rollback()
        if reserved:
            # A lost DB commit acknowledgement is also uncertain. Only release
            # after a successful authoritative read proves no persisted task.
            try:
                missing = db.query(Task).filter_by(id=task_id).with_for_update().one_or_none() is None
            except Exception as exc:
                logger.error("demo commit outcome unknown task=%s error=%s", task_id, type(exc).__name__)
                missing = False
            if missing:
                _release_reservation(identity, task_id)
        raise
    invalidate_after_write(task.id, user.id if user is not None else None)
    delivery = _enqueue_task(settings, "apps.worker.jobs.run_demo", task.id, settings.demo_job_timeout_sec)
    outcome = apply_task_delivery(db, task, delivery)
    if reserved and outcome == "rejected":
        _release_reservation(identity, task.id)
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
    for artifact in policy.downloadable(bundle_ready=bundle_state["bundle_ready"]):
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
        {row["sample_key"] for row in artifacts if row["kind"] == "origin" and row["sample_key"]}
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
        **bundle_state,
        "bundle_url": f"/api/demo/tasks/{task.id}/bundle" if bundle_state["bundle_ready"] else None,
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
