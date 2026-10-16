"""Dense embeddings via Volcengine multimodal embeddings. One text, one vector."""

from __future__ import annotations

import hashlib
import logging

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

EMBED_CACHE_TTL = 600


class EmbeddingError(Exception):
    pass


def _embed_cache_key(text: str, settings: Settings) -> str:
    raw = f"{settings.llm_embed_model}\n{int(settings.llm_embed_dim)}\n{text[:8000]}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"kb:embed:{digest}"


def _cached_vector(key: str, settings: Settings) -> list[float] | None:
    try:
        from app.cache import cache_get_json

        cached = cache_get_json(key)
    except Exception:
        logger.warning("embed cache read failed", exc_info=True)
        return None
    if not isinstance(cached, list) or len(cached) != int(settings.llm_embed_dim):
        return None
    try:
        return [float(item) for item in cached]
    except (TypeError, ValueError):
        return None


def _store_vector(key: str, vector: list[float]) -> None:
    try:
        from app.cache import cache_set_json

        cache_set_json(key, vector, EMBED_CACHE_TTL)
    except Exception:
        logger.warning("embed cache write failed", exc_info=True)


def embed_text(text: str, *, settings: Settings | None = None) -> list[float]:
    settings = settings or get_settings()
    cached = _cached_vector(_embed_cache_key(text, settings), settings)
    if cached is not None:
        return cached
    vector = _embed_remote(text, settings)
    _store_vector(_embed_cache_key(text, settings), vector)
    return vector


def _embed_remote(text: str, settings: Settings) -> list[float]:
    api_key = settings.resolved_llm_api_key
    if not api_key:
        raise EmbeddingError("未配置 LLM_API_KEY")
    base = settings.llm_base_url.rstrip("/")
    url = f"{base}/embeddings/multimodal"
    payload = {
        "model": settings.llm_embed_model,
        "encoding_format": "float",
        "dimensions": int(settings.llm_embed_dim),
        "input": [{"type": "text", "text": text[:8000]}],
    }
    with httpx.Client(timeout=settings.llm_timeout_sec, trust_env=False) as client:
        response = client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
    if response.status_code >= 400:
        logger.warning("embedding HTTP %s: %s", response.status_code, response.text[:200])
        raise EmbeddingError(f"embedding HTTP {response.status_code}")
    data = response.json().get("data")
    if not isinstance(data, dict):
        raise EmbeddingError("embedding 响应不是对象")
    vector = data.get("embedding")
    if not isinstance(vector, list) or len(vector) != int(settings.llm_embed_dim):
        raise EmbeddingError(f"embedding 维度为 {len(vector) if isinstance(vector, list) else '未知'}")
    return [float(item) for item in vector]
