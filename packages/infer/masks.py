from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def looks_like_label_map(image: np.ndarray, num_classes: int = 4) -> bool:
    """True when pixels are only class ids 0..C-1 (index masks look black as photos)."""
    if image.size == 0:
        return False
    uniq = np.unique(image)
    return int(uniq.size) <= num_classes and int(uniq.max()) < num_classes


class MaskError(ValueError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def color_or_index_to_label(mask_any: np.ndarray) -> np.ndarray:
    """Map a colour or index mask to class ids. Same rule as dataset_defects.DefectDataset."""
    if mask_any.ndim == 3:
        if mask_any.shape[2] == 4:
            mask_bgr = cv2.cvtColor(mask_any, cv2.COLOR_BGRA2BGR)
        else:
            mask_bgr = mask_any[:, :, :3]
        is_bg = (mask_bgr[:, :, 0] == 0) & (mask_bgr[:, :, 1] == 0) & (mask_bgr[:, :, 2] == 0)
        argmax_c = np.argmax(mask_bgr, axis=2)
        mapping = np.array([3, 2, 1], dtype=np.uint8)
        mask_idx = mapping[argmax_c]
        mask_idx[is_bg] = 0
        return mask_idx.astype(np.uint8)
    return mask_any.astype(np.uint8)


def decode_mask_bytes(data: bytes) -> np.ndarray:
    if not data:
        raise MaskError("掩码文件为空", code="EMPTY_FILE")
    decoded = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if decoded is None:
        raise MaskError("无法作为掩码读取", code="UNREADABLE")
    return color_or_index_to_label(decoded)


def validate_label_mask(mask: np.ndarray, *, height: int, width: int, num_classes: int) -> np.ndarray:
    if mask.ndim != 2:
        raise MaskError("掩码必须是单通道类别图", code="MASK_SHAPE")
    if mask.shape[0] != height or mask.shape[1] != width:
        raise MaskError(
            f"掩码尺寸 {mask.shape[1]}×{mask.shape[0]} 与原图 {width}×{height} 不一致",
            code="MASK_SIZE",
        )
    max_id = int(mask.max()) if mask.size else 0
    min_id = int(mask.min()) if mask.size else 0
    if min_id < 0 or max_id >= num_classes:
        raise MaskError(
            f"掩码类别超出 0–{num_classes - 1}（实际 {min_id}–{max_id}）",
            code="MASK_CLASS",
        )
    return mask.astype(np.uint8)


def encode_index_png(mask: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", mask)
    if not ok:
        raise MaskError("无法写出掩码 PNG", code="UNREADABLE")
    return buf.tobytes()


def read_index_mask(path: str | Path) -> np.ndarray:
    mask_any = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if mask_any is None:
        raise RuntimeError(f"Failed to read mask: {path}")
    return color_or_index_to_label(mask_any)
