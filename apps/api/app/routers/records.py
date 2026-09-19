from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.authz import get_current_user
from app.db.models import User
from app.deps import get_db
from app.services.demo import get_visible_demo_task, serialize_demo_task
from app.services.demo_identity import DemoIdentity
from app.services.records import (
    list_records,
    patch_record,
    rerun_record,
    serialize_record,
    submit_to_advisor,
    withdraw_from_advisor,
)
from app.services.tasks import serialize_task
from app.util_time import new_id

router = APIRouter(prefix="/records", tags=["records"])


class RecordPatchIn(BaseModel):
    note: str | None = Field(default=None, max_length=255)
    archived: bool | None = None


@router.get("")
def get_records(
    scope: str = "mine",
    type: str | None = None,
    status: str | None = None,
    archived: bool = False,
    inbox_state: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return list_records(
        db,
        user,
        scope=scope,
        type=type,
        status=status,
        archived=archived,
        inbox_state=inbox_state,
        page=page,
        page_size=page_size,
    )


@router.patch("/{task_id}")
def patch_records(
    task_id: str,
    body: RecordPatchIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    task = patch_record(db, user, task_id, note=body.note, archived=body.archived)
    return serialize_record(db, task, user)


@router.post("/{task_id}/submit")
def post_submit(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return serialize_record(db, submit_to_advisor(db, user, task_id), user)


@router.post("/{task_id}/withdraw")
def post_withdraw(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return serialize_record(db, withdraw_from_advisor(db, user, task_id), user)


@router.post("/{task_id}/rerun")
def post_rerun(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    task = rerun_record(db, user, task_id)
    if task.type == "demo":
        identity = DemoIdentity(sid=new_id(), user=user, ip="0.0.0.0", ip_hash="rerun")
        return serialize_demo_task(db, get_visible_demo_task(db, task.id, identity))
    return serialize_task(db, task)
