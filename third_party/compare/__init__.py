"""CPU baseline models only. Do not import the research-repo compare/__init__.py
(it pulls Mamba / Mask2Former and will fail on a CPU website machine).
"""

from .unet import UNet
from .deeplabv3_plus import DeepLabV3Plus
from .unet_plus_plus import NestedUNet

__all__ = ["UNet", "DeepLabV3Plus", "NestedUNet"]
