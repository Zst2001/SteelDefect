from __future__ import annotations

import hashlib
from dataclasses import dataclass

from fastapi import Cookie, Depends, Request, Response

from app.authz import get_optional_user
from app.config import Settings, get_settings
from app.db.models import User
from app.util_time import new_id


@dataclass(frozen=True)
class DemoIdentity:
    sid: str
    user: User | None
    ip: str
    ip_hash: str

    @property
    def logged_in(self) -> bool:
        return self.user is not None


def client_ip(request: Request, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    peer = request.client.host if request.client and request.client.host else "0.0.0.0"
    if settings.trust_proxy and peer in {"127.0.0.1", "::1"}:
        forwarded = (request.headers.get("x-forwarded-for") or "").strip()
        hops = [item.strip() for item in forwarded.split(",") if item.strip()]
        if hops:
            return hops[-1]
    return peer


def hash_guest_ip(ip: str, secret_key: str) -> str:
    return hashlib.sha256(f"{secret_key}|{ip}".encode("utf-8")).hexdigest()


def issue_demo_sid_cookie(response: Response, sid: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    response.set_cookie(
        key=settings.demo_sid_cookie_name,
        value=sid,
        httponly=True,
        samesite="lax",
        max_age=settings.demo_sid_days * 24 * 3600,
        path="/",
    )


def get_demo_identity(
    request: Request,
    response: Response,
    lab_demo_sid: str | None = Cookie(default=None, alias="lab_demo_sid"),
    user: User | None = Depends(get_optional_user),
) -> DemoIdentity:
    settings = get_settings()
    sid = (lab_demo_sid or "").strip()
    if len(sid) != 36:
        sid = new_id()
        issue_demo_sid_cookie(response, sid, settings)
    ip = client_ip(request, settings)
    return DemoIdentity(
        sid=sid,
        user=user,
        ip=ip,
        ip_hash=hash_guest_ip(ip, settings.secret_key),
    )
