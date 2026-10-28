from __future__ import annotations

import json
import logging
from functools import wraps
from typing import Any

import redis

from app.config import get_settings

_queue_text = None
_queue_bytes = None
_cache = None
logger = logging.getLogger(__name__)


def optional_cache(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except redis.exceptions.RedisError as exc:
            # Only read-optimization failures. Quota and RQ clients never use this wrapper.
            logger.warning("cache bypass operation=%s error=%s", function.__name__, type(exc).__name__)
            return None
    return wrapped


def queue_redis() -> redis.Redis:
    """Text client for PING / diagnostics (db0)."""
    global _queue_text
    if _queue_text is None:
        _queue_text = redis.Redis.from_url(get_settings().redis_queue_url, decode_responses=True)
    return _queue_text


def rq_connection() -> redis.Redis:
    """Binary Redis client for RQ. decode_responses must stay false."""
    global _queue_bytes
    if _queue_bytes is None:
        _queue_bytes = redis.Redis.from_url(get_settings().redis_queue_url, decode_responses=False)
    return _queue_bytes


def cache_redis() -> redis.Redis:
    global _cache
    if _cache is None:
        _cache = redis.Redis.from_url(get_settings().redis_cache_url, decode_responses=True)
    return _cache


@optional_cache
def cache_get_json(key: str) -> Any | None:
    raw = cache_redis().get(key)
    if not raw:
        return None
    return json.loads(raw)


@optional_cache
def cache_set_json(key: str, value: Any, ttl: int) -> None:
    cache_redis().setex(key, ttl, json.dumps(value, ensure_ascii=False))


@optional_cache
def cache_delete(*keys: str) -> None:
    if not keys:
        return
    cache_redis().delete(*keys)


def task_status_key(task_id: str) -> str:
    return f"lab:task:{task_id}:status"


def dash_key(user_id: str) -> str:
    return f"lab:dash:{user_id}:v3"


def models_list_key(user_id: str) -> str:
    return f"lab:models:list:{user_id}:v4"


@optional_cache
def invalidate_models_lists() -> None:
    client = cache_redis()
    keys = list(client.scan_iter("lab:models:list:*"))
    if keys:
        client.delete(*keys)


def invalidate_after_write(task_id: str | None = None, user_id: str | None = None) -> None:
    keys: list[str] = []
    if task_id:
        keys.append(task_status_key(task_id))
    if user_id:
        keys.append(dash_key(user_id))
        keys.append(models_list_key(user_id))
    cache_delete(*keys)
