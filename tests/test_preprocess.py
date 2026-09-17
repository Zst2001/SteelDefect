from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party"), str(ROOT / "apps" / "api")]

import pytest

pytest.importorskip("cv2")
pytest.importorskip("torch")
from infer.dataset_images import preprocess_rgb, read_rgb  # noqa: E402
from infer.spec import PreprocessSpec  # noqa: E402


def test_preprocess_is_deterministic_and_honors_size() -> None:
    image = ROOT / "assets" / "samples" / "neu" / "images" / "000001.jpg"
    if not image.is_file():
        return
    spec = PreprocessSpec(height=200, width=200, apply_clahe=True, sp_threshold=0.02)
    rgb = read_rgb(image)
    a = preprocess_rgb(rgb, spec)
    b = preprocess_rgb(rgb, spec)
    assert tuple(a.shape) == (3, 200, 200)
    assert a.equal(b)
