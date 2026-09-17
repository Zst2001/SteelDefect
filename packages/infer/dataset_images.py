from __future__ import annotations

from pathlib import Path
from typing import List

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

from infer.paths import ensure_third_party
from infer.spec import PreprocessSpec

ensure_third_party()

from dataset_defects import (  # noqa: E402
    IMG_EXTENSIONS,
    clahe_lab,
    detect_and_filter_salt_pepper,
    is_image_file,
)


def read_rgb(path: str | Path) -> np.ndarray:
    image_bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise RuntimeError(f"Failed to read image: {path}")
    return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)


def preprocess_rgb(image_rgb: np.ndarray, spec: PreprocessSpec) -> torch.Tensor:
    image = detect_and_filter_salt_pepper(image_rgb, threshold_ratio=spec.sp_threshold)
    if spec.apply_clahe:
        image = clahe_lab(image)
    height, width = spec.size
    image = cv2.resize(image, (width, height), interpolation=cv2.INTER_LINEAR)
    tensor = torch.from_numpy(image.astype(np.float32) / 255.0).permute(2, 0, 1).contiguous()
    return tensor


class ImagesOnlyDataset(Dataset):
    """Inference dataset that does not require masks (DefectDataset always does)."""

    def __init__(
        self,
        image_paths: List[Path],
        sample_keys: List[str],
        spec: PreprocessSpec,
    ) -> None:
        if len(image_paths) != len(sample_keys):
            raise ValueError("image_paths and sample_keys length mismatch")
        if not image_paths:
            raise RuntimeError("No images for inference")
        self.image_paths = [Path(p) for p in image_paths]
        self.sample_keys = list(sample_keys)
        self.spec = spec

    def __len__(self) -> int:
        return len(self.image_paths)

    def __getitem__(self, index: int) -> dict:
        path = self.image_paths[index]
        rgb = read_rgb(path)
        orig_h, orig_w = rgb.shape[:2]
        image = preprocess_rgb(rgb, self.spec)
        return {
            "id": self.sample_keys[index],
            "image": image,
            "origin_rgb": rgb,
            "orig_h": orig_h,
            "orig_w": orig_w,
            "path": str(path),
        }


def list_image_files(directory: Path) -> list[Path]:
    files = [p for p in sorted(directory.iterdir()) if p.is_file() and is_image_file(p.name)]
    return files


def stem_key(path: Path) -> str:
    return path.stem
