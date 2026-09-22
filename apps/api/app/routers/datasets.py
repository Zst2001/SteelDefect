from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.authz import get_current_user
from app.config import get_settings
from app.db.models import DatasetVersion, Sample, User
from app.deps import get_db
from app.errors import AppError
from app.services.datasets import (
    SAMPLE_PAGE_DEFAULT,
    dataset_detail_payload,
    get_visible_dataset,
    list_dataset_catalog,
    page_samples,
    sample_preview_path,
    summarize_dataset_version,
)
from app.services.storage import resolve_uri

router = APIRouter(prefix="/datasets", tags=["datasets"])

__all__ = ["router", "summarize_dataset_version"]


@router.get("")
def list_datasets(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return list_dataset_catalog(db, user)


@router.get("/{dataset_id}")
def dataset_detail(
    dataset_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    return dataset_detail_payload(db, user, dataset_id)


@router.get("/{dataset_id}/versions/{version_id}/samples")
def list_dataset_samples(
    dataset_id: str,
    version_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(SAMPLE_PAGE_DEFAULT, ge=1, le=48),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return page_samples(db, user, dataset_id, version_id, offset=offset, limit=limit)


@router.get("/{dataset_id}/versions/{version_id}/samples/{sample_key}/preview")
def dataset_sample_preview(
    dataset_id: str,
    version_id: str,
    sample_key: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    path, sample = sample_preview_path(db, user, dataset_id, version_id, sample_key)
    return FileResponse(path, filename=f"{sample.sample_key}{path.suffix.lower() or '.png'}")


@router.get("/{dataset_id}/gt/{sample_key}")
def download_gt(
    dataset_id: str,
    sample_key: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    dataset = get_visible_dataset(db, user, dataset_id)
    version = (
        db.query(DatasetVersion)
        .filter(DatasetVersion.dataset_id == dataset.id, DatasetVersion.is_fixed_test.is_(True))
        .order_by(DatasetVersion.created_at.asc())
        .first()
    )
    if version is None:
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
