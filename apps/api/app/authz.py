from __future__ import annotations

from datetime import timedelta

from fastapi import Cookie, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Session as AuthSession
from app.db.models import User
from app.deps import get_db
from app.errors import AppError
from app.util_time import utcnow


def get_optional_user(
    db: Session = Depends(get_db),
    lab_session: str | None = Cookie(default=None, alias="lab_session"),
) -> User | None:
    if not lab_session:
        return None
    row = db.get(AuthSession, lab_session)
    if row is None or row.expires_at < utcnow():
        return None
    user = db.get(User, row.user_id)
    if user is None or user.status != "active":
        return None
    return user


def get_current_user(
    db: Session = Depends(get_db),
    lab_session: str | None = Cookie(default=None, alias="lab_session"),
) -> User:
    settings = get_settings()
    token = lab_session
    if not token:
        raise AppError("未登录", code="UNAUTHENTICATED", stage="auth", status_code=401)
    row = db.get(AuthSession, token)
    if row is None or row.expires_at < utcnow():
        raise AppError("会话已失效", code="SESSION_EXPIRED", stage="auth", status_code=401)
    user = db.get(User, row.user_id)
    if user is None or user.status != "active":
        raise AppError("账号不可用", code="USER_DISABLED", stage="auth", status_code=403)
    row.expires_at = utcnow() + timedelta(hours=settings.session_hours)
    db.add(row)
    db.commit()
    return user


def require_advisor(user: User = Depends(get_current_user)) -> User:
    if user.role != "advisor":
        raise AppError("需要导师权限", code="FORBIDDEN", stage="auth", status_code=403)
    return user
