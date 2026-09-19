from __future__ import annotations

from collections import defaultdict

from app.cache import cache_redis
from app.config import Settings, get_settings
from app.errors import AppError
from app.services.demo_identity import DemoIdentity

QUOTA_MESSAGE = "今日公开演示次数已用完，请明日再试或登录"
SUBMIT_MESSAGE = "请求过于频繁，请稍后再试或登录"

RESERVE_LUA = """
local ip_key = KEYS[1]
local sid_key = KEYS[2]
local cutoff = tonumber(ARGV[1])
local now = tonumber(ARGV[2])
local member = ARGV[3]
local limit = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])
redis.call('ZREMRANGEBYSCORE', ip_key, '-inf', cutoff)
redis.call('ZREMRANGEBYSCORE', sid_key, '-inf', cutoff)
if redis.call('ZCARD', ip_key) >= limit or redis.call('ZCARD', sid_key) >= limit then
  return 0
end
redis.call('ZADD', ip_key, now, member)
redis.call('ZADD', sid_key, now, member)
redis.call('EXPIRE', ip_key, ttl)
redis.call('EXPIRE', sid_key, ttl)
return 1
"""


def demo_ip_key(ip_hash: str) -> str:
    return f"lab:demo:ip:{ip_hash}"


def demo_sid_key(sid: str) -> str:
    return f"lab:demo:sid:{sid}"


def demo_submit_key(ip_hash: str) -> str:
    return f"lab:demo:submit:{ip_hash}"


class MemoryQuotaStore:
    """In-memory ZSET used by tests. Same rolling-window rules as Redis."""

    def __init__(self) -> None:
        self.zsets: dict[str, dict[str, float]] = defaultdict(dict)
        self.counters: dict[str, int] = {}

    def _trim(self, key: str, cutoff: float) -> None:
        self.zsets[key] = {member: score for member, score in self.zsets[key].items() if score > cutoff}

    def reserve(self, ip_hash: str, sid: str, task_id: str, *, now: float, window: int, limit: int) -> bool:
        cutoff = now - window
        ip_key = demo_ip_key(ip_hash)
        sid_key = demo_sid_key(sid)
        self._trim(ip_key, cutoff)
        self._trim(sid_key, cutoff)
        if len(self.zsets[ip_key]) >= limit or len(self.zsets[sid_key]) >= limit:
            return False
        self.zsets[ip_key][task_id] = now
        self.zsets[sid_key][task_id] = now
        return True

    def release(self, ip_hash: str, sid: str, task_id: str) -> None:
        self.zsets[demo_ip_key(ip_hash)].pop(task_id, None)
        self.zsets[demo_sid_key(sid)].pop(task_id, None)

    def incr_submit(self, ip_hash: str, window: int = 3600) -> int:
        key = demo_submit_key(ip_hash)
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]


class RedisQuotaStore:
    def __init__(self, client=None) -> None:
        self.client = client

    def _redis(self):
        return self.client if self.client is not None else cache_redis()

    def reserve(self, ip_hash: str, sid: str, task_id: str, *, now: float, window: int, limit: int) -> bool:
        cutoff = now - window
        ttl = max(window * 2, window + 60)
        result = self._redis().eval(
            RESERVE_LUA,
            2,
            demo_ip_key(ip_hash),
            demo_sid_key(sid),
            cutoff,
            now,
            task_id,
            limit,
            ttl,
        )
        return int(result) == 1

    def release(self, ip_hash: str, sid: str, task_id: str) -> None:
        redis = self._redis()
        redis.zrem(demo_ip_key(ip_hash), task_id)
        redis.zrem(demo_sid_key(sid), task_id)

    def incr_submit(self, ip_hash: str, window: int) -> int:
        redis = self._redis()
        key = demo_submit_key(ip_hash)
        count = int(redis.incr(key))
        if count == 1:
            redis.expire(key, window)
        return count


_store = None


def get_quota_store():
    global _store
    if _store is None:
        _store = RedisQuotaStore()
    return _store


def set_quota_store(store) -> None:
    global _store
    _store = store


def _now() -> float:
    from time import time

    return time()


def assert_demo_submit_rate(identity: DemoIdentity, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    count = get_quota_store().incr_submit(identity.ip_hash, settings.demo_submit_window_sec)
    if count > settings.demo_submit_max:
        raise AppError(SUBMIT_MESSAGE, code="DEMO_SUBMIT_RATE", stage="quota", status_code=429)


def reserve_guest_quota(identity: DemoIdentity, task_id: str, settings: Settings | None = None) -> bool:
    if identity.logged_in:
        return True
    settings = settings or get_settings()
    return get_quota_store().reserve(
        identity.ip_hash,
        identity.sid,
        task_id,
        now=_now(),
        window=settings.demo_quota_window_sec,
        limit=settings.demo_quota_limit,
    )


def release_guest_quota(identity: DemoIdentity, task_id: str) -> None:
    if identity.logged_in:
        return
    get_quota_store().release(identity.ip_hash, identity.sid, task_id)


def raise_demo_quota() -> None:
    raise AppError(QUOTA_MESSAGE, code="DEMO_QUOTA", stage="quota", status_code=429)
