from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.authz import get_current_user
from app.config import get_settings
from app.db.models import Dataset, DatasetVersion, PreprocessSpecRow, Sample, User
from app.deps import get_db
from app.errors import AppError
from app.util_time import new_id
from app.services.input_freeze import lock_version, assert_unreferenced, current_samples
from infer.masks import MaskError, decode_mask_bytes, encode_index_png, looks_like_label_map, validate_label_mask

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
ALLOWED_MASK_EXT = ALLOWED_EXT | {".bmp"}

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("/images")
async def upload_images(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    settings = get_settings()
    if not files:
        raise AppError("请至少上传 1 张图片", code="EMPTY_UPLOAD", stage="file", status_code=400)
    if len(files) > settings.max_upload_images:
        raise AppError(
            f"快速对比最多 {settings.max_upload_images} 张",
            code="TOO_MANY_IMAGES",
            stage="file",
            status_code=400,
        )
    preprocess = db.query(PreprocessSpecRow).filter(PreprocessSpecRow.name == "neu_200").one()
    dataset = Dataset(
        id=new_id(),
        owner_id=user.id,
        name=f"upload-{user.username}",
        visibility="private",
    )
    version = DatasetVersion(
        id=new_id(),
        dataset_id=dataset.id,
        kind="upload_batch",
        class_map_json={"0": "背景", "1": "夹渣", "2": "斑块", "3": "划痕"},
        preprocess_id=preprocess.id,
        is_fixed_test=False,
        forbid_student_gt_download=False,
    )
    db.add(dataset)
    db.add(version)
    db.flush()

    used_keys: set[str] = set()
    samples: list[dict] = []
    dest_root = settings.storage_path / "uploads" / version.id
    dest_root.mkdir(parents=True, exist_ok=True)

    for upload in files:
        filename = Path(upload.filename or "image.png")
        ext = filename.suffix.lower()
        if ext not in ALLOWED_EXT:
            raise AppError(f"不支持的文件类型: {ext}", code="BAD_TYPE", stage="file", status_code=400)
        data = await upload.read()
        if not data:
            raise AppError(f"{filename.name} 为空文件", code="EMPTY_FILE", stage="file", status_code=400)
        if len(data) > settings.max_image_bytes:
            raise AppError(f"{filename.name} 超过单文件大小上限", code="FILE_TOO_LARGE", stage="file", status_code=400)
        key = filename.stem
        original = key
        suffix = 1
        while key in used_keys:
            key = f"{original}_{suffix}"
            suffix += 1
        used_keys.add(key)
        stored = dest_root / f"{key}{ext}"
        stored.write_bytes(data)
        image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise AppError(f"{filename.name} 无法作为图片读取", code="UNREADABLE", stage="file", status_code=400)
        if looks_like_label_map(image):
            raise AppError(
                f"{filename.name} 看起来是类别掩码（像素只有 0–3），不是钢表面原图。请把 JPG 原图放到「原图」，PNG 掩码放到「配对掩码」。",
                code="MASK_AS_IMAGE",
                stage="file",
                status_code=400,
            )
        height, width = image.shape[:2]
        digest = hashlib.sha256(data).hexdigest()
        sample = Sample(
            id=new_id(),
            version_id=version.id,
            sample_key=key,
            origin_uri=f"data:uploads/{version.id}/{stored.name}",
            mask_uri=None,
            width=width,
            height=height,
            sha256=digest,
        )
        db.add(sample)
        samples.append({"id": sample.id, "sample_key": key, "width": width, "height": height})

    db.commit()
    return {"batch_id": version.id, "has_gt": False, "samples": samples, "preprocess_id": preprocess.id}


def _mask_num_classes(version: DatasetVersion) -> int:
    class_map = version.class_map_json or {}
    return max(len(class_map), 4)


@router.post("/masks")
async def upload_masks(
    batch_id: str = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    settings = get_settings()
    if not files:
        raise AppError("请至少上传 1 张掩码", code="EMPTY_UPLOAD", stage="file", status_code=400)
    if len(files) > settings.max_upload_images:
        raise AppError(
            f"快速对比最多 {settings.max_upload_images} 张掩码",
            code="TOO_MANY_IMAGES",
            stage="file",
            status_code=400,
        )
    version = lock_version(db, batch_id)
    if version is None:
        raise AppError("上传批次不存在", code="BATCH_NOT_FOUND", stage="file", status_code=404)
    dataset = db.get(Dataset, version.dataset_id)
    if dataset is None:
        raise AppError("数据集不存在", code="NOT_FOUND", stage="file", status_code=404)
    if dataset.visibility == "private" and dataset.owner_id != user.id and user.role != "advisor":
        raise AppError("无权给该批次补掩码", code="FORBIDDEN", stage="auth", status_code=403)
    if version.kind != "upload_batch" or version.is_fixed_test or version.forbid_student_gt_download:
        raise AppError(
            "只能给自己上传的对比批次补掩码，不能改固定测试集",
            code="MASK_PRESET_FORBIDDEN",
            stage="auth",
            status_code=403,
        )

    assert_unreferenced(db, version)
    samples = current_samples(db, version.id)
    by_key = {sample.sample_key: sample for sample in samples}
    if not by_key:
        raise AppError("该批次没有图片，请先上传原图", code="NO_SAMPLES", stage="file", status_code=400)

    num_classes = _mask_num_classes(version)
    dest_root = settings.storage_path / "uploads" / version.id / "masks"
    dest_root.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    decoded: list[tuple[Sample, np.ndarray]] = []
    extras: list[str] = []
    for upload in files:
        filename = Path(upload.filename or "mask.png")
        ext = filename.suffix.lower()
        if ext not in ALLOWED_MASK_EXT:
            raise AppError(f"不支持的掩码类型: {ext}", code="BAD_TYPE", stage="file", status_code=400)
        data = await upload.read()
        if not data:
            raise AppError(f"{filename.name} 为空文件", code="EMPTY_FILE", stage="file", status_code=400)
        if len(data) > settings.max_image_bytes:
            raise AppError(f"{filename.name} 超过单文件大小上限", code="FILE_TOO_LARGE", stage="file", status_code=400)
        key = filename.stem
        if key in seen:
            raise AppError(f"掩码文件名重复: {key}", code="DUP_MASK", stage="file", status_code=400)
        seen.add(key)
        sample = by_key.get(key)
        if sample is None:
            extras.append(filename.name)
            continue
        try:
            labels = decode_mask_bytes(data)
            labels = validate_label_mask(
                labels,
                height=sample.height,
                width=sample.width,
                num_classes=num_classes,
            )
        except MaskError as exc:
            raise AppError(f"{filename.name} {exc}", code=exc.code, stage="file", status_code=400) from exc
        decoded.append((sample, labels))

    if extras:
        raise AppError(
            "这些掩码无法按文件名主名配对到本批图片: " + ", ".join(extras),
            code="MASK_UNPAIRED",
            stage="file",
            status_code=400,
        )
    if not decoded:
        raise AppError("没有配对成功的掩码", code="MASK_UNPAIRED", stage="file", status_code=400)

    paired = []
    for sample, labels in decoded:
        content = encode_index_png(labels)
        stored = dest_root / f"{new_id()}.png"
        with stored.open("xb") as handle:
            handle.write(content)
        sample.mask_uri = f"data:uploads/{version.id}/masks/{stored.name}"
        paired.append({"id": sample.id, "sample_key": sample.sample_key, "has_mask": True})

    db.commit()
    refreshed = db.query(Sample).filter(Sample.version_id == version.id).order_by(Sample.sample_key.asc()).all()
    missing = [s.sample_key for s in refreshed if not s.mask_uri]
    has_gt = not missing
    return {
        "batch_id": version.id,
        "has_gt": has_gt,
        "paired": paired,
        "missing_masks": missing,
        "samples": [
            {"id": s.id, "sample_key": s.sample_key, "width": s.width, "height": s.height, "has_mask": s.mask_uri is not None}
            for s in refreshed
        ],
    }
