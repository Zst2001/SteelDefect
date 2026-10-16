from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.authz import get_current_user
from app.db.models import User
from app.deps import get_db
from app.errors import AppError
from app.services.assistant import (
    add_message,
    create_session,
    dispatch_turn,
    get_session,
    iter_add_message,
    list_analyzable_tasks,
    list_sessions,
    serialize_session,
)

router = APIRouter(prefix="/assistant", tags=["assistant"])


class SessionIn(BaseModel):
    specialty: str = "segment"


class TurnIn(BaseModel):
    tool: str = "task.analyze"
    task_id: str | None = None
    question: str | None = Field(default=None, max_length=2000)
    confirm: bool = False
    batch_id: str | None = None
    baseline_version_ids: list[str] = Field(default_factory=list)
    student_version_id: str | None = None
    version_id: str | None = None
    enqueue: bool = False
    snippet: str | None = Field(default=None, max_length=8000)


class MessageIn(BaseModel):
    content: str | None = Field(default=None, max_length=2000)
    tool: str | None = None
    task_id: str | None = None
    question: str | None = Field(default=None, max_length=2000)
    confirm: bool = False
    batch_id: str | None = None
    baseline_version_ids: list[str] = Field(default_factory=list)
    student_version_id: str | None = None
    version_id: str | None = None
    enqueue: bool = False
    snippet: str | None = Field(default=None, max_length=8000)


@router.get("/tasks")
def get_tasks(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return list_analyzable_tasks(db, user)


@router.get("/sessions")
def get_sessions(
    specialty: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return list_sessions(db, user, specialty)


@router.post("/sessions")
def post_session(
    body: SessionIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    specialty = body.specialty if body else "segment"
    return serialize_session(create_session(db, user, specialty=specialty))


@router.get("/sessions/{session_id}")
def get_session_detail(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return serialize_session(get_session(db, session_id, user))


def _message_kwargs(body: MessageIn) -> dict:
    return {
        "content": body.content,
        "tool": body.tool,
        "task_id": body.task_id,
        "question": body.question,
        "confirm": body.confirm,
        "batch_id": body.batch_id,
        "baseline_version_ids": body.baseline_version_ids,
        "student_version_id": body.student_version_id,
        "version_id": body.version_id,
        "enqueue": body.enqueue,
        "snippet": body.snippet,
    }


@router.post("/sessions/{session_id}/messages")
def post_message(
    session_id: str,
    body: MessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return add_message(db, user, session_id, **_message_kwargs(body))


@router.post("/sessions/{session_id}/messages/stream")
async def post_message_stream(
    session_id: str,
    body: MessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    async def events():
        try:
            for event in iter_add_message(db, user, session_id, **_message_kwargs(body)):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)
        except AppError as exc:
            yield f"data: {json.dumps({'type': 'error', **exc.as_dict()}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/turns")
def post_turn(
    session_id: str,
    body: TurnIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return dispatch_turn(
        db,
        user,
        session_id,
        tool=body.tool,
        task_id=body.task_id,
        question=body.question,
        confirm=body.confirm,
        batch_id=body.batch_id,
        baseline_version_ids=body.baseline_version_ids,
        student_version_id=body.student_version_id,
        version_id=body.version_id,
        enqueue=body.enqueue,
        snippet=body.snippet,
    )
