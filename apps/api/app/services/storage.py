from __future__ import annotations

import hashlib
import re
from pathlib import Path

from app.config import Settings
from app.errors import AppError

SAFE_REL = re.compile(r"^[A-Za-z0-9._/-]+$")


def resolve_uri(uri: str, settings: Settings) -> Path:
    if uri.startswith("asset:"):
        rel = uri[len("asset:") :].lstrip("/").replace("\\", "/")
        path = (settings.repo_root / "assets" / rel).resolve()
        assets = (settings.repo_root / "assets").resolve()
        if assets not in path.parents and path != assets:
            raise AppError("非法资源路径", code="BAD_URI", stage="file", status_code=400)
        return path
    if uri.startswith("data:"):
        rel = uri[len("data:") :].lstrip("/").replace("\\", "/")
        path = (settings.storage_path / rel).resolve()
        root = settings.storage_path.resolve()
        if root not in path.parents and path != root:
            raise AppError("非法存储路径", code="BAD_URI", stage="file", status_code=400)
        return path
    if uri.startswith("neufull:"):
        rel = uri[len("neufull:") :].lstrip("/").replace("\\", "/")
        if ".." in rel.split("/"):
            raise AppError("非法全量 NEU 路径", code="BAD_URI", stage="file", status_code=400)
        root = settings.neu_full_path.resolve()
        path = (root / rel).resolve()
        if root not in path.parents and path != root:
            raise AppError("非法全量 NEU 路径", code="BAD_URI", stage="file", status_code=400)
        return path
    raise AppError("未知资源协议", code="BAD_URI", stage="file", status_code=400)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def safe_rel_path(rel: str) -> str:
    cleaned = rel.replace("\\", "/").lstrip("/")
    if ".." in cleaned.split("/") or not SAFE_REL.match(cleaned):
        raise AppError("非法相对路径", code="BAD_PATH", stage="file", status_code=400)
    return cleaned
