"""CPU dummy-forward protocol shared by worker builtins and the student isolate runner.

Do not report FPS. Time is milliseconds per image, batch=1, device=cpu.
Parameter count is every nn.Parameter (not requires_grad-only).
"""

from __future__ import annotations

import platform
import sys
import time
from typing import Any

import torch
import torch.nn as nn

WARMUP_RUNS = 3
TIMED_RUNS = 10
BATCH = 1
DEVICE = "cpu"
INPUT_KIND = "dummy"


def first_output_tensor(output: object) -> torch.Tensor:
    if isinstance(output, (tuple, list)):
        output = output[0]
    if not torch.is_tensor(output):
        raise TypeError("forward 主输出必须是张量")
    return output


def count_all_parameters(model: nn.Module) -> int:
    return int(sum(p.numel() for p in model.parameters()))


def collect_env() -> dict[str, str]:
    return {
        "device": DEVICE,
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
    }


@torch.inference_mode()
def measure_cpu_forward(
    model: nn.Module,
    *,
    in_channels: int,
    height: int,
    width: int,
    warmup_runs: int = WARMUP_RUNS,
    timed_runs: int = TIMED_RUNS,
) -> dict[str, Any]:
    model.eval()
    dummy = torch.randn(BATCH, in_channels, height, width, dtype=torch.float32)
    first_output_tensor(model(dummy))
    for _ in range(warmup_runs):
        model(dummy)
    timings_ms: list[float] = []
    for _ in range(timed_runs):
        started = time.perf_counter()
        first_output_tensor(model(dummy))
        timings_ms.append((time.perf_counter() - started) * 1000.0)
    mean_ms = sum(timings_ms) / len(timings_ms)
    return {
        "latency_ms_per_image": round(mean_ms, 3),
        "warmup_runs": warmup_runs,
        "timed_runs": timed_runs,
        "batch": BATCH,
        "input_h": height,
        "input_w": width,
        "input_kind": INPUT_KIND,
        "device": DEVICE,
        "timings_ms": [round(item, 3) for item in timings_ms],
    }


def fps_from_latency_ms(latency_ms: float | None, batch: int = BATCH) -> float | None:
    """Throughput of the same dummy-forward protocol. Not paper / CUDA FPS."""
    if latency_ms is None or latency_ms <= 0:
        return None
    return round((1000.0 * max(int(batch), 1)) / float(latency_ms), 3)
