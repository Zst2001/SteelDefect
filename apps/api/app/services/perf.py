from __future__ import annotations

from pathlib import Path

from app.services.dispatch import enqueue, Delivery
from app.services.submission import request_id
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.cache import invalidate_after_write, invalidate_models_lists, rq_connection
from app.config import Settings, get_settings
from app.db.models import Model, ModelPerfProfile, ModelVersion, Weight
from app.errors import AppError
from app.services.storage import resolve_uri
from app.util_time import new_id, utcnow
from admit.perf import fps_from_latency_ms


def can_measure(version: ModelVersion) -> bool:
    return version.status == "runnable" and not version.requires_cuda


def _weight_bytes(settings: Settings, weight: Weight | None) -> int | None:
    if weight is None:
        return None
    try:
        path = resolve_uri(weight.file_uri, settings)
    except AppError:
        return None
    if not path.is_file():
        return None
    return int(path.stat().st_size)


def _load_profile(db: Session, version_id: str) -> ModelPerfProfile | None:
    return db.query(ModelPerfProfile).filter(ModelPerfProfile.version_id == version_id).populate_existing().with_for_update().one_or_none()


def get_or_create_profile(db: Session, version: ModelVersion) -> ModelPerfProfile:
    # Serialize absence as well as updates. All writers lock version before profile.
    version = db.query(ModelVersion).filter_by(id=version.id).populate_existing().with_for_update().one()
    profile = _load_profile(db, version.id)
    if profile is not None:
        return profile
    profile = ModelPerfProfile(
        id=new_id(),
        version_id=version.id,
        status="unmeasured",
        warmup_runs=3,
        timed_runs=10,
        batch=1,
        input_h=version.input_h,
        input_w=version.input_w,
        input_kind="dummy",
        device="cpu",
        updated_at=utcnow(),
    )
    try:
        with db.begin_nested():
            db.add(profile)
            db.flush()
        return profile
    except IntegrityError:
        db.expire_all()
        existing = _load_profile(db, version.id)
        if existing is None:
            raise
        return existing


