import torch
import torch.nn as nn


class TinySeg(nn.Module):
    def __init__(self, num_classes: int, in_channels: int = 3, **kwargs):
        super().__init__()
        self.stem = nn.Conv2d(in_channels, 8, kernel_size=3, padding=1)
        self.head = nn.Conv2d(8, num_classes, kernel_size=1)

    def forward(self, x):
        return self.head(torch.relu(self.stem(x)))


def build_model(num_classes: int, in_channels: int = 3, **kwargs):
    return TinySeg(num_classes=num_classes, in_channels=in_channels)
