from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party")]

from infer.gradcam import (  # noqa: E402
    TARGET_LAYER_PATHS,
    cam_artifact_rel,
    cam_class_ids,
    cam_montage_rel,
    compute_gradcam,
    overlay_cam_rgb,
    resolve_target_layer,
)
from infer.task_io import check_drawio_bundle_names  # noqa: E402


class TinySeg(nn.Module):
    def __init__(self, num_classes: int = 4) -> None:
        super().__init__()
        self.features = nn.Conv2d(3, 8, 3, padding=1)
        self.norm = nn.BatchNorm2d(8)
        self.relu = nn.ReLU(inplace=True)
        self.head = nn.Conv2d(8, num_classes, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.relu(self.norm(self.features(x))))


def test_cam_class_ids_skip_background() -> None:
    assert cam_class_ids(4) == (1, 2, 3)
    assert cam_class_ids(1) == ()


def test_cam_paths() -> None:
    assert cam_artifact_rel("mv1", "img_01", 2) == "cam/mv1/img_01__c2.png"
    assert cam_montage_rel("img_01", 2) == "montage/img_01__cam_c2.png"


def test_overlay_cam_keeps_origin_shape_and_uses_jet() -> None:
    origin = np.full((16, 20, 3), 128, dtype=np.uint8)
    hot = overlay_cam_rgb(origin, np.ones((16, 20), dtype=np.float32), image_weight=0.2)
    cold = overlay_cam_rgb(origin, np.zeros((16, 20), dtype=np.float32), image_weight=0.2)
    assert hot.shape == origin.shape
    assert cold.shape == origin.shape
    assert int(hot[..., 0].mean()) > int(hot[..., 2].mean())
    assert int(cold[..., 2].mean()) > int(cold[..., 0].mean())


def test_empty_class_returns_zero_cam() -> None:
    model = TinySeg()
    model.eval()
    image = torch.zeros(3, 12, 12)
    pred = np.zeros((12, 12), dtype=np.uint8)
    layer = resolve_target_layer(model, slug=None, num_classes=4)
    cam = compute_gradcam(model, image, class_id=1, pred_mask=pred, target_layer=layer)
    assert cam.shape == (12, 12)
    assert float(cam.max()) == 0.0


def test_gradcam_on_inplace_relu_stays_normalized() -> None:
    torch.manual_seed(0)
    model = TinySeg()
    model.eval()
    image = torch.rand(3, 16, 16)
    pred = np.zeros((16, 16), dtype=np.uint8)
    pred[:, :8] = 1
    layer = model.features
    cam = compute_gradcam(model, image, class_id=1, pred_mask=pred, target_layer=layer)
    assert cam.shape == (16, 16)
    assert 0.0 <= float(cam.min()) <= float(cam.max()) <= 1.0
    assert float(cam.max()) > 0.0


def test_unet_target_layer_is_last_decoder_conv() -> None:
    from compare.unet import UNet

    model = UNet(in_channels=3, num_classes=4, bilinear=True)
    layer = resolve_target_layer(model, slug="unet", num_classes=4)
    assert layer is model.up4.conv.double_conv[3]
    pred = np.zeros((32, 32), dtype=np.uint8)
    pred[8:24, 8:24] = 1
    cam = compute_gradcam(
        model,
        torch.rand(3, 32, 32),
        class_id=1,
        pred_mask=pred,
        target_layer=layer,
    )
    assert cam.shape == (32, 32)
    assert float(cam.max()) >= 0.0


@pytest.mark.parametrize("slug", sorted(TARGET_LAYER_PATHS))
def test_builtin_target_layers_resolve(slug: str) -> None:
    from compare import BiSeNet, DANet, DeepLabV3Plus, NestedUNet, PSPNet, SegFormer, UNet

    constructors = {
        "unet": lambda: UNet(in_channels=3, num_classes=4, bilinear=True),
        "unetpp": lambda: NestedUNet(in_channels=3, num_classes=4),
        "deeplabv3": lambda: DeepLabV3Plus(in_channels=3, num_classes=4, backbone="resnet50", pretrained=False),
        "bisenet": lambda: BiSeNet(in_channels=3, num_classes=4, backbone_name="resnet18", pretrained=False),
        "danet": lambda: DANet(in_channels=3, num_classes=4, backbone_name="resnet18", pretrained=False, aux=False),
        "pspnet": lambda: PSPNet(in_channels=3, num_classes=4, backbone="resnet50", pretrained=False),
        "segformer": lambda: SegFormer(in_channels=3, num_classes=4),
    }
    net = constructors[slug]()
    net.eval()
    layer = resolve_target_layer(net, slug=slug, num_classes=4)
    assert isinstance(layer, nn.Conv2d)
    x = torch.zeros(1, 3, 32, 32)
    with torch.no_grad():
        y = net(x)
    if isinstance(y, (tuple, list)):
        y = y[0]
    assert tuple(y.shape[-2:]) == (32, 32)


def test_drawio_bundle_allows_cam_layers() -> None:
    check_drawio_bundle_names(
        [
            "task.json",
            "montage/a__mask.png",
            "origin/a.png",
            "cam/m/a__c1.png",
            "montage/a__cam_c1.png",
        ]
    )
