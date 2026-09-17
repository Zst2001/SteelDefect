from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn

from infer.paths import assets_root, ensure_third_party
from infer.spec import BUILTIN_SLUGS, BUILTIN_WEIGHT_FILES

ensure_third_party()

from load_checkpoint import build_cpu_baseline  # noqa: E402

_L1: dict[str, nn.Module] = {}


def extract_whitelisted_state(ckpt: Any) -> tuple[dict, str | None]:
    """Only accept checkpoint dicts; prefer model_state then state_dict."""
    if not isinstance(ckpt, dict):
        raise ValueError("checkpoint must be a dict")
    model_name = ckpt.get("model_name")
    if "model_state" in ckpt and isinstance(ckpt["model_state"], dict):
        return ckpt["model_state"], str(model_name) if model_name else None
    if "state_dict" in ckpt and isinstance(ckpt["state_dict"], dict):
        return ckpt["state_dict"], str(model_name) if model_name else None
    tensor_like = all(hasattr(v, "shape") for v in ckpt.values())
    if tensor_like:
        return ckpt, str(model_name) if model_name else None
    raise ValueError("checkpoint has no whitelisted key model_state / state_dict")


def load_checkpoint_file(path: str | Path) -> dict:
    try:
        return torch.load(str(path), map_location="cpu", weights_only=False)
    except TypeError:
        return torch.load(str(path), map_location="cpu")


def get_builtin_module(
    cache_key: str,
    slug: str,
    weight_path: str | Path | None = None,
    num_classes: int = 4,
) -> nn.Module:
    if slug not in BUILTIN_SLUGS:
        raise ValueError(f"unsupported builtin slug={slug!r}")
    cached = _L1.get(cache_key)
    if cached is not None:
        return cached
    resolved_weight = Path(weight_path) if weight_path else assets_root() / BUILTIN_WEIGHT_FILES[slug]
    if not resolved_weight.is_file():
        raise FileNotFoundError(f"missing baseline weight: {resolved_weight}")
    ckpt = load_checkpoint_file(resolved_weight)
    # Re-wrap so build_cpu_baseline still prefers model_state.
    if "model_state" not in ckpt:
        state, name = extract_whitelisted_state(ckpt)
        ckpt = {"model_state": state, "model_name": name or slug}
    model, _resolved = build_cpu_baseline(
        ckpt, fallback_model_name=slug, num_classes=num_classes, device=torch.device("cpu")
    )
    _L1[cache_key] = model
    return model


def drop_l1(cache_key: str | None = None) -> None:
    if cache_key is None:
        _L1.clear()
        return
    _L1.pop(cache_key, None)


@torch.no_grad()
def predict_mask(model: nn.Module, image_chw: torch.Tensor) -> np.ndarray:
    tensor = image_chw.unsqueeze(0)
    output = model(tensor)
    if isinstance(output, (tuple, list)):
        output = output[0]
    if not torch.is_tensor(output) or output.ndim != 4:
        raise ValueError("model output must be B,C,H,W logits")
    pred = output.argmax(dim=1)[0].cpu().numpy().astype(np.uint8)
    return pred


def count_parameters(model: nn.Module) -> int:
    return int(sum(p.numel() for p in model.parameters()))
