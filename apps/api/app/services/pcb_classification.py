"""Single private ROI classification on the existing Task/Record lifecycle."""
from __future__ import annotations

import hashlib
import json
import logging
from uuid import NAMESPACE_URL, uuid5

from rq.timeouts import JobTimeoutException

from app.cache import invalidate_after_write
from app.config import get_settings
from app.db.models import (AuditLog, Dataset, DatasetVersion, Model, ModelVersion, PreprocessSpecRow,
                           Sample, Task, TaskModel, Weight)
from app.errors import AppError
from app.services.classification import _registered
from app.services.dispatch import apply_task_delivery, enqueue
from app.services.input_freeze import current_samples, freeze_inputs, lock_version
from app.services.pcb_classification_uploads import MAX_UPLOAD_BYTES, SUPPORTED_FORMATS, prepare_upload
from app.services.submission import existing_task, lock_user, request_id
from app.util_time import new_id, utcnow
from infer.pcb_classification.catalog import DEFAULT, MODELS, PROTOCOL, admitted, catalog
from infer.pcb_classification.images import MAX_BYTES, MAX_PIXELS, decode

TYPE = "pcb_classify"  # Task.type is VARCHAR(16); no migration or collision with steel classification.
KIND = "pcb_cls_batch"
logger = logging.getLogger(__name__)


def asset_root(settings):
    return settings.repo_root / "assets/pcb_classification/deeppcb_roi_v0_formal_v1"


def require_enabled(settings):
    if not settings.pcb_classification_enabled:
        raise AppError("PCB 分类尚未启用，请联系管理员完成本机准入", code="PCB_CLS_DISABLED", stage="scene", status_code=409)


def asset(model_id, settings):
    if model_id not in MODELS:
        raise AppError("请选择已准入的 PCB 分类模型", code="PCB_CLS_MODEL_UNSUPPORTED", stage="protocol", status_code=400)
    try:
        proof = admitted(asset_root(settings))
        return {"model_id": model_id, "weight_sha256": MODELS[model_id][0],
                "source_hash": proof["source_hash"], "classes": proof["configs"]["classes"]["classes"]}
    except JobTimeoutException:
        raise
    except Exception as exc:
        raise AppError("PCB 分类资产未通过当前 Windows CPU 准入", code="PCB_CLS_ASSET_UNAVAILABLE", stage="load", status_code=409) from exc


def catalog_payload(settings=None):
    settings = settings or get_settings()
    rows = catalog(asset_root(settings))
    enabled = settings.pcb_classification_enabled
    ready = len(rows) == 2 and all(row["available"] for row in rows)
    classes = asset(DEFAULT, settings)["classes"] if ready else []
    return {"enabled": enabled, "available": enabled and ready, "models": rows, "classes": classes,
            "default_model": DEFAULT, "protocol_id": PROTOCOL, "max_image_bytes": MAX_UPLOAD_BYTES,
            "max_pixels": MAX_PIXELS, "supported_formats": list(SUPPORTED_FORMATS),
            "message": "仅上传已裁剪、以单个缺陷为主的 ROI；六类不包含正常类，不提供定位。"}


def _id(value):
    return str(uuid5(NAMESPACE_URL, "steel:pcb-cls:" + value))


def _protocol(db, item):
    extra = {"scene": "pcb", "task_kind": "classification", "protocol_id": PROTOCOL,
             "source_hash": item["source_hash"], "classes": item["classes"]}
    ident = _id("protocol:" + PROTOCOL + ":" + item["source_hash"])
    row, _ = _registered(db, PreprocessSpecRow, ident, lambda: PreprocessSpecRow(
        id=ident, name="pcb_cls_" + item["source_hash"][:24], height=224, width=224,
        apply_clahe=False, sp_threshold=0, dataset=PROTOCOL, extra_json=extra))
    if (row.dataset != PROTOCOL or row.extra_json != extra or row.apply_clahe
            or row.sp_threshold != 0 or (row.height, row.width) != (224, 224)):
        raise AppError("PCB 分类协议登记已变更", code="PCB_CLS_PROTOCOL_CHANGED", stage="protocol", status_code=409)
    return row


