from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from app.authz import get_current_user
from app.cache import cache_get_json, cache_set_json, invalidate_after_write, models_list_key
from app.config import get_settings
from app.db.models import Model, ModelVersion, User
from app.deps import get_db
from app.errors import AppError
from app.services.import_model import import_student_model, model_dir
from app.services.models import can_view_version, group_model_items, list_visible_versions, serialize_version

router = APIRouter(prefix="/models", tags=["models"])


def _load_version(db: Session, version_id: str) -> ModelVersion | None:
    version = (
        db.query(ModelVersion)
        .options(selectinload(ModelVersion.model), selectinload(ModelVersion.weights))
        .filter(ModelVersion.id == version_id)
        .one_or_none()
    )
    if version is not None:
        return version
    model = db.get(Model, version_id)
    if model is None:
        return None
    return (
        db.query(ModelVersion)
        .options(selectinload(ModelVersion.model), selectinload(ModelVersion.weights))
        .filter(ModelVersion.model_id == model.id)
        .order_by(ModelVersion.created_at.desc())
        .first()
    )


def _visible_version(db: Session, version_id: str, user: User) -> ModelVersion:
    version = _load_version(db, version_id)
    if version is None or not can_view_version(user, version.model, version):
        raise AppError("模型不存在", code="NOT_FOUND", stage="auth", status_code=404)
    return version


@router.get("")
def list_models(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    settings = get_settings()
    key = models_list_key(user.id)
    cached = cache_get_json(key)
    if cached is not None:
        return cached
    items = list_visible_versions(db, user)
    payload = group_model_items(items, user.id)
    cache_set_json(key, payload, settings.cache_models_ttl_sec)
    return payload


@router.post("/import")
async def import_model(
    name: str = Form(...),
    entry_symbol: str = Form("build_model"),
    num_classes: int = Form(4),
    in_channels: int = Form(3),
    requires_cuda: bool = Form(False),
    py_file: UploadFile = File(...),
    pth_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    version = await import_student_model(
        db,
        user,
        name=name,
        entry_symbol=entry_symbol,
        num_classes=num_classes,
        in_channels=in_channels,
        requires_cuda=requires_cuda,
        py_file=py_file,
        pth_file=pth_file,
    )
    loaded = _visible_version(db, version.id, user)
    return serialize_version(db, loaded, loaded.model, include_report=True)


class VisibilityIn(BaseModel):
    visibility: str = Field(pattern="^(private|shared)$")


@router.patch("/{version_id}/visibility")
def set_visibility(
    version_id: str,
    body: VisibilityIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if user.role != "advisor":
        raise AppError("仅导师可将模型设为课题组共享", code="FORBIDDEN", stage="auth", status_code=403)
    version = _visible_version(db, version_id, user)
    if version.model.source != "student":
        raise AppError("内置模型不可改可见性", code="BUILTIN_LOCKED", stage="auth", status_code=400)
    version.visibility = body.visibility
    db.commit()
    invalidate_after_write(None, version.model.owner_id)
    invalidate_after_write(None, user.id)
    return serialize_version(db, version, version.model, include_report=True)


@router.get("/{version_id}/admit-log")
def download_admit_log(
    version_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    version = _visible_version(db, version_id, user)
    path = model_dir(get_settings(), version.id) / "admit.log"
    if not path.is_file():
        raise AppError("还没有检查日志", code="LOG_MISSING", stage="file", status_code=404)
    return FileResponse(path, filename=f"{version.id}_admit.log", media_type="text/plain")


@router.get("/{version_id}")
def get_model(version_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    version = _visible_version(db, version_id, user)
    return serialize_version(db, version, version.model, include_report=True)
