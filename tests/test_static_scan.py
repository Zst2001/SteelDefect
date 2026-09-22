from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages")]

from admit.scan import scan_student_file, scan_student_source  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "student"


def test_good_tiny_passes_static_scan() -> None:
    issues = scan_student_file(str(FIXTURES / "good_tiny.py"))
    assert issues == []


def test_subprocess_is_blocked() -> None:
    issues = scan_student_file(str(FIXTURES / "bad_subprocess.py"))
    assert issues
    assert any("subprocess" in item.message.lower() or "不允许" in item.message for item in issues)


def test_eval_is_blocked() -> None:
    issues = scan_student_file(str(FIXTURES / "bad_eval.py"))
    assert any("eval" in item.message.lower() for item in issues)


def test_future_and_module_eval_are_allowed() -> None:
    source = """
from __future__ import annotations
import torch
import torch.nn as nn

class Tiny(nn.Module):
    def forward(self, x):
        return x

    def ratios(self):
        return getattr(self, "head")

def build_model(num_classes, in_channels=3, **kwargs):
    model = Tiny()
    model.eval()
    return model
"""
    assert scan_student_source(source) == []


def test_builtin_eval_still_blocked() -> None:
    issues = scan_student_source("x = eval('1')\n")
    assert any("eval" in item.message.lower() for item in issues)


def test_getattr_on_other_objects_blocked() -> None:
    issues = scan_student_source("getattr(torch, 'nn')\n")
    assert any("getattr" in item.message.lower() for item in issues)


def test_os_and_network_imports_blocked() -> None:
    source = "import os\nimport socket\nimport requests\n"
    messages = " ".join(item.message for item in scan_student_source(source))
    assert "os" in messages
    assert "socket" in messages
    assert "requests" in messages