def register_model(db, item):
    slug = item["model_id"]
    spec = _protocol(db, item)
    mid = _id("model:" + slug)
    parent, _ = _registered(db, Model, mid, lambda: Model(id=mid, owner_id=None, name=MODELS[slug][2], source="builtin"))
    vid = _id("version:" + slug + ":" + item["weight_sha256"] + ":" + spec.id)
    version, created = _registered(db, ModelVersion, vid, lambda: ModelVersion(
        id=vid, model_id=mid, slug=slug, num_classes=6, in_channels=3, input_h=224, input_w=224,
        preprocess_id=spec.id, requires_cuda=False, status="runnable", visibility="public"))
    uri = f"asset:pcb_classification/deeppcb_roi_v0_formal_v1/models/{slug}.pth"
    if created:
        db.add(Weight(id=new_id(), version_id=vid, file_uri=uri, sha256=item["weight_sha256"], param_count=MODELS[slug][1]))
        db.flush()
    weights = db.query(Weight).filter_by(version_id=vid).populate_existing().with_for_update().all()
    if (parent.source != "builtin" or parent.owner_id is not None or version.model_id != mid
            or version.slug != slug or version.preprocess_id != spec.id or version.status != "runnable"
            or version.visibility != "public" or version.requires_cuda
            or (version.num_classes, version.in_channels, version.input_h, version.input_w) != (6, 3, 224, 224)
            or len(weights) != 1 or weights[0].sha256 != item["weight_sha256"] or weights[0].file_uri != uri
            or weights[0].param_count != MODELS[slug][1]):
        raise AppError("PCB 分类模型登记已变更", code="PCB_CLS_MODEL_CHANGED", stage="protocol", status_code=409)
    return version


def image_bytes(name, content, mime=None):
    try:
        return decode(content, name, mime)
    except (ValueError, OSError) as exc:
        raise AppError(str(exc), code="PCB_CLS_BAD_IMAGE", stage="file", status_code=400) from exc


def create_batch(db, user, name, content, mime, settings=None):
    settings = settings or get_settings()
    require_enabled(settings)
    item = asset(DEFAULT, settings)
    try:
        content, facts, source = prepare_upload(content, name)
    except (ValueError, OSError) as exc:
        raise AppError(str(exc), code="PCB_CLS_BAD_IMAGE", stage="file", status_code=400) from exc
    folder = path = None
    try:
        lock_user(db, user)
        spec = _protocol(db, item)
        dataset = Dataset(id=new_id(), owner_id=user.id, name="PCB 单缺陷 ROI 分类", visibility="private")
        db.add(dataset)
        db.flush()
        meta = {"scene": "pcb", "task_kind": "classification", "protocol_id": PROTOCOL,
                "filename": name[:128], "image": facts, "source_image": source, "classes": item["classes"]}
        version = DatasetVersion(id=new_id(), dataset_id=dataset.id, kind=KIND, class_map_json=meta,
                                 preprocess_id=spec.id, is_fixed_test=False, forbid_student_gt_download=False)
        db.add(version)
        db.flush()
        folder = settings.storage_path / "pcb_classification" / version.id
        folder.mkdir(parents=True, exist_ok=False)
        suffix = "png" if facts["format"] == "PNG" else "jpg"
        path = folder / f"image.{suffix}"
        with path.open("xb") as stream:
            stream.write(content)
        db.add(Sample(id=new_id(), version_id=version.id, sample_key="image",
                      origin_uri=f"data:pcb_classification/{version.id}/image.{suffix}", mask_uri=None,
                      width=facts["width"], height=facts["height"], sha256=hashlib.sha256(content).hexdigest()))
        db.add(AuditLog(id=new_id(), actor_id=user.id, action="pcb_cls.upload", target_type="dataset_version", target_id=version.id,
                        reason="已验证单张 ROI；不含真实类别标注"))
        db.commit()
        return {"batch_id": version.id, "sample_count": 1, "has_gt": False, **facts, "source_image": source}
    except Exception:
        db.rollback()
        if path:
            path.unlink(missing_ok=True)
        if folder and folder.exists():
            folder.rmdir()
        raise


def snapshot(db, task):
    version = db.query(DatasetVersion).filter_by(id=task.dataset_version_id).populate_existing().with_for_update().one()
    dataset = db.query(Dataset).filter_by(id=version.dataset_id).populate_existing().with_for_update().one()
    spec = db.query(PreprocessSpecRow).filter_by(id=task.preprocess_id).populate_existing().with_for_update().one()
    samples = current_samples(db, version.id)
    meta = version.class_map_json or {}
    if (task.type != TYPE or task.has_gt or version.kind != KIND or version.is_fixed_test or version.forbid_student_gt_download
            or dataset.owner_id != task.creator_id or dataset.visibility != "private"
            or spec.dataset != PROTOCOL or version.preprocess_id != task.preprocess_id
            or meta.get("protocol_id") != PROTOCOL or meta.get("task_kind") != "classification" or meta.get("scene") != "pcb"
            or len(samples) != 1 or samples[0].sample_key != "image" or samples[0].mask_uri is not None
            or (samples[0].width, samples[0].height) != (meta["image"]["width"], meta["image"]["height"])):
        raise ValueError("PCB classification contract changed")
    links = db.query(TaskModel).filter_by(task_id=task.id).populate_existing().with_for_update().all()
    if len(links) != 1 or links[0].role != "baseline":
        raise ValueError("PCB classification model role/count")
    mv = db.query(ModelVersion).filter_by(id=links[0].model_version_id).populate_existing().with_for_update().one()
    parent = db.query(Model).filter_by(id=mv.model_id).populate_existing().with_for_update().one()
    weights = db.query(Weight).filter_by(version_id=mv.id).populate_existing().with_for_update().all()
    if (parent.source != "builtin" or parent.owner_id is not None or mv.slug not in MODELS
            or (mv.num_classes, mv.in_channels, mv.input_h, mv.input_w) != (6, 3, 224, 224)
            or mv.preprocess_id != spec.id or len(weights) != 1):
        raise ValueError("PCB classification model changed")
    sample = samples[0]
    return {"dataset": meta, "preprocess": spec.extra_json,
            "model": {"id": mv.id, "slug": mv.slug, "weight_sha256": weights[0].sha256,
                      "weight_uri": weights[0].file_uri, "param_count": weights[0].param_count},
            "sample": {"id": sample.id, "sha256": sample.sha256, "width": sample.width, "height": sample.height}}


