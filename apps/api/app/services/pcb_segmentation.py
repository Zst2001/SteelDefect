"""Private, single-image PCB tasks on the existing task and permission system."""
from __future__ import annotations

import hashlib
import io
import json
import logging
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import numpy as np
from PIL import Image
from rq.timeouts import JobTimeoutException

from app.cache import invalidate_after_write
from app.config import get_settings
from app.db.models import (Artifact, AuditLog, Dataset, DatasetVersion, Model, ModelVersion,
                           PreprocessSpecRow, Sample, Task, TaskModel, TaskSample, Weight)
from app.errors import AppError
from app.services.classification import _registered
from app.services.dispatch import apply_task_delivery, enqueue
from app.services.input_freeze import current_samples, freeze_inputs, lock_version
from app.services.submission import existing_task, lock_user, request_id
from app.util_time import new_id, utcnow
from infer.pcb.runtime import MODELS

TYPE = "pcb_segmentation"
MAX_IMAGE_BYTES = 2 * 1024 * 1024
CLASSES = [{"id": 0, "key": "background", "name": "背景"}, {"id": 1, "key": "defect", "name": "缺陷"}]
NAMES = {"unet": "U-Net", "unet_resnet18": "ResNet18-U-Net", "unetpp_resnet18": "ResNet18-U-Net++"}
logger = logging.getLogger(__name__)


def enabled(settings=None):
    return bool(getattr(settings or get_settings(), "pcb_segmentation_enabled", False))


def asset_root(settings):
    return settings.repo_root / "assets/pcb/meiwei_v2_formal_v1"


def require_enabled(settings):
    if not enabled(settings):
        raise AppError("PCB 分割尚未启用，请联系管理员完成本地验收", code="PCB_DISABLED", stage="scene", status_code=409)


def asset(model_id, settings):
    if model_id not in MODELS:
        raise AppError("请选择已准入的 PCB 分割模型", code="PCB_MODEL_UNSUPPORTED", stage="protocol", status_code=400)
    try:
        from infer.pcb.catalog import catalog
        item = next(row for row in catalog(asset_root(settings)) if row["slug"] == model_id)
        if not item.get("available") or item["weight_sha256"] != MODELS[model_id][0]:
            raise ValueError("identity unavailable")
        return item
    except JobTimeoutException:
        # The RQ deadline belongs to task execution, not asset admission.
        raise
    except Exception as exc:
        raise AppError("PCB 三模型准入或资产校验未通过", code="PCB_ASSET_UNAVAILABLE", stage="load", status_code=409) from exc


def catalog_payload(settings=None):
    settings = settings or get_settings()
    from infer.pcb.catalog import catalog
    rows = catalog(asset_root(settings))
    ready = len(rows) == 3 and all(row.get("available") for row in rows)
    return {"enabled": enabled(settings), "available": enabled(settings) and ready,
            "models": rows, "default_model": "unet", "max_image_bytes": MAX_IMAGE_BYTES,
            "input": {"width": 220, "height": 220, "mode": "RGB", "formats": ["PNG", "JPEG"]},
            "message": "单张 220×220 RGB 图片；无配对 GT 不计算真实性能指标。"}


def _id(value):
    return str(uuid5(NAMESPACE_URL, "steel:pcb:" + value))


def _protocol(db, item, include_cam=False):
    source_hash = item["deployment_source_hash"]
    extra = {"scene": "pcb", "task_kind": "segmentation", "protocol_hash": item["protocol_hash"],
             "deployment_source_hash": source_hash,
             "classes": CLASSES, "include_cam": include_cam}
    ident = _id("protocol:" + item["protocol_hash"] + ":" + source_hash + ":" + str(include_cam))
    row, _ = _registered(db, PreprocessSpecRow, ident, lambda: PreprocessSpecRow(
        id=ident, name="pcb_" + item["protocol_hash"][:16] + "_" + source_hash[:16] + ("_cam" if include_cam else "_base"),
        height=256, width=256, apply_clahe=False, sp_threshold=0, dataset="pcb_meiwei_v2", extra_json=extra))
    if (row.dataset != "pcb_meiwei_v2" or row.extra_json != extra or row.apply_clahe
            or row.sp_threshold != 0 or (row.height, row.width) != (256, 256)):
        raise AppError("PCB 处理协议登记不一致", code="PCB_PROTOCOL_CHANGED", stage="protocol", status_code=409)
    return row


