from __future__ import annotations

from pathlib import Path
from typing import Any

import torch


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
    """Student weights: tensors only. Do not execute pickled callbacks."""
    try:
        obj = torch.load(str(path), map_location="cpu", weights_only=True)
    except TypeError:
        obj = torch.load(str(path), map_location="cpu")
    except Exception as exc:
        raise ValueError(f"无法安全读取权重（拒绝任意 pickle 回调）：{exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError("checkpoint must be a dict")
    return obj
