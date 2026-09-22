from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "apps" / "api")]

from PIL import Image

from app.services.scatter import MAIN_COLOR, mm_to_scatter_s, render_scatter


def _points():
    return [
        {"name": "LGDS-Net (Our)", "x": 214.3, "y": 86.2, "params": 12.4, "is_main": True},
        {"name": "UNet", "x": 180.1, "y": 82.4, "params": 17.3, "is_main": False},
        {"name": "PSPNet", "x": 95.0, "y": 84.1, "params": None, "is_main": False},
    ]


def test_mm_to_scatter_s_is_point_area():
    assert mm_to_scatter_s(5) == pytest.approx((5 / 25.4 * 72) ** 2)


def test_png_and_pdf_magic():
    png = render_scatter(
        title="Network Performance Comparison",
        xlabel="FPS",
        ylabel="mIoU (%)",
        points=_points(),
        default_marker_mm=5,
        fmt="png",
    )
    pdf = render_scatter(
        title="Network Performance Comparison",
        xlabel="FPS",
        ylabel="mIoU (%)",
        points=_points(),
        default_marker_mm=5,
        fmt="pdf",
    )
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert pdf.startswith(b"%PDF")


def test_main_model_uses_red():
    png = render_scatter(
        title="t",
        xlabel="X",
        ylabel="Y",
        points=_points(),
        fmt="png",
    )
    image = Image.open(BytesIO(png)).convert("RGB")
    target = tuple(int(MAIN_COLOR[i : i + 2], 16) for i in (1, 3, 5))
    found = False
    for pixel in image.getdata():
        if all(abs(channel - expected) <= 18 for channel, expected in zip(pixel, target, strict=True)):
            found = True
            break
    assert found


def test_missing_params_keep_default_size():
    from app.services.scatter import _sizes

    sizes = _sizes([None, None], 5)
    assert sizes[0] == sizes[1] == mm_to_scatter_s(5)