def create_task(db, user, *, batch_id, model_id, idempotency_key=None, settings=None):
    settings = settings or get_settings()
    require_enabled(settings)
    item = asset(model_id, settings)
    try:
        lock_user(db, user)
        version = lock_version(db, batch_id)
        dataset = db.get(Dataset, version.dataset_id) if version else None
        if not version or version.kind != KIND or not dataset or dataset.owner_id != user.id:
            raise AppError("ROI 批次不存在或不可访问", code="PCB_CLS_BATCH_FORBIDDEN", stage="auth", status_code=404)
        model = register_model(db, item)
        if version.preprocess_id != model.preprocess_id:
            raise AppError("分类协议已变更，请重新上传 ROI", code="PCB_CLS_PROTOCOL_CHANGED", stage="protocol", status_code=409)
        ident = request_id(TYPE, user.id, idempotency_key)
        previous = existing_task(db, ident, TYPE, version.id, [model.id], None)
        if previous is not None:
            return previous
        samples = current_samples(db, version.id)
        task = Task(id=ident, type=TYPE, creator_id=user.id, dataset_version_id=version.id,
                    preprocess_id=model.preprocess_id, status="queued", has_gt=False,
                    error_summary="QUEUE_PENDING: 已保存，尚未确认入队", updated_at=utcnow())
        db.add(task)
        db.flush()
        from app.services.tasks import _attach_models_and_samples
        _attach_models_and_samples(db, task, [model], None, samples)
        db.flush()
        freeze_inputs(db, task, samples, settings)
        db.add(AuditLog(id=new_id(), actor_id=user.id, action="pcb_cls.create", target_type="task", target_id=task.id,
                        reason="提交单张 ROI 六分类任务"))
        db.commit()
    except Exception:
        db.rollback()
        raise
    invalidate_after_write(task.id, user.id)
    from app.services.pcb_delivery import CALLBACK
    delivery = enqueue(settings, "apps.worker.jobs.run_pcb_classification", task.id,
                       settings.pcb_classification_job_timeout_sec, job_id=f"task-{task.id}", on_failure=CALLBACK)
    apply_task_delivery(db, task, delivery)
    return task


def serialize_task(db, task, settings=None):
    from app.services.task_artifacts import TaskArtifacts
    settings = settings or get_settings()
    meta = db.get(DatasetVersion, task.dataset_version_id).class_map_json or {}
    guard = TaskArtifacts(db, task, settings)
    result = None
    try:
        path = guard.file("pcb_classification.json")
        if path.stat().st_size <= 32000:
            result = json.loads(path.read_text(encoding="utf-8"))
    except (AppError, OSError, ValueError):
        pass
    link = db.query(TaskModel).filter_by(task_id=task.id).first()
    mv = db.get(ModelVersion, link.model_version_id) if link else None
    return {"id": task.id, "type": TYPE, "type_label": "PCB 缺陷分类", "scene": "pcb", "task_kind": "classification",
            "status": task.status, "error_summary": task.error_summary, "created_at": task.created_at.isoformat(),
            "has_gt": False, "n": 1, "classes": meta.get("classes", []), "input": meta.get("image", {}),
            "source_image": meta.get("source_image"),
            "protocol_id": PROTOCOL, "model": {"id": mv.slug, "name": MODELS.get(mv.slug, (None, None, mv.slug))[2]} if mv else None,
            "result": result, "metrics": {"available": False}, "bundle_ready": False,
            "artifacts": [{"kind": a.kind, "rel_path": a.rel_path, "url": f"/api/tasks/{task.id}/file/{a.rel_path}"}
                          for a in guard.downloadable()],
            "open_path": f"/inspect/pcb/classification/tasks/{task.id}",
            "result_download_url": f"/api/tasks/{task.id}/file/pcb_classification.json" if result else None,
            "disclaimer": "仅对已裁剪单缺陷 ROI 六分类，不含正常类、不提供定位；置信度不是准确率。"}
