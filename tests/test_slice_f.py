from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party"), str(ROOT / "apps" / "api")]

import numpy as np
import pytest
from app.errors import AppError
from app.routers.datasets import summarize_dataset_version
from app.services.dashboard import _task_payload
from app.services.tasks import (
    _assert_baseline_count,
    assert_eval_samples,
    assert_eval_version,
    serialize_metrics,
)
from infer.metrics import (
    add_to_confmat,
    build_metric_payload,
    empty_confmat,
    metrics_dict_from_confmat,
)
from infer.spec import (
    COMPARE_BASELINE_LIMIT,
    EVAL_BASELINE_LIMIT,
    OFFICIAL_SPLIT_DISCLAIMER,
    OFFICIAL_SPLIT_SCOPE,
)
from infer.task_io import select_preview_keys


def test_preview_keys_are_sorted_first_n() -> None:
    keys = [f"{i:06d}" for i in range(20, 0, -1)]
    assert select_preview_keys(keys, 8) == [f"{i:06d}" for i in range(1, 9)]
    assert select_preview_keys(keys, 0) == [f"{i:06d}" for i in range(1, 21)]
    assert select_preview_keys(["a", "b"], 8) == ["a", "b"]


def test_eval_allows_all_builtins_compare_still_caps_at_three() -> None:
    ids = [f"m{i}" for i in range(EVAL_BASELINE_LIMIT)]
    _assert_baseline_count(ids, max_baselines=EVAL_BASELINE_LIMIT)
    with pytest.raises(AppError) as too_many:
        _assert_baseline_count(ids, max_baselines=COMPARE_BASELINE_LIMIT)
    assert too_many.value.code == "BASELINE_COUNT"
    with pytest.raises(AppError) as empty:
        _assert_baseline_count([], max_baselines=EVAL_BASELINE_LIMIT)
    assert empty.value.code == "BASELINE_COUNT"
    with pytest.raises(AppError) as dup:
        _assert_baseline_count(["a", "a"], max_baselines=EVAL_BASELINE_LIMIT)
    assert dup.value.code == "DUP_BASELINE"


def test_eval_rejects_upload_batch_and_missing_gt() -> None:
    with pytest.raises(AppError) as forbidden:
        assert_eval_version(SimpleNamespace(kind="upload_batch", is_fixed_test=False))
    assert forbidden.value.code == "EVAL_DATASET_FORBIDDEN"
    with pytest.raises(AppError) as no_gt:
        assert_eval_samples([SimpleNamespace(mask_uri=None), SimpleNamespace(mask_uri="asset:x")])
    assert no_gt.value.code == "EVAL_NO_GT"
    assert_eval_version(SimpleNamespace(kind="preset", is_fixed_test=True))
    assert_eval_samples([SimpleNamespace(mask_uri="asset:a")])


def test_only_preset_fixed_split_is_eval_ready() -> None:
    preset = SimpleNamespace(id="p", kind="preset", is_fixed_test=True, forbid_student_gt_download=True)
    upload = SimpleNamespace(id="u", kind="upload_batch", is_fixed_test=False, forbid_student_gt_download=False)
    paired = [SimpleNamespace(mask_uri="asset:a") for _ in range(20)]
    missing = [SimpleNamespace(mask_uri="asset:a"), SimpleNamespace(mask_uri=None)]
    ready = summarize_dataset_version(preset, paired)
    assert ready["eval_ready"] is True
    assert ready["sample_count"] == 20
    assert summarize_dataset_version(upload, paired)["eval_ready"] is False
    assert summarize_dataset_version(preset, missing)["eval_ready"] is False
    assert summarize_dataset_version(preset, [])["eval_ready"] is False


def test_official_payload_keeps_acc_off_headline_fields() -> None:
    gt = np.zeros((8, 8), dtype=np.uint8)
    gt[:2, :2] = 1
    pred = np.zeros((8, 8), dtype=np.uint8)
    pred[:2, :2] = 1
    cm = add_to_confmat(empty_confmat(4), pred, gt, 4)
    scored = metrics_dict_from_confmat(cm, include_acc=True)
    assert "mIoU" in scored and "mDice" in scored
    assert "Acc" in scored
    assert 0.0 <= scored["Acc"] <= 1.0
    payload = build_metric_payload(
        n=20,
        models=[{"name": "UNet", **scored}],
        scope=OFFICIAL_SPLIT_SCOPE,
    )
    assert payload["scope"] == OFFICIAL_SPLIT_SCOPE
    assert payload["disclaimer"] == OFFICIAL_SPLIT_DISCLAIMER
    assert "NEU-20" in payload["disclaimer"]
    assert "test split" in payload["disclaimer"]


def test_serialize_metrics_uses_official_disclaimer_for_eval() -> None:
    task = SimpleNamespace(
        has_gt=True,
        type="eval",
        metric_set=SimpleNamespace(
            scope=OFFICIAL_SPLIT_SCOPE,
            n=20,
            payload_json={"models": [{"name": "UNet", "mIoU": 0.41, "mDice": 0.5, "Acc": 0.91}]},
        ),
    )
    body = serialize_metrics(task)
    assert body["available"] is True
    assert body["scope"] == "official_split"
    assert body["n"] == 20
    assert body["disclaimer"] == OFFICIAL_SPLIT_DISCLAIMER
    assert body["models"][0]["Acc"] == 0.91


def test_eval_task_label_on_dashboard() -> None:
    task = SimpleNamespace(
        id="t-eval",
        type="eval",
        status="success",
        has_gt=True,
        error_summary=None,
        created_at=datetime(2026, 9, 16),
    )
    payload = _task_payload(task)
    assert payload["type_label"] == "正式评测"
    assert payload["bundle_ready"] is True
