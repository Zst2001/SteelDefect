"""Milvus access for the academic specialty.

The assistant may only touch the collection named ippilab. Other names,
including paper_literature, are rejected before a client is constructed.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pymilvus import DataType, MilvusClient

from app.config import Settings

logger = logging.getLogger(__name__)

ALLOWED_COLLECTION = "ippilab"
# 2026-10-16 金标：应命中最低 0.540，应拒答最高 0.431。0.35 会放过「番茄叶片」这类无关问句。
SCORE_MIN = 0.48
SCORE_RESCUE = 0.45
SEARCH_LIMIT = 24
PARENT_LIMIT = 5
_PROPER_NAME = re.compile(r"10\.\d{4,}/\S+|NEU-20|NEU-DET|ResNet|U-Net|YOLO", re.IGNORECASE)


class MilvusCollectionError(Exception):
    """Raised when the configured collection is not the allowed lab collection."""


def collection_name(settings: Settings) -> str:
    name = (settings.milvus_collection_name or "").strip()
    if name != ALLOWED_COLLECTION:
        raise MilvusCollectionError("科研助手只允许集合 ippilab")
    return name


def milvus_configured(settings: Settings) -> bool:
    if not (settings.milvus_uri or "").strip() or not (settings.milvus_token or "").strip():
        return False
    try:
        collection_name(settings)
    except MilvusCollectionError:
        return False
    return True


def connect(settings: Settings) -> tuple[MilvusClient, str]:
    name = collection_name(settings)
    uri = settings.milvus_uri.strip()
    token = settings.milvus_token.strip()
    if not uri or not token:
        raise MilvusCollectionError("未配置 Milvus")
    client = MilvusClient(uri=uri, token=token, timeout=20)
    return client, name


def _vector_dim(desc: dict[str, Any]) -> int | None:
    for field in desc.get("fields") or []:
        if field.get("name") == "vector":
            params = field.get("params") or {}
            dim = params.get("dim")
            return int(dim) if dim is not None else None
    return None


def assert_schema(client: MilvusClient, name: str, settings: Settings) -> None:
    if name != ALLOWED_COLLECTION:
        raise MilvusCollectionError("科研助手只允许集合 ippilab")
    desc = client.describe_collection(name)
    dim = _vector_dim(desc)
    if dim != int(settings.llm_embed_dim):
        raise MilvusCollectionError(f"ippilab 向量维度为 {dim}，需要 {settings.llm_embed_dim}")
    index = client.describe_index(name, "vector")
    metric = str(index.get("metric_type") or "")
    if metric.upper() != "COSINE":
        raise MilvusCollectionError(f"ippilab 度量是 {metric or '未知'}，需要 COSINE")


def ensure_collection(settings: Settings) -> MilvusClient:
    client, name = connect(settings)
    if client.has_collection(name):
        assert_schema(client, name, settings)
        return client
    schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=True)
    schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
    schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=int(settings.llm_embed_dim))
    index_params = client.prepare_index_params()
    index_params.add_index(field_name="vector", index_type="AUTOINDEX", metric_type="COSINE")
    client.create_collection(collection_name=name, schema=schema, index_params=index_params)
    assert_schema(client, name, settings)
    return client


def clear_collection(settings: Settings) -> None:
    client, name = connect(settings)
    if not client.has_collection(name):
        return
    assert_schema(client, name, settings)
    try:
        client.delete(collection_name=name, filter="id >= 0")
    except Exception:
        logger.info("ippilab delete-all skipped", exc_info=True)


def insert_rows(settings: Settings, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    client = ensure_collection(settings)
    name = collection_name(settings)
    written = 0
    for start in range(0, len(rows), 32):
        batch = rows[start : start + 32]
        client.insert(collection_name=name, data=batch)
        written += len(batch)
    flush = getattr(client, "flush", None)
    if callable(flush):
        flush(name)
    return written


def _query_names(query: str) -> list[str]:
    found: list[str] = []
    for match in _PROPER_NAME.finditer(query or ""):
        name = match.group(0)
        if name not in found:
            found.append(name)
    return found


def _name_in_text(names: list[str], text: str) -> bool:
    folded = text.casefold()
    return any(name.casefold() in folded for name in names)


def search_vectors(
    settings: Settings,
    vector: list[float],
    *,
    limit: int = SEARCH_LIMIT,
    query: str = "",
) -> list[dict[str, Any]] | None:
    """Search ippilab. None means the collection is missing or empty (caller may fall back)."""
    client, name = connect(settings)
    if not client.has_collection(name):
        return None
    assert_schema(client, name, settings)
    stats = client.get_collection_stats(name)
    if int(stats.get("row_count") or 0) <= 0:
        return None
    if len(vector) != int(settings.llm_embed_dim):
        raise MilvusCollectionError("查询向量维度与 ippilab 不一致")
    raw = client.search(
        collection_name=name,
        data=[vector],
        anns_field="vector",
        search_params={"metric_type": "COSINE"},
        limit=limit,
        output_fields=[
            "text",
            "parent_text",
            "parent_id",
            "file_name",
            "section_path",
            "source_label",
            "category",
            "slug",
            "chunk_level",
            "block_type",
        ],
    )
    names = _query_names(query)
    hits = raw[0] if raw else []
    out: list[dict[str, Any]] = []
    for item in hits:
        entity = item.get("entity") if isinstance(item, dict) else {}
        entity = entity or {}
        score = item.get("distance") if isinstance(item, dict) else None
        if score is None or float(score) < SCORE_RESCUE:
            continue
        parent = str(entity.get("parent_text") or entity.get("text") or "").strip()
        if not parent:
            continue
        if float(score) < SCORE_MIN and not _name_in_text(names, parent):
            continue
        title = str(entity.get("section_path") or entity.get("file_name") or "审定语料")
        out.append(
            {
                "id": str(entity.get("parent_id") or item.get("id")),
                "slug": entity.get("slug"),
                "file_id": entity.get("slug"),
                "file_name": entity.get("file_name") or "",
                "block_type": entity.get("block_type") or "",
                "title": title,
                "category": entity.get("category") or "kb",
                "source": str(entity.get("source_label") or "实验室知识库"),
                "excerpt": parent[:2000],
                "score": float(score),
                "via": "milvus",
                "parent_id": str(entity.get("parent_id") or item.get("id")),
            }
        )
    return _diversify(_dedupe_parents(out))


def _dedupe_parents(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for hit in hits:
        key = str(hit.get("parent_id") or hit.get("id"))
        current = best.get(key)
        if current is None or float(hit.get("score") or 0) > float(current.get("score") or 0):
            best[key] = hit
    ranked = sorted(best.values(), key=lambda item: float(item.get("score") or 0), reverse=True)
    return ranked


def _diversify(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(hits, key=lambda item: float(item.get("score") or 0), reverse=True)
    picked: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for hit in ranked:
        group = (str(hit.get("file_name") or ""), str(hit.get("block_type") or ""))
        if group in seen:
            deferred.append(hit)
            continue
        seen.add(group)
        picked.append(hit)
        if len(picked) >= PARENT_LIMIT:
            return picked
    for hit in deferred:
        if len(picked) >= PARENT_LIMIT:
            break
        picked.append(hit)
    return picked
