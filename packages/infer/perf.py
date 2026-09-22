"""Builtin efficiency measurement on the lab-worker CPU. Students stay in Docker."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from admit.perf import collect_env, count_all_parameters, measure_cpu_forward
from infer.engine import get_builtin_module


def measure_builtin(
    *,
    version_id: str,
    slug: str,
    weight_path: Path,
    num_classes: int,
    in_channels: int,
    height: int,
    width: int,
) -> dict[str, Any]:
    model = get_builtin_module(version_id, slug, weight_path, num_classes=num_classes)
    stats = measure_cpu_forward(model, in_channels=in_channels, height=height, width=width)
    return {
        **stats,
        "param_count": count_all_parameters(model),
        "flops": None,
        "weight_bytes": int(weight_path.stat().st_size) if weight_path.is_file() else None,
        "env": collect_env(),
    }
