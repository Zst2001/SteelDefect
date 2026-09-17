from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.cache import cache_redis, queue_redis
from admit.dockerutil import docker_available, image_present
from app.config import get_settings
from app.db.session import engine

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    mysql_ok = False
    redis_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        mysql_ok = True
    except Exception:
        mysql_ok = False
    try:
        redis_ok = queue_redis().ping() is True and cache_redis().ping() is True
    except Exception:
        redis_ok = False
    docker_ok = docker_available()
    image_ok = image_present(get_settings().student_image) if docker_ok else False
    status = "ok" if mysql_ok and redis_ok else "degraded"
    return {
        "status": status,
        "mysql": mysql_ok,
        "redis": redis_ok,
        "docker": docker_ok,
        "student_image": image_ok,
    }
