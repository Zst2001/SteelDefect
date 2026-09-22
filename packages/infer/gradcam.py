"""Segmentation Grad-CAM for builtin CPU baselines.

Follows jacobgil/pytorch-grad-cam's SemanticSegmentationTarget: the scalar is the
sum of class logits over the predicted region. Target layers are Conv2d modules so
inplace ReLU later in the block does not corrupt the hooked tensor.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# Last spatial conv before the 1x1 classifier, keyed by builtin slug.
TARGET_LAYER_PATHS: dict[str, str] = {
    "unet": "up4.conv.double_conv.3",
    "unetpp": "conv0_4.conv2",
    "deeplabv3": "classifier.0",
    "bisenet": "classifier.0",
    "danet": "head.conv_p2.0",
    "pspnet": "classifier.0",
    "segformer": "decode_head.linear_fuse",
}


def cam_class_ids(num_classes: int) -> tuple[int, ...]:
    """Defect classes only. Background (0) is not visualized."""
    return tuple(index for index in range(1, max(int(num_classes), 1)))


def cam_artifact_rel(model_version_id: str, sample_key: str, class_id: int) -> str:
    return f"cam/{model_version_id}/{sample_key}__c{int(class_id)}.png"


def cam_montage_rel(sample_key: str, class_id: int) -> str:
    return f"montage/{sample_key}__cam_c{int(class_id)}.png"


def _nested_attr(root: nn.Module, path: str) -> nn.Module:
    current: Any = root
    for part in path.split("."):
        current = current[int(part)] if part.isdigit() else getattr(current, part)
    if not isinstance(current, nn.Module):
        raise TypeError(f"{path} is not an nn.Module")
    return current


def last_spatial_conv(model: nn.Module, num_classes: int) -> nn.Module:
    chosen: nn.Module | None = None
    for _name, module in model.named_modules():
        if not isinstance(module, nn.Conv2d):
            continue
        if module.out_channels == num_classes and module.kernel_size == (1, 1):
            continue
        chosen = module
    if chosen is None:
        raise RuntimeError("no Conv2d suitable for Grad-CAM")
    return chosen


def resolve_target_layer(model: nn.Module, *, slug: str | None, num_classes: int) -> nn.Module:
    path = TARGET_LAYER_PATHS.get(str(slug or ""))
    if path:
        try:
            return _nested_attr(model, path)
        except (AttributeError, IndexError, TypeError):
            pass
    return last_spatial_conv(model, num_classes)


def _primary_logits(output: Any) -> torch.Tensor:
    if isinstance(output, (tuple, list)):
        output = output[0]
    if not torch.is_tensor(output) or output.ndim != 4:
        raise ValueError("model output must be B,C,H,W logits")
    return output


def compute_gradcam(
    model: nn.Module,
    image_chw: torch.Tensor,
    *,
    class_id: int,
    pred_mask: np.ndarray,
    target_layer: nn.Module,
) -> np.ndarray:
    """Return a [0, 1] CAM at the predicted-mask spatial size."""
    mask = np.asarray(pred_mask)
    if mask.ndim != 2:
        raise ValueError("pred_mask must be H,W")
    empty = np.zeros(mask.shape, dtype=np.float32)
    region = (mask == int(class_id)).astype(np.float32)
    if float(region.sum()) < 1:
        return empty

    activations: list[torch.Tensor] = []
    gradients: list[torch.Tensor] = []

    def on_forward(_module: nn.Module, _inputs: Any, output: torch.Tensor) -> None:
        activations.append(output.detach())
        if output.requires_grad:
            def _store_grad(grad: torch.Tensor) -> None:
                gradients.append(grad.detach())

            output.register_hook(_store_grad)

    handle_f = target_layer.register_forward_hook(on_forward)
    was_training = model.training
    model.eval()
    tensor: torch.Tensor | None = None
    try:
        tensor = image_chw.detach().float().unsqueeze(0)
        tensor.requires_grad_(True)
        model.zero_grad(set_to_none=True)
        logits = _primary_logits(model(tensor))
        class_map = logits[0, int(class_id)]
        region_t = torch.from_numpy(region).to(device=class_map.device, dtype=class_map.dtype)
        if region_t.shape != class_map.shape:
            region_t = F.interpolate(
                region_t.unsqueeze(0).unsqueeze(0),
                size=class_map.shape,
                mode="nearest",
            )[0, 0]
        score = (class_map * region_t).sum()
        score_ok = bool(torch.isfinite(score.detach()).item()) and float(score.detach().abs()) >= 1e-12
        if not score_ok:
            return empty
        score.backward()
        if not activations or not gradients:
            return empty
        acts = activations[-1][0]
        grads = gradients[-1][0]
        if acts.ndim != 3 or grads.ndim != 3:
            raise ValueError("Grad-CAM layer must emit C,H,W feature maps")
        weights = grads.mean(dim=(1, 2))
        cam = torch.relu((weights[:, None, None] * acts).sum(dim=0))
        peak = float(cam.max().item())
        if peak <= 1e-12:
            return empty
        cam = cam / peak
        cam_np = cam.detach().cpu().numpy().astype(np.float32)
        if cam_np.shape != mask.shape:
            cam_np = cv2.resize(cam_np, (mask.shape[1], mask.shape[0]), interpolation=cv2.INTER_LINEAR)
        return np.clip(cam_np, 0.0, 1.0)
    finally:
        handle_f.remove()
        if tensor is not None:
            tensor.grad = None
        model.zero_grad(set_to_none=True)
        if was_training:
            model.train()


def overlay_cam_rgb(origin_rgb: np.ndarray, cam: np.ndarray, image_weight: float = 0.5) -> np.ndarray:
    """Jet heatmap on the origin. `cam` is [0, 1]; origin is uint8 RGB."""
    if origin_rgb.ndim != 3 or origin_rgb.shape[2] != 3:
        raise ValueError("origin_rgb must be H,W,3")
    height, width = origin_rgb.shape[:2]
    cam_map = np.asarray(cam, dtype=np.float32)
    if cam_map.shape != (height, width):
        cam_map = cv2.resize(cam_map, (width, height), interpolation=cv2.INTER_LINEAR)
    cam_map = np.clip(cam_map, 0.0, 1.0)
    heatmap = cv2.applyColorMap(np.uint8(np.round(255.0 * cam_map)), cv2.COLORMAP_JET)
    heatmap = cv2.cvtColor(heatmap, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    image = origin_rgb.astype(np.float32) / 255.0
    weight = float(np.clip(image_weight, 0.0, 1.0))
    blended = (1.0 - weight) * heatmap + weight * image
    peak = float(blended.max())
    if peak > 0:
        blended = blended / peak
    return np.clip(np.round(blended * 255.0), 0, 255).astype(np.uint8)
