from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from infer.paths import ensure_third_party

ensure_third_party()

from infer.spec import ERROR_COLORS_BGR

from viz_color import colorize_mask, get_color_map  # noqa: E402


def neu_color_map(num_classes: int = 4) -> dict[int, list[int]]:
    return get_color_map("neu", num_classes)


def save_rgb_png(path: Path, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if not cv2.imwrite(str(path), bgr):
        raise RuntimeError(f"failed to write {path}")


def save_bgr_png(path: Path, bgr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), bgr):
        raise RuntimeError(f"failed to write {path}")


def align_mask(mask: np.ndarray, height: int, width: int) -> np.ndarray:
    if mask.shape[0] == height and mask.shape[1] == width:
        return mask
    return cv2.resize(mask, (width, height), interpolation=cv2.INTER_NEAREST)


def colorize_bgr(mask: np.ndarray, dataset: str = "neu", num_classes: int = 4) -> np.ndarray:
    return colorize_mask(mask, get_color_map(dataset, num_classes))


def overlay_rgb(origin_rgb: np.ndarray, mask_aligned: np.ndarray, alpha: float = 0.45) -> np.ndarray:
    """Blend class colors onto the origin only where the mask is a defect (class > 0)."""
    color_bgr = colorize_bgr(mask_aligned)
    color_rgb = cv2.cvtColor(color_bgr, cv2.COLOR_BGR2RGB)
    out = origin_rgb.astype(np.float32)
    defect = mask_aligned > 0
    if not np.any(defect):
        return origin_rgb.copy()
    out[defect] = (1.0 - alpha) * out[defect] + alpha * color_rgb[defect].astype(np.float32)
    return np.clip(out, 0, 255).astype(np.uint8)


def error_map_bgr(pred: np.ndarray, gt: np.ndarray) -> np.ndarray:
    """Pixel error map on the display grid. TN black, TP green, FP mill orange, FN blue, swap yellow."""
    if pred.shape != gt.shape:
        raise ValueError(f"pred/gt shape mismatch {pred.shape} vs {gt.shape}")
    out = np.zeros((*gt.shape, 3), dtype=np.uint8)
    tn = (pred == gt) & (gt == 0)
    tp = (pred == gt) & (gt > 0)
    fp = (pred > 0) & (gt == 0)
    fn = (pred == 0) & (gt > 0)
    swap = (pred != gt) & (pred > 0) & (gt > 0)
    out[tn] = ERROR_COLORS_BGR["tn"]
    out[tp] = ERROR_COLORS_BGR["tp"]
    out[fp] = ERROR_COLORS_BGR["fp"]
    out[fn] = ERROR_COLORS_BGR["fn"]
    out[swap] = ERROR_COLORS_BGR["swap"]
    return out


def boundary_bgr(mask_aligned: np.ndarray, dataset: str = "neu", num_classes: int = 4) -> np.ndarray:
    color = colorize_bgr(mask_aligned, dataset=dataset, num_classes=num_classes)
    kernel = np.ones((3, 3), np.uint8)
    edges = np.zeros_like(color)
    unique_ids = [int(v) for v in np.unique(mask_aligned) if int(v) > 0]
    for class_id in unique_ids:
        layer = (mask_aligned == class_id).astype(np.uint8) * 255
        gradient = cv2.morphologyEx(layer, cv2.MORPH_GRADIENT, kernel)
        edges[gradient > 0] = color[gradient > 0]
    return edges
