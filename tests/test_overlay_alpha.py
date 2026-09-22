from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party")]

from infer.viz import overlay_rgb  # noqa: E402


def test_overlay_keeps_background_origin_unchanged() -> None:
    origin = np.full((8, 8, 3), 80, dtype=np.uint8)
    mask = np.zeros((8, 8), dtype=np.uint8)
    mask[2:5, 2:5] = 1
    out = overlay_rgb(origin, mask, alpha=1.0)
    assert np.array_equal(out[0, 0], [80, 80, 80])
    assert not np.array_equal(out[3, 3], [80, 80, 80])


def test_overlay_zero_alpha_is_origin() -> None:
    origin = np.arange(48, dtype=np.uint8).reshape(4, 4, 3)
    mask = np.ones((4, 4), dtype=np.uint8)
    out = overlay_rgb(origin, mask, alpha=0.0)
    assert np.array_equal(out, origin)


def test_overlay_does_not_dim_whole_image() -> None:
    origin = np.full((6, 6, 3), 120, dtype=np.uint8)
    mask = np.zeros((6, 6), dtype=np.uint8)
    mask[1, 1] = 3
    out = overlay_rgb(origin, mask, alpha=0.45)
    background = np.delete(out.reshape(-1, 3), 1 * 6 + 1, axis=0)
    assert np.allclose(background, 120, atol=0)
