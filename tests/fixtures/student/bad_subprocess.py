import subprocess
import torch.nn as nn


def build_model(num_classes: int, in_channels: int = 3, **kwargs):
    subprocess.getoutput("echo blocked")
    return nn.Conv2d(in_channels, num_classes, 1)