def register_model(db, item):
    slug = item["slug"]
    spec = _protocol(db, item)
    mid = _id("model:" + slug)
    parent, _ = _registered(db, Model, mid, lambda: Model(id=mid, owner_id=None, name=NAMES[slug], source="builtin"))
    vid = _id("version:" + slug + ":" + item["weight_sha256"] + ":" + spec.id)
    version, created = _registered(db, ModelVersion, vid, lambda: ModelVersion(
        id=vid, model_id=mid, slug=slug, num_classes=2, in_channels=3, input_h=256, input_w=256,
        preprocess_id=spec.id, requires_cuda=False, status="runnable", visibility="public"))
    uri = f"asset:pcb/meiwei_v2_formal_v1/models/{slug}/weights.pth"
    if created:
        db.add(Weight(id=new_id(), version_id=vid, file_uri=uri, sha256=item["weight_sha256"], param_count=MODELS[slug][1]))
        db.flush()
    weights = db.query(Weight).filter_by(version_id=vid).populate_existing().with_for_update().all()
    if (parent.source != "builtin" or parent.owner_id is not None or version.model_id != mid
            or version.slug != slug or version.preprocess_id != spec.id or version.status != "runnable"
            or version.requires_cuda or (version.num_classes, version.in_channels, version.input_h, version.input_w) != (2, 3, 256, 256)
            or len(weights) != 1 or weights[0].sha256 != item["weight_sha256"] or weights[0].file_uri != uri
            or weights[0].param_count != MODELS[slug][1]):
        raise AppError("PCB 模型登记不一致", code="PCB_MODEL_CHANGED", stage="protocol", status_code=409)
    return version


def image_bytes(name, content, *, gt=False):
    """Preserve source bytes; normalize only explicitly supported lossless GT."""
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise AppError("每个文件须为 1 字节至 2 MiB", code="PCB_IMAGE_SIZE", stage="file", status_code=400)
    try:
        with Image.open(io.BytesIO(content)) as image:
            extension = Path(name.replace("\\", "/")).suffix.lower()
            formats = {"PNG": {".png"}} if gt else {"PNG": {".png"}, "JPEG": {".jpg", ".jpeg"}}
            if image.format not in formats or extension not in formats[image.format]:
                raise ValueError("format or extension")
            if image.size != (220, 220) or image.mode != ("L" if gt else "RGB") or getattr(image, "n_frames", 1) != 1:
                raise ValueError("size or channels")
            if image.getexif().get(274, 1) != 1:
                raise ValueError("EXIF orientation")
            image.load()
            suffix = "png" if image.format == "PNG" else "jpg"
            if not gt:
                return content, suffix
            values = np.asarray(image)
            unique = set(np.unique(values).tolist())
            if not (unique <= {0, 1} or unique <= {0, 255}):
                raise ValueError("GT values")
            normalized = (values > 0).astype(np.uint8)
            stream = io.BytesIO()
            Image.fromarray(normalized).save(stream, format="PNG")
            return stream.getvalue(), "png"
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        message = ("GT 须为 220×220 单通道 PNG，像素只含 0/1 或 0/255" if gt else
                   "图片须为 220×220 RGB 单帧 PNG/JPEG，扩展名须与内容一致，EXIF 方向只能为 1 或缺省")
        raise AppError(message, code="PCB_BAD_GT" if gt else "PCB_BAD_IMAGE", stage="file", status_code=400) from exc


def create_batch(db, user, file, gt=None, settings=None):
    settings = settings or get_settings()
    require_enabled(settings)
    item = asset("unet", settings)  # admission is all three, never a partial fallback
    original, suffix = image_bytes(*file)
    mask = image_bytes(*gt, gt=True)[0] if gt is not None else None
    paths = []
    folder = None
    try:
        lock_user(db, user)
        spec = _protocol(db, item)
        dataset = Dataset(id=new_id(), owner_id=user.id, name="PCB 分割单图批次", visibility="private")
        db.add(dataset)
        db.flush()
        meta = {"scene": "pcb", "task_kind": "segmentation", "protocol_hash": item["protocol_hash"],
                "classes": CLASSES, "filename": file[0].replace("\\", "/").split("/")[-1][:128],
                "gt_encoding": "0/1" if mask is not None else None}
        version = DatasetVersion(id=new_id(), dataset_id=dataset.id, kind="pcb_batch", class_map_json=meta,
                                 preprocess_id=spec.id, is_fixed_test=False, forbid_student_gt_download=False)
        db.add(version)
        db.flush()
        folder = settings.storage_path / "pcb" / version.id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / f"image.{suffix}"
        paths.append(path)
        path.write_bytes(original)
        if mask is not None:
            path = folder / "gt.png"
            paths.append(path)
            path.write_bytes(mask)
        db.add(Sample(id=new_id(), version_id=version.id, sample_key="image",
                      origin_uri=f"data:pcb/{version.id}/image.{suffix}",
                      mask_uri=f"data:pcb/{version.id}/gt.png" if mask is not None else None,
                      width=220, height=220, sha256=hashlib.sha256(original).hexdigest()))
        db.add(AuditLog(id=new_id(), actor_id=user.id, action="pcb.upload", target_type="dataset_version", target_id=version.id,
                        reason="已验证单张 PCB 图像及可选二值 GT"))
        db.commit()
        return {"batch_id": version.id, "sample_count": 1, "has_gt": mask is not None,
                "samples": [{"sample_key": "image", "filename": meta["filename"], "width": 220, "height": 220}]}
    except Exception:
        db.rollback()
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("PCB upload cleanup incomplete")
        if folder is not None and folder.exists():
            try:
                folder.rmdir()
            except OSError:
                logger.warning("PCB upload directory cleanup incomplete")
        raise


