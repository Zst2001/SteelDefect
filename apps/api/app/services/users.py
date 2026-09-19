from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.db.models import AuditLog, User
from app.db.models import Session as AuthSession
from app.errors import AppError
from app.security import hash_password
from app.util_time import new_id, utcnow

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fff-]+$")
DEFAULT_QUOTA = {"max_upload_images": 50}
CREATE_REASON = "开通学生账号"


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "role_label": "导师" if user.role == "advisor" else "学生",
        "status": user.status,
        "created_at": user.created_at.isoformat() + "Z",
    }


def _write_audit(db: Session, *, actor_id: str, action: str, target_id: str, reason: str) -> None:
    db.add(
        AuditLog(
            id=new_id(),
            actor_id=actor_id,
            action=action,
            target_type="user",
            target_id=target_id,
            reason=reason.strip() or CREATE_REASON,
            created_at=utcnow(),
        )
    )


def list_users(db: Session) -> list[User]:
    return db.query(User).order_by(User.role.asc(), User.username.asc()).all()


def create_student(
    db: Session,
    advisor: User,
    *,
    username: str,
    password: str,
    reason: str = CREATE_REASON,
) -> User:
    name = username.strip()
    if not 2 <= len(name) <= 32 or not USERNAME_PATTERN.fullmatch(name):
        raise AppError("用户名须为 2–32 位中文、字母、数字、下划线或短横线", code="BAD_USERNAME", stage="auth", status_code=400)
    if not 8 <= len(password) <= 128:
        raise AppError("密码至少 8 位", code="BAD_PASSWORD", stage="auth", status_code=400)
    taken = db.query(User).filter(User.username == name).one_or_none()
    if taken:
        raise AppError("用户名已被占用", code="USERNAME_TAKEN", stage="auth", status_code=409)
    user = User(
        id=new_id(),
        username=name,
        password_hash=hash_password(password),
        role="student",
        status="active",
        quota_json=dict(DEFAULT_QUOTA),
        created_at=utcnow(),
    )
    db.add(user)
    db.flush()
    _write_audit(db, actor_id=advisor.id, action="user.create", target_id=user.id, reason=reason)
    db.commit()
    db.refresh(user)
    return user


def set_student_status(
    db: Session,
    advisor: User,
    user_id: str,
    *,
    status: str,
    reason: str,
) -> User:
    if status not in {"active", "disabled"}:
        raise AppError("状态只能是 active 或 disabled", code="BAD_STATUS", stage="auth", status_code=400)
    note = reason.strip()
    if not note:
        raise AppError("启停账号须填写原因", code="REASON_REQUIRED", stage="auth", status_code=400)
    user = db.get(User, user_id)
    if user is None:
        raise AppError("用户不存在", code="NOT_FOUND", stage="auth", status_code=404)
    if user.role != "student":
        raise AppError("只能启停学生账号", code="NOT_STUDENT", stage="auth", status_code=400)
    if user.id == advisor.id:
        raise AppError("不能启停当前账号", code="FORBIDDEN", stage="auth", status_code=403)
    user.status = status
    db.add(user)
    if status == "disabled":
        db.query(AuthSession).filter(AuthSession.user_id == user.id).delete()
    action = "user.enable" if status == "active" else "user.disable"
    _write_audit(db, actor_id=advisor.id, action=action, target_id=user.id, reason=note)
    db.commit()
    db.refresh(user)
    return user
