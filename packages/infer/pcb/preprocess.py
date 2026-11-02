# -*- coding: utf-8 -*-
"""220×220 RGB 到 1×3×256×256。不读取数据集，不使用 CLAHE 或 ImageNet mean/std。"""

import numpy as np
import torch


class ContractError(ValueError):
    pass


def prepare_canvas(image):
    array = np.asarray(image)
    if array.ndim != 3 or array.shape != (220, 220, 3) or array.dtype != np.uint8:
        raise ContractError("只接受 220×220 的 RGB uint8，当前形状 %s dtype %s" % (getattr(array, "shape", None), getattr(array, "dtype", None)))
    padded = np.pad(array, ((18, 18), (18, 18), (0, 0)), mode="constant", constant_values=0)
    tensor = torch.from_numpy(padded).permute(2, 0, 1).float().div(255.0).unsqueeze(0)
    if tuple(tensor.shape) != (1, 3, 256, 256):
        raise ContractError("预处理结果不是 1×3×256×256")
    return tensor
