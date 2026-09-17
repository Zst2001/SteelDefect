from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party"), str(ROOT / "apps" / "api")]

from infer.task_io import metrics_response  # noqa: E402


def test_metrics_without_gt_are_unavailable() -> None:
    payload = metrics_response(has_gt=False)
    assert payload == {"available": False}
    blob = str(payload).lower()
    assert "miou" not in blob
    assert "dice" not in blob
    assert "acc" not in blob


def test_metrics_missing_payload_not_zero_filled() -> None:
    payload = metrics_response(has_gt=True, payload=None)
    assert payload == {"available": False}