def serialize_perf(
    db: Session,
    version: ModelVersion,
    model: Model,
    *,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    profile = db.query(ModelPerfProfile).filter(ModelPerfProfile.version_id == version.id).one_or_none()
    weight = version.weights[0] if version.weights else None
    weight_bytes = profile.weight_bytes if profile and profile.weight_bytes is not None else _weight_bytes(settings, weight)
    param_count = None
    if profile and profile.param_count is not None:
        param_count = int(profile.param_count)
    elif weight and weight.param_count is not None:
        param_count = int(weight.param_count)
    flops = int(profile.flops) if profile and profile.flops is not None else None
    # A remeasurement keeps the last stored values for diagnosis, but queued,
    # failed or incompatible profiles must not publish them as current CPU speed.
    latency = None
    if (
        profile is not None
        and profile.status == "success"
        and profile.device == "cpu"
        and profile.batch == 1
        and profile.input_kind == "dummy"
        and (profile.input_h, profile.input_w) == (version.input_h, version.input_w)
    ):
        latency = profile.latency_ms_per_image
    fps = fps_from_latency_ms(latency)
    if fps is None:
        latency = None
    batch = profile.batch if profile else 1
    status = profile.status if profile else "unmeasured"
    runnable = can_measure(version)
    return {
        "status": status,
        "can_measure": runnable and status not in {"queued", "measuring"},
        "param_count": param_count,
        "weight_bytes": weight_bytes,
        "latency_ms_per_image": latency,
        "fps_per_image": fps,
        "flops": flops,
        "warmup_runs": profile.warmup_runs if profile else 3,
        "timed_runs": profile.timed_runs if profile else 10,
        "batch": batch,
        "input_h": profile.input_h if profile else version.input_h,
        "input_w": profile.input_w if profile else version.input_w,
        "input_kind": profile.input_kind if profile else "dummy",
        "device": profile.device if profile else "cpu",
        "env": profile.env_json if profile else None,
        "fail_message": profile.fail_message if profile else None,
        "measured_at": profile.measured_at.isoformat() if profile and profile.measured_at else None,
        "source": model.source,
        "disclaimer": "本机 CPU、batch=1、dummy 随机输入的前向。FPS = 1000 / ms/图。不是 CUDA 论文测速，也不是测试集指标。",
    }


def request_measure(db: Session, version: ModelVersion, model: Model, *, idempotency_key: str | None = None) -> ModelPerfProfile:
    version = db.query(ModelVersion).filter_by(id=version.id).populate_existing().with_for_update().one()
    from app.services.models import is_classification_version
    if is_classification_version(db, version):
        raise AppError("分类模型不使用分割测参执行器", code="TASK_KIND_MISMATCH", stage="protocol", status_code=400)
    if version.requires_cuda:
        raise AppError(
            "当前环境为 CPU，该模型标明需要 CUDA，不可测量。不会静默改用随机权重。",
            code="CUDA_REQUIRED",
            stage="resource",
            status_code=400,
        )
    if version.status != "runnable":
        raise AppError(
            "只有检查通过、当前环境可运行的模型才能测量参数量与耗时。",
            code="NOT_RUNNABLE",
            stage="auth",
            status_code=400,
        )
    profile = get_or_create_profile(db, version)
    requested_job_id = "perf-" + request_id("perf", version.id, idempotency_key)
    if profile.status in {"queued", "measuring"} or (idempotency_key is not None and profile.job_id == requested_job_id):
        return profile
    settings = get_settings()
    profile.status = "queued"
    profile.fail_message = "QUEUE_PENDING: 测参尚未确认入队"
    profile.updated_at = utcnow()
    profile.job_id = requested_job_id
    job_id = profile.job_id
    db.commit()
    delivery = enqueue_perf(version.id, settings, job_id=job_id)
    profile = db.query(ModelPerfProfile).filter_by(version_id=version.id).populate_existing().with_for_update().one()
    if profile.status == "queued" and profile.job_id == job_id:
        state = delivery.state if isinstance(delivery, Delivery) else "confirmed"
        if state == "confirmed":
            profile.fail_message = None
        elif state == "rejected":
            profile.status, profile.fail_message = "failed", "QUEUE_REJECTED: 测参未入队"
        elif state == "unknown":
            profile.fail_message = "QUEUE_UNKNOWN: 测参入队待核验；作业 ID=" + job_id
    db.commit()
    invalidate_models_lists()
    invalidate_after_write(None, model.owner_id)
    return profile


def enqueue_perf(version_id: str, settings: Settings | None = None, *, job_id: str | None = None):
    settings = settings or get_settings()
    return enqueue(settings, "apps.worker.jobs.run_perf", version_id, settings.perf_job_timeout_sec,
                   job_id=job_id or f"perf-{new_id()}")


def apply_measure_result(
    db: Session,
    version: ModelVersion,
    model: Model,
    payload: dict,
    *,
    settings: Settings | None = None,
) -> ModelPerfProfile:
    # Reject malformed runner output before mutating a profile or its weights.
    # In particular, NaN/Infinity cannot be represented by API JSON responses.
    try:
        latency = float(payload["latency_ms_per_image"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid performance latency: expected positive finite ms/image") from exc
    if fps_from_latency_ms(latency) is None:
        raise ValueError("Invalid performance latency: expected positive finite ms/image")
    settings = settings or get_settings()
    profile = get_or_create_profile(db, version)
    weight = db.query(Weight).filter(Weight.version_id == version.id).first()
    measured_params = payload.get("param_count")
    if measured_params is not None:
        measured_params = int(measured_params)
        profile.param_count = measured_params
        if weight is not None and weight.param_count is None:
            weight.param_count = measured_params
    weight_bytes = payload.get("weight_bytes")
    if weight_bytes is None:
        weight_bytes = _weight_bytes(settings, weight)
    profile.weight_bytes = int(weight_bytes) if weight_bytes is not None else None
    profile.latency_ms_per_image = latency
    flops = payload.get("flops")
    profile.flops = int(flops) if flops is not None else None
    profile.warmup_runs = int(payload.get("warmup_runs") or 3)
    profile.timed_runs = int(payload.get("timed_runs") or 10)
    profile.batch = int(payload.get("batch") or 1)
    profile.input_h = int(payload.get("input_h") or version.input_h)
    profile.input_w = int(payload.get("input_w") or version.input_w)
    profile.input_kind = str(payload.get("input_kind") or "dummy")
    profile.device = str(payload.get("device") or "cpu")
    profile.env_json = payload.get("env") if isinstance(payload.get("env"), dict) else None
    profile.status = "success"
    profile.fail_message = None
    profile.measured_at = utcnow()
    profile.updated_at = utcnow()
    db.flush()
    return profile


def mark_measure_failed(db: Session, version: ModelVersion, model: Model, message: str) -> ModelPerfProfile:
    profile = get_or_create_profile(db, version)
    profile.status = "failed"
    profile.fail_message = message
    profile.updated_at = utcnow()
    db.flush()
    return profile


def weight_path_for_version(settings: Settings, version: ModelVersion, weight: Weight | None) -> Path | None:
    if weight is None:
        return None
    return resolve_uri(weight.file_uri, settings)
