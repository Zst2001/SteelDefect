from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.authz import require_advisor
from app.db.models import User
from app.deps import get_db
from app.services.users import create_student, list_users, serialize_user, set_student_status

router = APIRouter(prefix="/admin", tags=["admin"])


class CreateStudentIn(BaseModel):
    username: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_\u4e00-\u9fff-]+$")
    password: str = Field(min_length=8, max_length=128)
    reason: str = Field(default="开通学生账号", max_length=200)


class UserStatusIn(BaseModel):
    status: str = Field(pattern=r"^(active|disabled)$")
    reason: str = Field(min_length=1, max_length=200)


@router.get("/users")
def get_users(db: Session = Depends(get_db), _advisor: User = Depends(require_advisor)) -> dict:
    return {"items": [serialize_user(row) for row in list_users(db)]}


@router.post("/users")
def post_user(
    body: CreateStudentIn,
    db: Session = Depends(get_db),
    advisor: User = Depends(require_advisor),
) -> dict:
    user = create_student(
        db,
        advisor,
        username=body.username,
        password=body.password,
        reason=body.reason,
    )
    return serialize_user(user)


@router.patch("/users/{user_id}")
def patch_user(
    user_id: str,
    body: UserStatusIn,
    db: Session = Depends(get_db),
    advisor: User = Depends(require_advisor),
) -> dict:
    user = set_student_status(db, advisor, user_id, status=body.status, reason=body.reason)
    return serialize_user(user)
