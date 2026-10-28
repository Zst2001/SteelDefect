"""Authenticated NEU-CLS batches using the existing task/queue/ownership tables."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.cache import invalidate_after_write
from app.config import get_settings
from app.db.models import (AuditLog, Dataset, DatasetVersion, Model, ModelVersion,
                           PreprocessSpecRow, Sample, Task, TaskModel, Weight)
from app.errors import AppError
from app.services.dispatch import apply_task_delivery, enqueue
from app.services.input_freeze import current_samples, freeze_inputs, lock_version
from app.services.storage import sha256_file
from app.services.submission import existing_task, lock_user, request_id
from app.util_time import new_id, utcnow
from infer.classification import DEFAULT_MODEL, MODEL_SLUGS, catalog, inspect_asset

MAX_IMAGES = 50
MAX_MODELS = 3
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def asset_root(settings):
    return settings.repo_root / "assets" / "classification" / "neu_cls_v1"


def asset(slug, settings):
    if slug not in MODEL_SLUGS:
        raise AppError("请选择已登记的内置分类模型", code="CLASSIFICATION_MODEL_UNSUPPORTED", stage="protocol", status_code=400)
    try:
        return inspect_asset(slug, root=asset_root(settings))
    except Exception as exc:
        raise AppError("分类模型资产未通过校验，请联系管理员", code="CLASSIFICATION_MODEL_UNAVAILABLE", stage="load", status_code=409) from exc


def catalog_payload(settings=None):
    settings = settings or get_settings()
    return {"models": catalog(root=asset_root(settings)), "default_model": DEFAULT_MODEL,
            "max_images": MAX_IMAGES, "max_models": MAX_MODELS, "max_image_bytes": MAX_IMAGE_BYTES}


def _upload_asset(settings):
    # Every accepted asset is bound to the same canonical class/preprocess
    # hashes by inspect_asset; a missing default must not disable other models.
    for slug in (DEFAULT_MODEL, *(name for name in MODEL_SLUGS if name != DEFAULT_MODEL)):
        try:
            return asset(slug, settings)
        except AppError:
            continue
    raise AppError("暂无可用分类模型，请联系管理员检查资产", code="CLASSIFICATION_MODEL_UNAVAILABLE", stage="load", status_code=409)


def _id(value):
    return str(uuid5(NAMESPACE_URL, "steel:classification:" + value))


def _registered(db, cls, ident, factory):
    query = lambda: db.query(cls).filter_by(id=ident).populate_existing().with_for_update().one_or_none()
    # Avoid a missing-row FOR UPDATE gap lock: two first installers could both
    # hold that gap then deadlock on insertion under MySQL REPEATABLE READ.
    if db.get(cls, ident) is not None:
        row = query()
        if row is not None:
            return row, False
    try:
        with db.begin_nested():
            row = factory()
            db.add(row)
            db.flush()
        return row, True
    except IntegrityError:
        row = query()
        if row is None:
            raise
        return row, False


def _protocol(db, item):
    pid = _id("protocol:" + item.protocol_hash)
    expected = {"task_kind": "classification", "protocol_hash": item.protocol_hash,
                "classes": item.classes, "preprocess": item.preprocess}
    row, _ = _registered(db, PreprocessSpecRow, pid, lambda: PreprocessSpecRow(
        id=pid, name="neu_cls_" + item.protocol_hash[:32], height=224, width=224,
        apply_clahe=False, sp_threshold=0, dataset="neu_cls", extra_json=expected))
    if row.dataset != "neu_cls" or row.extra_json != expected:
        raise AppError("分类协议登记已变更", code="CLASSIFICATION_PROTOCOL_CHANGED", stage="protocol", status_code=409)
    return row


def register_model(db, item):
    protocol = _protocol(db, item)
    model_id = _id("model:" + item.slug)
    parent, _ = _registered(db, Model, model_id, lambda: Model(id=model_id, owner_id=None, name=item.name, source="builtin"))
    version_id = _id("version:" + item.slug + ":" + item.weight_sha256 + ":" + item.protocol_hash)
    version, created = _registered(db, ModelVersion, version_id, lambda: ModelVersion(
        id=version_id, model_id=parent.id, slug=item.slug, num_classes=6,
        in_channels=3, input_h=224, input_w=224, preprocess_id=protocol.id,
        requires_cuda=False, status="runnable", visibility="public"))
    if created:
        db.add(Weight(id=new_id(), version_id=version.id,
                      file_uri=f"asset:classification/neu_cls_v1/{item.slug}/weights.pth",
                      sha256=item.weight_sha256, param_count=item.param_count))
        db.flush()
    weights = db.query(Weight).filter_by(version_id=version.id).populate_existing().with_for_update().all()
    if (parent.source != "builtin" or parent.owner_id is not None or version.preprocess_id != protocol.id
            or version.status != "runnable" or version.model_id != parent.id or version.slug != item.slug
            or (version.num_classes, version.in_channels, version.input_h, version.input_w) != (6, 3, 224, 224)
            or version.requires_cuda or len(weights) != 1 or weights[0].sha256 != item.weight_sha256
            or weights[0].file_uri != f"asset:classification/neu_cls_v1/{item.slug}/weights.pth"):
        raise AppError("分类模型登记不一致", code="CLASSIFICATION_MODEL_UNAVAILABLE", stage="protocol", status_code=409)
    return version


def parse_labels(raw, count):
    if raw in (None, "", "null"):
        return None
    try:
        values = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError) as exc:
        raise AppError("分类标签须为 JSON 整数数组", code="BAD_CLASS_LABELS", stage="protocol", status_code=400) from exc
    if not isinstance(values, list) or len(values) != count or any(type(v) is not int or not 0 <= v <= 5 for v in values):
        raise AppError("标签须与图片逐一对应，全部为 0–5；无标签时请不填写", code="BAD_CLASS_LABELS", stage="protocol", status_code=400)
    return values


def _image_bytes(content):
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise AppError("单图大小须为 1 字节至 10 MiB", code="CLASSIFICATION_IMAGE_SIZE", stage="file", status_code=400)
    try:
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
            if image.format not in {"PNG", "JPEG", "BMP", "TIFF"} or image.mode not in {"L", "RGB", "RGBA", "P"}:
                raise ValueError("unsupported image")
            if getattr(image, "n_frames", 1) != 1 or min(width, height) < 1 or width * height > 4_000_000 or max(width, height) / min(width, height) > 4:
                raise ValueError("dimensions")
            image.load()
            suffix = {"PNG": "png", "JPEG": "jpg", "BMP": "bmp", "TIFF": "tiff"}[image.format]
            return content, width, height, suffix
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise AppError("图片损坏或格式/尺寸不支持；仅单帧 PNG、JPEG、BMP、TIFF，至多 400 万像素、长宽比不超过 4", code="CLASSIFICATION_BAD_IMAGE", stage="file", status_code=400) from exc


def create_batch(db: Session, user, files: list[tuple[str, bytes]], labels=None, settings=None):
    settings = settings or get_settings()
    if not 1 <= len(files) <= MAX_IMAGES:
        raise AppError("请上传 1–50 张分类图片", code="CLASSIFICATION_IMAGE_COUNT", stage="file", status_code=400)
    labels = parse_labels(labels, len(files))
    item = _upload_asset(settings)
    prepared, seen = [], set()
    for index, (name, content) in enumerate(files):
        original, width, height, suffix = _image_bytes(content)
        digest = hashlib.sha256(original).hexdigest()
        if digest in seen:
            raise AppError("批次含重复图像，请移除后重试", code="CLASSIFICATION_DUPLICATE_IMAGE", stage="file", status_code=400)
        seen.add(digest)
        filename = name.replace("\\", "/").split("/")[-1][:128] or f"image_{index + 1}"
        prepared.append((f"image_{index + 1:04d}", filename, original, width, height, digest, suffix))
    paths = []
    try:
        lock_user(db, user)
        protocol = _protocol(db, item)
        dataset = Dataset(id=new_id(), owner_id=user.id, name="钢铁分类上传批次", visibility="private")
        db.add(dataset)
        db.flush()
        meta = {"task_kind": "classification", "classes": item.classes, "protocol_hash": item.protocol_hash,
                "labels_by_sample_key": {row[0]: labels[i] for i, row in enumerate(prepared)} if labels is not None else {},
                "filenames": {row[0]: row[1] for row in prepared}}
        version = DatasetVersion(id=new_id(), dataset_id=dataset.id, kind="classification_batch",
                                 class_map_json=meta, preprocess_id=protocol.id, is_fixed_test=False,
                                 forbid_student_gt_download=False)
        db.add(version)
        db.flush()
        folder = settings.storage_path / "classification" / version.id
        folder.mkdir(parents=True, exist_ok=False)
        for key, _, content, width, height, digest, suffix in prepared:
            path = folder / f"{key}.{suffix}"
            path.write_bytes(content)
            paths.append(path)
            db.add(Sample(id=new_id(), version_id=version.id, sample_key=key,
                          origin_uri=f"data:classification/{version.id}/{key}.{suffix}", mask_uri=None,
                          width=width, height=height, sha256=digest))
        db.add(AuditLog(id=new_id(), actor_id=user.id, action="classification.upload", target_type="dataset_version", target_id=version.id, reason="已验证分类图像与图级标签"))
        db.commit()
        return {"batch_id": version.id, "sample_count": len(prepared), "has_gt": labels is not None,
                "samples": [{"sample_key": row[0], "filename": row[1], **({"class_id": labels[i]} if labels is not None else {})} for i, row in enumerate(prepared)]}
    except Exception:
        db.rollback()
        for path in paths:
            path.unlink(missing_ok=True)
        raise


def create_classification_task(db, user, *, batch_id, model_slugs, idempotency_key=None, settings=None):
    settings = settings or get_settings()
    if not isinstance(model_slugs, list) or not 1 <= len(model_slugs) <= MAX_MODELS or len(set(model_slugs)) != len(model_slugs):
        raise AppError("请选择 1–3 个不同的内置分类模型", code="CLASSIFICATION_MODEL_COUNT", stage="protocol", status_code=400)
    lock_user(db, user)
    version = lock_version(db, batch_id)
    dataset = db.get(Dataset, version.dataset_id) if version else None
    if version is None or version.kind != "classification_batch" or dataset is None or dataset.owner_id != user.id:
        raise AppError("分类批次不存在或不属于当前用户", code="CLASSIFICATION_BATCH_FORBIDDEN", stage="auth", status_code=404)
    items = [asset(slug, settings) for slug in model_slugs]
    meta = version.class_map_json or {}
    if any(item.protocol_hash != meta.get("protocol_hash") for item in items):
        raise AppError("模型与图像批次的分类协议不一致", code="CLASSIFICATION_PROTOCOL_MISMATCH", stage="protocol", status_code=409)
    try:
        models = [register_model(db, item) for item in items]
        task_id = request_id("classification", user.id, idempotency_key)
        previous = existing_task(db, task_id, "classification", version.id, [m.id for m in models], None)
        if previous is not None:
            return previous
        samples = current_samples(db, version.id)
        labels = meta.get("labels_by_sample_key", {})
        if not 1 <= len(samples) <= MAX_IMAGES or any(s.mask_uri is not None for s in samples):
            raise AppError("分类批次图像无效", code="CLASSIFICATION_BAD_BATCH", stage="protocol", status_code=409)
        if labels and (set(labels) != {s.sample_key for s in samples} or any(type(v) is not int or not 0 <= v <= 5 for v in labels.values())):
            raise AppError("分类标签不完整或无效", code="BAD_CLASS_LABELS", stage="protocol", status_code=409)
        task = Task(id=task_id, type="classification", creator_id=user.id, dataset_version_id=version.id,
                    preprocess_id=version.preprocess_id, status="queued", has_gt=bool(labels),
                    error_summary="QUEUE_PENDING: 已保存，尚未确认入队", updated_at=utcnow())
        db.add(task)
        db.flush()
        from app.services.tasks import _attach_models_and_samples
        _attach_models_and_samples(db, task, models, None, samples)
        db.flush()
        freeze_inputs(db, task, samples, settings)
        db.add(AuditLog(id=new_id(), actor_id=user.id, action="classification.create", target_type="task", target_id=task.id, reason="提交可信内置分类任务"))
        db.commit()
    except Exception:
        db.rollback()
        raise
    invalidate_after_write(task.id, user.id)
    delivery = enqueue(settings, "apps.worker.jobs.run_classification", task.id,
                       settings.compare_job_timeout_sec, job_id=f"task-{task.id}")
    apply_task_delivery(db, task, delivery)
    return task


def serialize_classification_metrics(task):
    if not task.has_gt or task.status not in {"success", "partial_success"} or task.metric_set is None:
        return {"available": False}
    return task.metric_set.payload_json


def serialize_classification_task(db, task, settings=None):
    from app.db.models import TaskSample
    from app.services.task_artifacts import TaskArtifacts
    settings = settings or get_settings()
    version = db.get(DatasetVersion, task.dataset_version_id)
    meta = version.class_map_json or {}
    guard = TaskArtifacts(db, task, settings)
    predictions, download = [], None
    if task.status in {"success", "partial_success", "failed"}:
        try:
            result = json.loads(guard.file("classification.json").read_text(encoding="utf-8"))
            predictions = result.get("predictions", [])
            download = f"/api/tasks/{task.id}/file/classification.json"
        except (AppError, OSError, ValueError):
            pass
    samples = []
    for link in db.query(TaskSample).filter_by(task_id=task.id).order_by(TaskSample.sort_order).all():
        sample = db.get(Sample, link.sample_id)
        if sample is None:
            continue
        preview = None
        try:
            guard.file(f"origin/{sample.sample_key}.png")
            preview = f"/api/tasks/{task.id}/file/origin/{sample.sample_key}.png"
        except AppError:
            pass
        samples.append({"sample_key": sample.sample_key, "filename": meta.get("filenames", {}).get(sample.sample_key, sample.sample_key),
                        "preview_url": preview, **({"class_id": meta.get("labels_by_sample_key", {}).get(sample.sample_key)} if task.has_gt else {})})
    models = []
    for link in db.query(TaskModel).filter_by(task_id=task.id).order_by(TaskModel.sort_order).all():
        mv = db.get(ModelVersion, link.model_version_id)
        parent = db.get(Model, mv.model_id) if mv else None
        models.append({"model_version_id": link.model_version_id, "slug": mv.slug if mv else None,
                       "name": parent.name if parent else "模型不可用", "status": link.status,
                       "fail_stage": link.fail_stage, "fail_message": link.fail_message})
    return {"id": task.id, "type": "classification", "task_kind": "classification", "scene": "steel",
            "type_label": "钢铁缺陷分类", "status": task.status, "has_gt": task.has_gt, "n": len(samples),
            "error_summary": task.error_summary, "created_at": task.created_at.isoformat(),
            "classes": meta.get("classes", []), "models": models, "samples": samples, "predictions": predictions,
            "metrics": serialize_classification_metrics(task), "result_download_url": download,
            "protocol_hash": meta.get("protocol_hash"), "bundle_ready": False,
            "open_path": f"/classification/{task.id}", "disclaimer": "六类均为已知缺陷，不含正常类；softmax 得分不是经过校准的正确概率。"}
