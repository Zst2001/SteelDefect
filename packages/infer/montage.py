from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np

HEADER_H = 36
GAP = 8
PANEL_BG = (32, 36, 42)


def _fit(image_bgr: np.ndarray, height: int, width: int) -> np.ndarray:
    if image_bgr.shape[0] == height and image_bgr.shape[1] == width:
        return image_bgr
    return cv2.resize(image_bgr, (width, height), interpolation=cv2.INTER_LINEAR)


def _header(width: int, text: str) -> np.ndarray:
    bar = np.full((HEADER_H, width, 3), PANEL_BG, dtype=np.uint8)
    cv2.putText(
        bar,
        text,
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (232, 228, 217),
        1,
        cv2.LINE_AA,
    )
    return bar


def build_row(panels: Sequence[tuple[str, np.ndarray]]) -> np.ndarray:
    """Horizontal montage. Column order is the given sequence (origin | [gt] | baselines | student)."""
    if not panels:
        raise ValueError("montage needs at least one panel")
    heights = [p.shape[0] for _, p in panels]
    widths = [p.shape[1] for _, p in panels]
    height = max(heights)
    width = max(widths)
    chunks: list[np.ndarray] = []
    for index, (title, image) in enumerate(panels):
        fitted = _fit(image, height, width)
        labeled = np.vstack([_header(width, title), fitted])
        chunks.append(labeled)
        if index != len(panels) - 1:
            chunks.append(np.full((height + HEADER_H, GAP, 3), PANEL_BG, dtype=np.uint8))
    return np.hstack(chunks)
