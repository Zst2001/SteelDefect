from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload

from app.authz import get_current_user
from app.db.models import Dataset, DatasetVersion, Sample, User
from app.deps import get_db
from app.errors import AppError
from app.services.storage import resolve_uri
from app.config import get_settings
from fastapi.responses import FileResponse

router = APIRouter(prefix="/datasets", tags=["datasets"])


def summarize_dataset_version(version: DatasetVersion, samples: list[Sample]) -> dict:
    has_gt = bool(samples) and all(sample.mask_uri for sample in samples)
    eval_ready = version.kind == "preset" and bool(version.is_fixed_test) and has_gt
    return {
        "id": version.id,
        "kind": version.kind,
        "is_fixed_test": version.is_fixed_test,
        "forbid_student_gt_download": version.forbid_student_gt_download,
        "sample_count": len(samples),
        "has_gt": has_gt,
        "eval_ready": eval_ready,
    }


@router.get("")
def list_datasets(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    rows = db.query(Dataset).all()
    items = []
    for dataset in rows:
        if dataset.visibility == "preset" or dataset.owner_id == user.id or user.role == "advisor":
            versions = db.query(DatasetVersion).filter(DatasetVersion.dataset_id == dataset.id).all()
            version_payload = []
            for version in versions:
                samples = db.query(Sample).filter(Sample.version_id == version.id).all()
                version_payload.append(summarize_dataset_version(version, samples))
            items.append(
                {
                    "id": dataset.id,
                    "name": dataset.name,
                    "visibility": dataset.visibility,
                    "owner_id": dataset.owner_id,
                    "eval_ready": any(row["eval_ready"] for row in version_payload),
                    "versions": version_payload,
                }
            )
    return {"items": items}


@router.get("/{dataset_id}")
def dataset_detail(
    dataset_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise AppError("数据集不存在", code="NOT_FOUND", stage="file", status_code=404)
    if dataset.visibility == "private" and dataset.owner_id != user.id and user.role != "advisor":
        raise AppError("无权查看该数据集", code="FORBIDDEN", stage="auth", status_code=403)
    versions = (
        db.query(DatasetVersion)
        .options(selectinload(DatasetVersion.samples))
        .filter(DatasetVersion.dataset_id == dataset.id)
        .all()
    )
    version_payload = []
    for version in versions:
        samples = []
        for sample in version.samples:
            item = {
                "id": sample.id,
                "sample_key": sample.sample_key,
                "width": sample.width,
                "height": sample.height,
                "has_mask": sample.mask_uri is not None,
            }
            if version.forbid_student_gt_download and user.role == "student":
                item["mask_download"] = False
            samples.append(item)
        summary = summarize_dataset_version(version, list(version.samples))
        summary["samples"] = samples
        version_payload.append(summary)
    return {
        "id": dataset.id,
        "name": dataset.name,
        "visibility": dataset.visibility,
        "eval_ready": any(row["eval_ready"] for row in version_payload),
        "versions": version_payload,
    }


@router.get("/{dataset_id}/gt/{sample_key}")
def download_gt(
    dataset_id: str,
    sample_key: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise AppError("数据集不存在", code="NOT_FOUND", stage="file", status_code=404)
    version = (
        db.query(DatasetVersion)
        .filter(DatasetVersion.dataset_id == dataset.id)
        .order_by(DatasetVersion.created_at.asc())
        .first()
    )
    if version is None:
        raise AppError("没有数据版本", code="NOT_FOUND", stage="file", status_code=404)
    if version.forbid_student_gt_download and user.role != "advisor":
        raise AppError(
            "固定测试集的 GT 不对普通学生提供下载",
            code="GT_FORBIDDEN",
            stage="auth",
            status_code=403,
        )
    sample = (
        db.query(Sample)
        .filter(Sample.version_id == version.id, Sample.sample_key == sample_key)
        .one_or_none()
    )
    if sample is None or not sample.mask_uri:
        raise AppError("没有对应掩码", code="NO_MASK", stage="file", status_code=404)
    path = resolve_uri(sample.mask_uri, get_settings())
    return FileResponse(path)