def task_include_cam(db, task):
    spec = db.query(PreprocessSpecRow).filter_by(id=task.preprocess_id).populate_existing().with_for_update().one()
    value = (spec.extra_json or {}).get("include_cam")
    if type(value) is not bool:
        raise AppError("PCB 解释图层配置无效", code="PCB_PROTOCOL_CHANGED", stage="protocol")
    return value


def pcb_snapshot(db, task):
    version = db.query(DatasetVersion).filter_by(id=task.dataset_version_id).populate_existing().with_for_update().one()
    dataset = db.query(Dataset).filter_by(id=version.dataset_id).populate_existing().with_for_update().one()
    spec = db.query(PreprocessSpecRow).filter_by(id=task.preprocess_id).populate_existing().with_for_update().one()
    base = db.query(PreprocessSpecRow).filter_by(id=version.preprocess_id).populate_existing().with_for_update().one()
    if (task.type != TYPE or version.kind != "pcb_batch" or version.is_fixed_test or version.forbid_student_gt_download
            or dataset.owner_id != task.creator_id or dataset.visibility != "private"
            or spec.dataset != "pcb_meiwei_v2" or base.dataset != "pcb_meiwei_v2"):
        raise ValueError("PCB identity changed")
    samples = db.query(Sample).filter_by(version_id=version.id).order_by(Sample.sample_key).populate_existing().with_for_update().all()
    if len(samples) != 1 or samples[0].sample_key != "image" or (samples[0].width, samples[0].height) != (220, 220) or bool(samples[0].mask_uri) != bool(task.has_gt):
        raise ValueError("PCB sample contract changed")
    links = db.query(TaskModel).filter_by(task_id=task.id).populate_existing().with_for_update().all()
    if len(links) != 1:
        raise ValueError("PCB model count changed")
    models = []
    for link in links:
        mv = db.query(ModelVersion).filter_by(id=link.model_version_id).populate_existing().with_for_update().one()
        parent = db.query(Model).filter_by(id=mv.model_id).populate_existing().with_for_update().one()
        weights = db.query(Weight).filter_by(version_id=mv.id).populate_existing().with_for_update().all()
        if (link.role != "baseline" or parent.source != "builtin" or parent.owner_id is not None or mv.slug not in MODELS
                or mv.num_classes != 2 or mv.in_channels != 3 or (mv.input_h, mv.input_w) != (256, 256)
                or mv.preprocess_id != base.id or len(weights) != 1):
            raise ValueError("PCB model contract changed")
        models.append({"id": mv.id, "slug": mv.slug, "preprocess_id": mv.preprocess_id,
                       "weight_sha256": weights[0].sha256, "weight_uri": weights[0].file_uri,
                       "param_count": weights[0].param_count, "role": link.role})
    return {"scene": "pcb", "task_kind": "segmentation", "dataset": version.class_map_json,
            "preprocess": spec.extra_json, "base_preprocess": base.extra_json, "models": models,
            "sample_facts": [{"id": s.id, "sha256": s.sha256, "width": s.width, "height": s.height} for s in samples]}


