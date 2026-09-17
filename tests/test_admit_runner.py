from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages")]

FIXTURES = ROOT / "tests" / "fixtures" / "student"


class TinySeg(nn.Module):
    def __init__(self, num_classes: int, in_channels: int = 3, **kwargs):
        super().__init__()
        self.stem = nn.Conv2d(in_channels, 8, kernel_size=3, padding=1)
        self.head = nn.Conv2d(8, num_classes, kernel_size=1)

    def forward(self, x):
        return self.head(torch.relu(self.stem(x)))


def _write_weights(path: Path) -> None:
    model = TinySeg(num_classes=4, in_channels=3)
    torch.save({"model_state": model.state_dict()}, path)


def test_admit_runner_accepts_tiny_model(tmp_path: Path) -> None:
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    (in_dir / "model.py").write_text((FIXTURES / "good_tiny.py").read_text(encoding="utf-8"), encoding="utf-8")
    _write_weights(in_dir / "weights.pth")
    (in_dir / "manifest.json").write_text(
        json.dumps(
            {
                "entry_symbol": "build_model",
                "num_classes": 4,
                "in_channels": 3,
                "input_h": 200,
                "input_w": 200,
                "source_name": "model.py",
                "weight_name": "weights.pth",
            }
        ),
        encoding="utf-8",
    )
    env = {**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": str(ROOT / "packages")}
    proc = subprocess.run(
        [sys.executable, "-m", "admit", "admit", "--in", str(in_dir), "--out", str(out_dir)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    result = json.loads((out_dir / "result.json").read_text(encoding="utf-8"))
    assert proc.returncode == 0, proc.stderr
    assert result["ok"] is True
    assert result["param_count"] > 0


def test_admit_runner_shape_mismatch(tmp_path: Path) -> None:
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    (in_dir / "model.py").write_text((FIXTURES / "good_tiny.py").read_text(encoding="utf-8"), encoding="utf-8")
    _write_weights(in_dir / "weights.pth")
    (in_dir / "manifest.json").write_text(
        json.dumps(
            {
                "entry_symbol": "build_model",
                "num_classes": 8,
                "in_channels": 3,
                "input_h": 200,
                "input_w": 200,
                "source_name": "model.py",
                "weight_name": "weights.pth",
            }
        ),
        encoding="utf-8",
    )
    env = {**__import__("os").environ, "PYTHONPATH": str(ROOT / "packages")}
    subprocess.run(
        [sys.executable, "-m", "admit", "admit", "--in", str(in_dir), "--out", str(out_dir)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    result = json.loads((out_dir / "result.json").read_text(encoding="utf-8"))
    assert result["ok"] is False
    assert result["fail_stage"] in {"load", "shape", "build"}
