from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
import torch

from infer.paths import ensure_third_party
from infer.spec import BATCH_REFERENCE_DISCLAIMER, BATCH_REFERENCE_SCOPE, NEU_CLASS_MAP, OFFICIAL_SPLIT_DISCLAIMER, OFFICIAL_SPLIT_SCOPE

ensure_third_party()

from utils_losses_metrics import compute_confusion_matrix, metrics_from_confmat  # noqa: E402


def empty_confmat(num_classes: int) -> torch.Tensor:
    return torch.zeros((num_classes, num_classes), dtype=torch.int64)


def add_to_confmat(cm: torch.Tensor, pred_hw: np.ndarray, gt_hw: np.ndarray, num_classes: int) -> torch.Tensor:
    if pred_hw.shape != gt_hw.shape:
        raise ValueError(f"pred/gt grid mismatch {pred_hw.shape} vs {gt_hw.shape}")
    pred = torch.from_numpy(pred_hw.astype(np.int64, copy=False)).unsqueeze(0)
    target = torch.from_numpy(gt_hw.astype(np.int64, copy=False)).unsqueeze(0)
    return cm + compute_confusion_matrix(pred, target, num_classes)


def _round_metric(value: float) -> float:
    return round(float(value), 6)


def metrics_dict_from_confmat(
    cm: torch.Tensor,
    class_map: Mapping[str, str] | None = None,
    *,
    include_acc: bool = False,
) -> dict[str, Any]:
    raw = metrics_from_confmat(cm)
    iou = [_round_metric(v) for v in raw["IoU_per_class"].tolist()]
    labels = class_map or NEU_CLASS_MAP
    per_class = []
    for index, score in enumerate(iou):
        per_class.append({"id": index, "name": labels.get(str(index), str(index)), "iou": score})
    payload = {
        "mIoU": _round_metric(float(raw["mIoU"])),
        "mDice": _round_metric(float(raw["mDice"])),
        "IoU_per_class": iou,
        "classes": per_class,
    }
    if include_acc:
        payload["Acc"] = _round_metric(float(raw["Acc"]))
    return payload


def build_metric_payload(
    *,
    n: int,
    models: Sequence[Mapping[str, Any]],
    class_map: Mapping[str, str] | None = None,
    scope: str = BATCH_REFERENCE_SCOPE,
    disclaimer: str | None = None,
) -> dict[str, Any]:
    labels = dict(class_map or NEU_CLASS_MAP)
    if disclaimer is None:
        disclaimer = (
            OFFICIAL_SPLIT_DISCLAIMER if scope == OFFICIAL_SPLIT_SCOPE else BATCH_REFERENCE_DISCLAIMER
        )
    return {
        "scope": scope,
        "n": int(n),
        "display_align": "original_size",
        "class_map": labels,
        "disclaimer": disclaimer,
        "models": list(models),
    }
