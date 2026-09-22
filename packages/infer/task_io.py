from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence


TASK_DIR_NAMES = (
    "origin",
    "gt",
    "pred",
    "overlay",
    "boundary",
    "error",
    "cam",
    "montage",
)


def task_root(storage_root: Path, task_id: str) -> Path:
    return Path(storage_root) / "tasks" / task_id


def prepare_task_dirs(storage_root: Path, task_id: str) -> Path:
    root = task_root(storage_root, task_id)
    for name in TASK_DIR_NAMES:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_task_json(task_dir: Path, payload: dict[str, Any]) -> None:
    if not payload.get("has_gt", False):
        payload = dict(payload)
        payload.pop("metrics", None)
    write_json(task_dir / "task.json", payload)


def metrics_response(*, has_gt: bool, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Never invent zeros. No-GT responses omit accuracy fields."""
    if not has_gt:
        return {"available": False}
    if not payload:
        return {"available": False}
    return {"available": True, **payload}


def select_preview_keys(sample_keys: Sequence[str], limit: int) -> list[str]:
    """Deterministic montage sample: sorted keys, then the first `limit`."""
    ordered = sorted(str(key) for key in sample_keys)
    if limit <= 0 or len(ordered) <= limit:
        return ordered
    return ordered[:limit]


def check_drawio_bundle_names(names: Sequence[str]) -> None:
    """Bundle is PNG layers + task.json for Draw.io. gt/ and error/ are allowed. No PDF, no metrics.json."""
    lowered = [name.replace("\\", "/").lower() for name in names]
    if "task.json" not in lowered:
        raise ValueError("bundle missing task.json")
    if not any(name.startswith("montage/") for name in lowered):
        raise ValueError("bundle missing montage layers")
    if not any(name.startswith("origin/") for name in lowered):
        raise ValueError("bundle missing origin layers")
    if any(name.endswith(".pdf") for name in lowered):
        raise ValueError("bundle must not contain PDF")
    if any(name.endswith("metrics.json") for name in lowered):
        raise ValueError("bundle must not contain metrics.json")
