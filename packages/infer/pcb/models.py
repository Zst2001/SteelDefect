# -*- coding: utf-8 -*-
"""PCB 分割模型。M0 为随机初始化 U-Net；M1/M2 为 ResNet18 编码器。M3 仍不实现。"""

from typing import Dict

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision.models import resnet18


FUTURE_MODELS = ("deeplabv3plus_resnet18",)
TRAINABLE_MODELS = ("unet", "unet_resnet18", "unetpp_resnet18")


class UnknownModelError(ValueError):
    pass


class ConvBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=False),
            nn.Conv2d(out_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=False),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class UNet(nn.Module):
    """四次下采样的 U-Net。输入高宽须能被 16 整除。输出与输入同网格的两通道 logits。"""

    def __init__(self, in_channels: int = 3, num_classes: int = 2, base_channels: int = 32):
        super().__init__()
        c = int(base_channels)
        self.enc1 = ConvBlock(in_channels, c)
        self.enc2 = ConvBlock(c, c * 2)
        self.enc3 = ConvBlock(c * 2, c * 4)
        self.enc4 = ConvBlock(c * 4, c * 8)
        self.bottleneck = ConvBlock(c * 8, c * 16)
        self.dec4 = ConvBlock(c * 16 + c * 8, c * 8)
        self.dec3 = ConvBlock(c * 8 + c * 4, c * 4)
        self.dec2 = ConvBlock(c * 4 + c * 2, c * 2)
        self.dec1 = ConvBlock(c * 2 + c, c)
        self.head = nn.Conv2d(c, num_classes, kernel_size=1)
        self.pool = nn.MaxPool2d(2)
        self.cam_layer_name = "dec1"

    def _up(self, x: torch.Tensor, skip: torch.Tensor) -> torch.Tensor:
        x = F.interpolate(x, size=skip.shape[-2:], mode="bilinear", align_corners=False)
        return torch.cat([x, skip], dim=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        e4 = self.enc4(self.pool(e3))
        b = self.bottleneck(self.pool(e4))
        d4 = self.dec4(self._up(b, e4))
        d3 = self.dec3(self._up(d4, e3))
        d2 = self.dec2(self._up(d3, e2))
        d1 = self.dec1(self._up(d2, e1))
        return self.head(d1)


def _resnet18_bare():
    net = resnet18(weights=None)
    for module in net.modules():
        if isinstance(module, nn.ReLU):
            module.inplace = False
    return net


class ResNet18Encoder(nn.Module):
    """TorchVision ResNet18 去掉 fc。conv1 步幅 2，最细特征是输入的 1/32。"""

    def __init__(self):
        super().__init__()
        net = _resnet18_bare()
        self.conv1 = net.conv1
        self.bn1 = net.bn1
        self.relu = net.relu
        self.maxpool = net.maxpool
        self.layer1 = net.layer1
        self.layer2 = net.layer2
        self.layer3 = net.layer3
        self.layer4 = net.layer4

    def forward(self, x: torch.Tensor):
        e0 = self.relu(self.bn1(self.conv1(x)))
        x = self.maxpool(e0)
        e1 = self.layer1(x)
        e2 = self.layer2(e1)
        e3 = self.layer3(e2)
        e4 = self.layer4(e3)
        return e0, e1, e2, e3, e4


def _up_cat(x: torch.Tensor, skip: torch.Tensor) -> torch.Tensor:
    x = F.interpolate(x, size=skip.shape[-2:], mode="bilinear", align_corners=False)
    return torch.cat([x, skip], dim=1)


class UNetResNet18(nn.Module):
    """ResNet18 编码器 + U-Net 解码器。单一主头，无深监督。"""

    def __init__(self, in_channels: int = 3, num_classes: int = 2):
        super().__init__()
        if in_channels != 3:
            raise UnknownModelError("unet_resnet18 的 ImageNet 编码器只接受 3 通道")
        self.encoder = ResNet18Encoder()
        self.dec4 = ConvBlock(512 + 256, 256)
        self.dec3 = ConvBlock(256 + 128, 128)
        self.dec2 = ConvBlock(128 + 64, 64)
        self.dec1 = ConvBlock(64 + 64, 64)
        self.dec0 = ConvBlock(64, 32)
        self.head = nn.Conv2d(32, num_classes, kernel_size=1)
        self.cam_layer_name = "dec0"

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        e0, e1, e2, e3, e4 = self.encoder(x)
        d4 = self.dec4(_up_cat(e4, e3))
        d3 = self.dec3(_up_cat(d4, e2))
        d2 = self.dec2(_up_cat(d3, e1))
        d1 = self.dec1(_up_cat(d2, e0))
        d0 = self.dec0(F.interpolate(d1, size=x.shape[-2:], mode="bilinear", align_corners=False))
        return self.head(d0)


class UNetPPResNet18(nn.Module):
    """同一 ResNet18 编码器上的 U-Net++ 嵌套解码。单一主头，无深监督。"""

    def __init__(self, in_channels: int = 3, num_classes: int = 2):
        super().__init__()
        if in_channels != 3:
            raise UnknownModelError("unetpp_resnet18 的 ImageNet 编码器只接受 3 通道")
        self.encoder = ResNet18Encoder()
        channels = [64, 64, 128, 256, 512]
        self.nodes = nn.ModuleDict()
        for depth in range(1, 5):
            for index in range(0, 5 - depth):
                in_ch = channels[index] * depth + channels[index + 1]
                self.nodes["%d_%d" % (index, depth)] = ConvBlock(in_ch, channels[index])
        self.dec0 = ConvBlock(channels[0], 32)
        self.head = nn.Conv2d(32, num_classes, kernel_size=1)
        self.cam_layer_name = "dec0"

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        levels = [[feat] for feat in self.encoder(x)]
        for depth in range(1, 5):
            for index in range(0, 5 - depth):
                parts = list(levels[index])
                below = levels[index + 1][depth - 1]
                below = F.interpolate(below, size=parts[0].shape[-2:], mode="bilinear", align_corners=False)
                parts.append(below)
                levels[index].append(self.nodes["%d_%d" % (index, depth)](torch.cat(parts, dim=1)))
        full = F.interpolate(levels[0][4], size=x.shape[-2:], mode="bilinear", align_corners=False)
        return self.head(self.dec0(full))


def known_model_names():
    return list(TRAINABLE_MODELS) + list(FUTURE_MODELS)


def build_model(name: str, num_classes: int = 2, in_channels: int = 3, **kwargs) -> nn.Module:
    if name in FUTURE_MODELS:
        raise UnknownModelError("%s 已登记，本阶段不构建、不下载、不训练" % name)
    if name == "unet":
        extra = set(kwargs) - {"base_channels"}
        if extra:
            raise UnknownModelError("unet 不接受参数: %s" % ", ".join(sorted(extra)))
        return UNet(in_channels=in_channels, num_classes=num_classes, base_channels=int(kwargs.get("base_channels", 32)))
    if name == "unet_resnet18":
        if kwargs:
            raise UnknownModelError("unet_resnet18 不接受构造参数: %s" % ", ".join(sorted(kwargs)))
        return UNetResNet18(in_channels=in_channels, num_classes=num_classes)
    if name == "unetpp_resnet18":
        if kwargs:
            raise UnknownModelError("unetpp_resnet18 不接受构造参数: %s" % ", ".join(sorted(kwargs)))
        return UNetPPResNet18(in_channels=in_channels, num_classes=num_classes)
    raise UnknownModelError("未知模型: %s。当前可训练: %s" % (name, ", ".join(TRAINABLE_MODELS)))


def count_parameters(model: nn.Module) -> Dict[str, int]:
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return {"params": int(total), "trainable_params": int(trainable)}

