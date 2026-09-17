from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.authz import get_current_user
from app.config import get_settings
from app.db.models import User
from app.deps import get_db
from app.errors import AppError
from app.services.storage import safe_rel_path
from app.services.tasks import (
    create_compare_task,
    create_eval_task,
    get_visible_task,
    serialize_metrics,
    serialize_task,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


class CompareIn(BaseModel):
    batch_id: str
    baseline_version_ids: list[str] = Field(min_length=1, max_length=3)
    student_version_id: str | None = None


class EvalIn(BaseModel):
    dataset_version_id: str
    baseline_version_ids: list[str] = Field(min_length=1, max_length=3)
    student_version_id: str | None = None


@router.post("/compare")
def create_compare(body: CompareIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    task = create_compare_task(
        db,
        user,
        batch_id=body.batch_id,
        baseline_version_ids=body.baseline_version_ids,
        student_version_id=body.student_version_id,
    )
    return serialize_task(db, get_visible_task(db, task.id, user))


@router.post("/eval")
def create_eval(body: EvalIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    task = create_eval_task(
        db,
        user,
        dataset_version_id=body.dataset_version_id,
        baseline_version_ids=body.baseline_version_ids,
        student_version_id=body.student_version_id,
    )
    return serialize_task(db, get_visible_task(db, task.id, user))


@router.get("/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    task = get_visible_task(db, task_id, user)
    return serialize_task(db, task)


@router.get("/{task_id}/metrics")
def get_metrics(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    task = get_visible_task(db, task_id, user)
    return serialize_metrics(task)


@router.get("/{task_id}/samples/{sample_key}/view")
def sample_view(
    task_id: str,
    sample_key: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    task = get_visible_task(db, task_id, user)
    payload = serialize_task(db, task)
    arts = [a for a in payload["artifacts"] if a["sample_key"] == sample_key]
    return {"task_id": task.id, "sample_key": sample_key, "has_gt": task.has_gt, "artifacts": arts}


@router.get("/{task_id}/file/{rel_path:path}")
def get_file(
    task_id: str,
    rel_path: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = get_visible_task(db, task_id, user)
    cleaned = safe_rel_path(rel_path)
    root = (get_settings().storage_path / "tasks" / task.id).resolve()
    path = (root / cleaned).resolve()
    if root not in path.parents and path != root:
        raise AppError("非法路径", code="BAD_PATH", stage="file", status_code=400)
    if not path.is_file():
        raise AppError("文件不存在", code="NOT_FOUND", stage="file", status_code=404)
    return FileResponse(path)


@router.get("/{task_id}/bundle")
def get_bundle(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = get_visible_task(db, task_id, user)
    path = get_settings().storage_path / "tasks" / task.id / "bundle.zip"
    if not path.is_file():
        raise AppError("打包文件尚未生成", code="BUNDLE_MISSING", stage="file", status_code=404)
    return FileResponse(
        path,
        filename=f"{task.id}_drawio.zip",
        media_type="application/zip",
    )