def create_pcb_task(db, user, *, batch_id, model_id, include_cam=False, idempotency_key=None, settings=None):
    settings = settings or get_settings()
    require_enabled(settings)
    if type(include_cam) is not bool:
        raise AppError("CAM 选项须为布尔值", code="PCB_BAD_CAM_OPTION", stage="protocol", status_code=400)
    item = asset(model_id, settings)
    try:
        lock_user(db, user)
        version = lock_version(db, batch_id)
        dataset = db.get(Dataset, version.dataset_id) if version else None
        if not version or version.kind != "pcb_batch" or not dataset or dataset.owner_id != user.id:
            raise AppError("PCB 批次不存在或不属于当前用户", code="PCB_BATCH_FORBIDDEN", stage="auth", status_code=404)
        if (version.class_map_json or {}).get("protocol_hash") != item["protocol_hash"]:
            raise AppError("PCB 批次协议不一致", code="PCB_PROTOCOL_CHANGED", stage="protocol", status_code=409)
        model = register_model(db, item)
        spec = _protocol(db, item, include_cam)
        ident = request_id(TYPE, user.id, idempotency_key)
        previous = existing_task(db, ident, TYPE, version.id, [model.id], None)
        if previous is not None:
            if previous.preprocess_id != spec.id:
                raise AppError("同一幂等键不能修改 CAM 选项", code="IDEMPOTENCY_CONFLICT", stage="protocol", status_code=409)
            return previous
        samples = current_samples(db, version.id)
        if len(samples) != 1:
            raise AppError("PCB 首期仅支持单图", code="PCB_BAD_BATCH", stage="protocol", status_code=409)
        task = Task(id=ident, type=TYPE, creator_id=user.id, dataset_version_id=version.id,
                    preprocess_id=spec.id, status="queued", has_gt=bool(samples[0].mask_uri),
                    error_summary="QUEUE_PENDING: 已保存，尚未确认入队", updated_at=utcnow())
        db.add(task)
        db.flush()
        from app.services.tasks import _attach_models_and_samples
        _attach_models_and_samples(db, task, [model], None, samples)
        db.flush()
        freeze_inputs(db, task, samples, settings)
        db.add(AuditLog(id=new_id(), actor_id=user.id, action="pcb.create", target_type="task", target_id=task.id,
                        reason="提交受控 PCB 分割任务"))
        db.commit()
    except Exception:
        db.rollback()
        raise
    invalidate_after_write(task.id, user.id)
    from app.services.pcb_delivery import CALLBACK
    delivery = enqueue(settings, "apps.worker.jobs.run_pcb_segmentation", task.id,
                       settings.pcb_job_timeout_sec, job_id=f"task-{task.id}", on_failure=CALLBACK)
    apply_task_delivery(db, task, delivery)
    return task


def serialize_pcb_metrics(task):
    if not task.has_gt or task.status != "success" or task.metric_set is None or task.metric_set.scope != "pcb_uploaded_pair":
        return {"available": False}
    return task.metric_set.payload_json


def serialize_pcb_task(db, task, settings=None):
    from app.services.task_artifacts import TaskArtifacts
    settings = settings or get_settings()
    version = db.get(DatasetVersion, task.dataset_version_id)
    meta = version.class_map_json or {}
    guard = TaskArtifacts(db, task, settings)
    result = {}
    try:
        result = json.loads(guard.file("pcb.json").read_text(encoding="utf-8"))
    except (AppError, OSError, ValueError):
        pass
    arts = [{"kind": a.kind, "sample_key": a.sample_key, "model_version_id": a.model_version_id,
             "rel_path": a.rel_path, "url": f"/api/tasks/{task.id}/file/{a.rel_path}"} for a in guard.downloadable()]
    link = db.query(TaskModel).filter_by(task_id=task.id).first()
    mv = db.get(ModelVersion, link.model_version_id) if link else None
    weight = db.query(Weight).filter_by(version_id=mv.id).first() if mv else None
    sample = db.query(Sample).join(TaskSample, Sample.id == TaskSample.sample_id).filter(TaskSample.task_id == task.id).first()
    return {"id": task.id, "type": TYPE, "type_label": "PCB 表面缺陷分割", "scene": "pcb", "task_kind": "segmentation",
            "status": task.status, "has_gt": task.has_gt, "n": 1, "include_cam": task_include_cam(db, task),
            "error_summary": task.error_summary, "created_at": task.created_at.isoformat(), "classes": CLASSES,
            "model": {"id": mv.slug, "model_version_id": mv.id, "name": NAMES.get(mv.slug, mv.slug),
                      "status": link.status, "weight_sha256": weight.sha256 if weight else None,
                      "protocol_hash": meta.get("protocol_hash")} if mv else None,
            "samples": [{"sample_key": "image", "filename": meta.get("filename"), "sha256": sample.sha256 if sample else None}],
            "artifacts": arts, "metrics": serialize_pcb_metrics(task),
            "cam": result.get("cam", {"status": "pending" if task.status in {"queued", "running"} else "not_requested"}),
            "bundle_ready": False, "open_path": f"/inspect/pcb/tasks/{task.id}",
            "result_download_url": f"/api/tasks/{task.id}/file/pcb.json" if result else None,
            "disclaimer": "无配对 GT 无法计算真实性能指标；缺陷概率图与 Grad-CAM 不是精度。"}
