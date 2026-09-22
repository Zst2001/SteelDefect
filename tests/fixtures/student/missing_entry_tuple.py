import torch
import torch.nn as nn


class TinyBlock(nn.Module):
    def __init__(self, in_planes):
        super().__init__()
        self.conv = nn.Conv2d(in_planes, in_planes, 1)

    def forward(self, x):
        return self.conv(x)


class DemoNet(nn.Module):
    def __init__(self, num_classes, pretrained_backbone=False):
        super().__init__()
        self.stem = nn.Conv2d(3, 8, 3, padding=1)
        self.head = nn.Conv2d(8, num_classes, 1)
        self.aux = nn.Conv2d(8, num_classes, 1)
        _ = pretrained_backbone

    def forward(self, x):
        feat = torch.relu(self.stem(x))
        s1 = self.head(feat)
        s2 = self.aux(feat)
        return s1, s2
