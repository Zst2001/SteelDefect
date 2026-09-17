"""Mask colour maps extracted from code/eval.py (do not import eval.py).

Colours are OpenCV BGR so saved PNGs match the paper labels:
NEU: 1=Inclusion red, 2=Patch green, 3=Scratch blue.
"""

from typing import Dict, List

import numpy as np


def get_color_map(dataset: str, num_classes: int) -> Dict[int, List[int]]:
    if dataset == "neu":
        return {0: [0, 0, 0], 1: [0, 0, 255], 2: [0, 255, 0], 3: [255, 0, 0]}
    if dataset == "magnetic":
        return {
            0: [0, 0, 0],
            1: [255, 0, 255],
            2: [0, 255, 255],
            3: [255, 165, 0],
            4: [255, 0, 165],
            5: [0, 255, 165],
        }
    if dataset == "bsdata":
        return {0: [0, 0, 0], 1: [0, 255, 0]}
    if dataset in ("steel_pipe", "severstal"):
        return {
            0: [0, 0, 0],
            1: [0, 0, 255],
            2: [0, 255, 0],
            3: [255, 0, 0],
            4: [0, 255, 255],
        }
    palette = [
        [0, 0, 0],
        [0, 0, 255],
        [0, 255, 0],
        [255, 0, 0],
        [255, 255, 0],
        [255, 0, 255],
    ]
    return {index: palette[index % len(palette)] for index in range(num_classes)}


def colorize_mask(mask: np.ndarray, color_map: Dict[int, List[int]]) -> np.ndarray:
    coloured = np.zeros((*mask.shape, 3), dtype=np.uint8)
    for class_id, colour in color_map.items():
        coloured[mask == class_id] = colour
    return coloured
