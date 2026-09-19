from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.authz import get_current_user
from app.config import get_settings
from app.db.models import Session as AuthSession
from app.db.models import User
from app.deps import get_db
from app.errors import AppError
from app.security import verify_password
from app.util_time import new_id, utcnow

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "role_label": "导师" if user.role == "advisor" else "学生",
        "status": user.status,
    }


def _issue_session(db: Session, user: User, response: Response) -> dict:
    settings = get_settings()
    session = AuthSession(
        id=new_id(),
        user_id=user.id,
        expires_at=utcnow() + timedelta(hours=settings.session_hours),
    )
    db.add(session)
    db.commit()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session.id,
        httponly=True,
        samesite="lax",
        max_age=settings.session_hours * 3600,
        path="/",
    )
    return _user_payload(user)


@router.post("/register")
def register() -> dict:
    raise AppError(
        "已关闭公开注册，请联系导师开通学生账号",
        code="REGISTER_DISABLED",
        stage="auth",
        status_code=403,
    )


@router.post("/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)) -> dict:
    user = db.query(User).filter(User.username == body.username).one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise AppError("用户名或密码错误", code="BAD_CREDENTIALS", stage="auth", status_code=401)
    if user.status != "active":
        raise AppError("账号已停用", code="USER_DISABLED", stage="auth", status_code=403)
    return _issue_session(db, user, response)


@router.post("/logout")
def logout(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    settings = get_settings()
    db.query(AuthSession).filter(AuthSession.user_id == user.id).delete()
    db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return _user_payload(user)
