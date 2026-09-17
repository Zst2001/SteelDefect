from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party"), str(ROOT / "apps" / "api")]

import numpy as np
import pytest

pytest.importorskip("cv2")
pytest.importorskip("torch")

from infer.masks import MaskError, color_or_index_to_label, decode_mask_bytes, encode_index_png, looks_like_label_map, validate_label_mask  # noqa: E402
from infer.metrics import add_to_confmat, build_metric_payload, empty_confmat, metrics_dict_from_confmat  # noqa: E402
from infer.spec import BATCH_REFERENCE_DISCLAIMER, ERROR_COLORS_BGR  # noqa: E402
from infer.task_io import check_drawio_bundle_names, metrics_response  # noqa: E402
from infer.viz import align_mask, error_map_bgr  # noqa: E402


def test_drawio_bundle_allows_gt_and_error_but_not_metrics() -> None:
    names = [
        "task.json",
        "montage/a__mask.png",
        "origin/a.png",
        "gt/a.png",
        "error/model/a.png",
        "montage/a__error.png",
    ]
    check_drawio_bundle_names(names)
    with pytest.raises(ValueError, match="metrics.json"):
        check_drawio_bundle_names([*names, "metrics.json"])


def test_color_mask_maps_red_to_inclusion() -> None:
    canvas = np.zeros((4, 4, 3), dtype=np.uint8)
    canvas[1, 2] = (0, 0, 255)
    labels = color_or_index_to_label(canvas)
    assert labels.shape == (4, 4)
    assert int(labels[1, 2]) == 1
    assert int(labels[0, 0]) == 0


def test_index_mask_is_detected_as_label_map() -> None:
    labels = np.zeros((8, 8), dtype=np.uint8)
    labels[2, 3] = 1
    assert looks_like_label_map(labels) is True
    photo = np.full((8, 8, 3), 114, dtype=np.uint8)
    photo[0, 0] = (47, 80, 153)
    assert looks_like_label_map(photo) is False


def test_index_mask_roundtrip_and_size_check() -> None:
    labels = np.zeros((6, 8), dtype=np.uint8)
    labels[2, 3] = 2
    png = encode_index_png(labels)
    decoded = decode_mask_bytes(png)
    checked = validate_label_mask(decoded, height=6, width=8, num_classes=4)
    assert np.array_equal(checked, labels)
    with pytest.raises(MaskError) as exc:
        validate_label_mask(decoded, height=6, width=7, num_classes=4)
    assert exc.value.code == "MASK_SIZE"


def test_reject_class_id_out_of_range() -> None:
    labels = np.zeros((2, 2), dtype=np.uint8)
    labels[0, 0] = 4
    with pytest.raises(MaskError) as exc:
        validate_label_mask(labels, height=2, width=2, num_classes=4)
    assert exc.value.code == "MASK_CLASS"


def test_metrics_use_aligned_original_grid() -> None:
    gt = np.zeros((40, 50), dtype=np.uint8)
    gt[:10, :10] = 1
    pred_small = np.zeros((20, 25), dtype=np.uint8)
    pred_small[:5, :5] = 1
    aligned = align_mask(pred_small, 40, 50)
    assert aligned.shape == (40, 50)
    cm = add_to_confmat(empty_confmat(4), aligned, gt, 4)
    assert int(cm.sum()) == 40 * 50
    scored = metrics_dict_from_confmat(cm)
    assert "Acc" not in scored
    assert 0.0 <= scored["mIoU"] <= 1.0
    assert len(scored["IoU_per_class"]) == 4


def test_metric_payload_is_batch_reference_without_acc() -> None:
    payload = build_metric_payload(
        n=2,
        models=[{"name": "UNet", "mIoU": 0.5, "mDice": 0.6, "IoU_per_class": [0.1, 0.2, 0.3, 0.4]}],
    )
    blob = str(payload).lower()
    assert payload["scope"] == "batch_reference"
    assert payload["disclaimer"] == BATCH_REFERENCE_DISCLAIMER
    assert payload["display_align"] == "original_size"
    assert "acc" not in blob
    wrapped = metrics_response(has_gt=True, payload=payload)
    assert wrapped["available"] is True
    assert wrapped["disclaimer"] == BATCH_REFERENCE_DISCLAIMER
    assert "Acc" not in wrapped


def test_error_map_tp_fp_fn_swap() -> None:
    pred = np.array([[0, 1], [1, 2]], dtype=np.uint8)
    gt = np.array([[0, 1], [0, 1]], dtype=np.uint8)
    err = error_map_bgr(pred, gt)
    assert tuple(err[0, 0]) == ERROR_COLORS_BGR["tn"]
    assert tuple(err[0, 1]) == ERROR_COLORS_BGR["tp"]
    assert tuple(err[1, 0]) == ERROR_COLORS_BGR["fp"]
    assert tuple(err[1, 1]) == ERROR_COLORS_BGR["swap"]
