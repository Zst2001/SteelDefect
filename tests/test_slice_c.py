from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party"), str(ROOT / "apps" / "api")]

import pytest  # noqa: E402

from app.services.dashboard import _task_payload  # noqa: E402
from app.services.models import group_model_items  # noqa: E402
from infer.task_io import check_drawio_bundle_names  # noqa: E402


def test_group_models_splits_builtin_mine_shared() -> None:
    items = [
        {"source": "builtin", "owner_id": None, "visibility": "public", "name": "UNet"},
        {"source": "student", "owner_id": "u1", "visibility": "private", "name": "Mine"},
        {"source": "student", "owner_id": "u2", "visibility": "shared", "name": "Shared"},
    ]
    grouped = group_model_items(items, "u1")
    assert [row["name"] for row in grouped["builtins"]] == ["UNet"]
    assert [row["name"] for row in grouped["mine"]] == ["Mine"]
    assert [row["name"] for row in grouped["shared"]] == ["Shared"]


def test_success_alone_does_not_mark_bundle_ready() -> None:
    task = SimpleNamespace(
        id="t1",
        type="compare",
        status="success",
        has_gt=False,
        error_summary=None,
        created_at=datetime(2026, 9, 14),
    )
    payload = _task_payload(task)
    assert payload["bundle_ready"] is False  # No artifact/ZIP evidence supplied.
    assert payload["bundle_unavailable_reason"]
    assert payload["type_label"] == "快速对比"
    assert payload["has_gt"] is False


def test_queued_task_not_bundle_ready() -> None:
    task = SimpleNamespace(
        id="t2",
        type="compare",
        status="queued",
        has_gt=False,
        error_summary=None,
        created_at=datetime(2026, 9, 14),
    )
    assert _task_payload(task)["bundle_ready"] is False


def test_drawio_bundle_requires_layers() -> None:
    check_drawio_bundle_names(["task.json", "montage/a__mask.png", "origin/a.png"])


def test_drawio_bundle_rejects_pdf_and_metrics() -> None:
    names = ["task.json", "montage/a.png", "origin/a.png"]
    with pytest.raises(ValueError, match="PDF"):
        check_drawio_bundle_names([*names, "report.pdf"])
    with pytest.raises(ValueError, match="metrics.json"):
        check_drawio_bundle_names([*names, "metrics.json"])


def test_drawio_bundle_allows_optional_gt_error() -> None:
    check_drawio_bundle_names(
        ["task.json", "montage/a__mask.png", "origin/a.png", "gt/a.png", "error/m/a.png"]
    )
