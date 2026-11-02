# -*- coding: utf-8 -*-
"""把 256 网格上的两通道 logits 裁回 220，再算缺陷概率和掩码。"""

import numpy as np
import torch


class ContractError(ValueError):
    pass


def crop_source(logits):
    if logits.ndim != 4 or tuple(logits.shape[1:]) != (2, 256, 256):
        raise ContractError("还原时期望 B×2×256×256 logits，当前 %s" % (tuple(logits.shape),))
    return logits[:, :, 18:238, 18:238]


def mask_and_probability(logits):
    restored = crop_source(logits)
    probability = torch.softmax(restored, dim=1)[0, 1]
    mask = restored.argmax(dim=1)[0].to(torch.uint8)
    if tuple(mask.shape) != (220, 220) or tuple(probability.shape) != (220, 220):
        raise ContractError("输出没有回到 220×220")
    return mask, probability


def to_numpy(mask, probability):
    return mask.detach().cpu().numpy(), probability.detach().cpu().numpy().astype(np.float32)
