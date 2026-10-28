from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps import get_db
from app.errors import AppError
from app.services.demo import (
    create_demo_task,
    get_demo_sample,
    get_visible_demo_task,
    list_demo_catalog,
    list_demo_models,
    serialize_demo_task,
)
from app.services.demo_identity import DemoIdentity, get_demo_identity
from app.services.demo_quota import assert_demo_submit_rate
from app.services.storage import resolve_uri
from app.services.task_artifacts import TaskArtifacts

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoTaskIn(BaseModel):
    sample_keys: list[str] = Field(min_length=1, max_length=5)
    baseline_version_ids: list[str] = Field(min_length=1, max_length=3)


@router.get("/samples")
def demo_samples(
    db: Session = Depends(get_db),
    _identity: DemoIdentity = Depends(get_demo_identity),
) -> dict:
    return list_demo_catalog(db)


@router.get("/samples/{sample_key}/preview")
def demo_sample_preview(
    sample_key: str,
    db: Session = Depends(get_db),
    _identity: DemoIdentity = Depends(get_demo_identity),
):
    sample = get_demo_sample(db, sample_key)
    path = resolve_uri(sample.origin_uri, get_settings())
    if not path.is_file():
        raise AppError("预备样例文件缺失", code="SAMPLE_FILE_MISSING", stage="file", status_code=404)
    return FileResponse(path, filename=f"{sample.sample_key}{path.suffix.lower() or '.png'}")


@router.get("/models")
def demo_models(
    db: Session = Depends(get_db),
    _identity: DemoIdentity = Depends(get_demo_identity),
) -> dict:
    return list_demo_models(db)


@router.post("/tasks")
def create_demo(
    body: DemoTaskIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> dict:
    assert_demo_submit_rate(identity)
    task = create_demo_task(
        db,
        identity,
        sample_keys=body.sample_keys,
        idempotency_key=idempotency_key,
        baseline_version_ids=body.baseline_version_ids,
    )
    return serialize_demo_task(db, get_visible_demo_task(db, task.id, identity))


@router.get("/tasks/{task_id}")
def get_demo_task(
    task_id: str,
    db: Session = Depends(get_db),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> dict:
    return serialize_demo_task(db, get_visible_demo_task(db, task_id, identity))


@router.get("/tasks/{task_id}/file/{rel_path:path}")
def get_demo_file(
    task_id: str,
    rel_path: str,
    db: Session = Depends(get_db),
    identity: DemoIdentity = Depends(get_demo_identity),
):
    task = get_visible_demo_task(db, task_id, identity)
    path = TaskArtifacts(db, task, get_settings()).file(rel_path)
    return FileResponse(path)


@router.get("/tasks/{task_id}/bundle")
def get_demo_bundle(
    task_id: str,
    db: Session = Depends(get_db),
    identity: DemoIdentity = Depends(get_demo_identity),
):
    task = get_visible_demo_task(db, task_id, identity)
    path = TaskArtifacts(db, task, get_settings()).file("bundle.zip")
    return FileResponse(
        path,
        filename=f"{task.id}_demo.zip",
        media_type="application/zip",
    )
