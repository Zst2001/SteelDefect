# -*- coding: utf-8 -*-
"""叠加、边界、概率图和 Grad-CAM。概率图不是 Grad-CAM。无合法 GT 时不生成误差图。"""

import cv2
import numpy as np
import torch
import torch.nn.functional as F

from .postprocess import mask_and_probability, to_numpy
from .preprocess import prepare_canvas


OVERLAY_COLOR = (220, 30, 30)
OVERLAY_ALPHA = 0.45


class ContractError(ValueError):
    pass


def overlay(image, mask):
    out = np.asarray(image).astype(np.float32).copy()
    color = np.array(OVERLAY_COLOR, dtype=np.float32)
    out[mask == 1] = (1.0 - OVERLAY_ALPHA) * out[mask == 1] + OVERLAY_ALPHA * color
    return np.clip(out, 0, 255).astype(np.uint8)


def boundary(mask):
    fg = (mask == 1).astype(np.uint8)
    contours, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    canvas = np.zeros((mask.shape[0], mask.shape[1], 3), dtype=np.uint8)
    cv2.drawContours(canvas, contours, -1, (255, 220, 0), 1)
    return canvas


def probability_heatmap(probability):
    gray = np.clip(np.asarray(probability) * 255.0, 0, 255).astype(np.uint8)
    colored = cv2.applyColorMap(gray, cv2.COLORMAP_VIRIDIS)
    return cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)


def error_map(gt, pred):
    gt_array = np.asarray(gt)
    if gt_array.shape != (220, 220) or set(np.unique(gt_array).tolist()) - {0, 1}:
        raise ContractError("GT 必须是 220×220 且只含 0 和 1")
    canvas = np.zeros((220, 220, 3), dtype=np.uint8)
    canvas[(gt_array == 1) & (pred == 1)] = (40, 180, 70)
    canvas[(gt_array == 0) & (pred == 1)] = (220, 40, 40)
    canvas[(gt_array == 1) & (pred == 0)] = (40, 90, 220)
    return canvas


class SegmentationGradCAM(object):
    def __init__(self, model):
        layer_name = model.cam_layer_name
        modules = dict(model.named_modules())
        if layer_name not in modules:
            raise ContractError("模型没有审定的 CAM 层 %s" % layer_name)
        self.model = model
        self.layer_name = layer_name
        self.fmap = None
        self.grad = None
        self.layer = modules[layer_name]

    def __call__(self, image):
        handles = [
            self.layer.register_forward_hook(lambda _m, _i, out: setattr(self, "fmap", out)),
            self.layer.register_full_backward_hook(lambda _m, _gin, gout: setattr(self, "grad", gout[0])),
        ]
        requires_grad = [p.requires_grad for p in self.model.parameters()]
        try:
            with torch.enable_grad():
                return self._compute(image)
        finally:
            for handle in handles:
                handle.remove()
            self.model.zero_grad(set_to_none=True)
            for p, original in zip(self.model.parameters(), requires_grad):
                p.requires_grad_(original)
            self.fmap = self.grad = None

    def _compute(self, image):
        tensor = prepare_canvas(image)
        for param in self.model.parameters():
            param.requires_grad_(True)
        self.model.eval()
        logits = self.model(tensor)
        valid = torch.zeros(logits.shape[-2:], dtype=logits.dtype)
        valid[18:238, 18:238] = 1
        region = (logits.argmax(dim=1) == 1).float().detach() * valid.view(1, 256, 256)
        if float(region.sum().item()) <= 0:
            return {"status": "unavailable", "reason": "预测前景为空", "layer": self.layer_name}
        if self.fmap is None:
            return {"status": "failed", "reason": "目标层没有特征", "layer": self.layer_name}
        score = (logits[:, 1] * region).sum()
        self.model.zero_grad(set_to_none=True)
        score.backward()
        if self.grad is None or not torch.isfinite(self.grad).all():
            return {"status": "failed", "reason": "目标层没有有效梯度", "layer": self.layer_name}
        weights = self.grad.mean(dim=(2, 3), keepdim=True)
        cam = F.relu((weights * self.fmap).sum(dim=1, keepdim=True))
        cam = F.interpolate(cam, size=logits.shape[-2:], mode="bilinear", align_corners=False)
        cam = cam[0, 0, 18:238, 18:238].detach()
        if not torch.isfinite(cam).all() or float(cam.max()) <= 0:
            return {"status": "failed", "reason": "Grad-CAM 为空", "layer": self.layer_name}
        norm = (cam - cam.min()) / (cam.max() - cam.min() + 1e-8)
        return {
            "status": "ok",
            "layer": self.layer_name,
            "map": norm.cpu().numpy(),
            "target": "原图范围内预测缺陷像素的 defect logit 之和，区域 detach",
        }


def predict_layers(model, image, gt=None):
    tensor = prepare_canvas(image)
    with torch.no_grad():
        logits = model(tensor)
    if not torch.isfinite(logits).all():
        raise ContractError("logits 含非有限值")
    mask, probability = to_numpy(*mask_and_probability(logits))
    image_array = np.asarray(image)
    layers = {
        "logits": logits.detach().cpu(),
        "pred_mask": mask,
        "probability": probability,
        "probability_heatmap": probability_heatmap(probability),
        "overlay": overlay(image_array, mask),
        "boundary": boundary(mask),
    }
    if gt is not None:
        layers["error_map"] = error_map(gt, mask)
    return layers
