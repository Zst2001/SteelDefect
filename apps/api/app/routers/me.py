from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.authz import get_current_user
from app.cache import cache_get_json, cache_set_json, dash_key
from app.config import get_settings
from app.db.models import User
from app.deps import get_db
from app.services.dashboard import build_dashboard

router = APIRouter(tags=["me"])


@router.get("/me/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    settings = get_settings()
    key = dash_key(user.id)
    cached = cache_get_json(key)
    if cached is not None:
        return cached
    payload = build_dashboard(db, user)
    cache_set_json(key, payload, settings.cache_task_ttl_sec)
    return payload
