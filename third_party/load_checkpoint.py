"""Minimal CPU-baseline loader. Checkpoints typically store weights under `model_state`."""

from typing import Any, Dict, Optional, Tuple

import torch
import torch.nn as nn

from compare import DeepLabV3Plus, NestedUNet, UNet


def build_cpu_baseline(
    ckpt: Dict[str, Any],
    fallback_model_name: str,
    num_classes: int = 4,
    device: Optional[torch.device] = None,
) -> Tuple[nn.Module, str]:
    if device is None:
        device = torch.device("cpu")
    state_dict = ckpt.get("model_state", ckpt)
    model_name = str(ckpt.get("model_name", fallback_model_name)).lower()

    if model_name in ("unet", "best_unet"):
        model = UNet(in_channels=3, num_classes=num_classes, bilinear=True)
        resolved = "unet"
    elif model_name in ("unetpp", "unet++", "nestedunet", "best_unetpp"):
        model = NestedUNet(in_channels=3, num_classes=num_classes, deep_supervision=False)
        resolved = "unetpp"
    elif model_name in ("deeplabv3", "deeplabv3plus", "deeplabv3+", "best_deeplabv3"):
        model = DeepLabV3Plus(
            in_channels=3, num_classes=num_classes, backbone="resnet50", pretrained=False
        )
        resolved = "deeplabv3"
    else:
        raise ValueError(
            f"Unsupported CPU baseline model_name={model_name!r}. "
            "Expected unet / unetpp / deeplabv3."
        )

    model.load_state_dict(state_dict, strict=True)
    model.to(device)
    model.eval()
    return model, resolved
