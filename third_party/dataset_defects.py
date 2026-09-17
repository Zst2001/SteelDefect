import os
import glob
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset


IMG_EXTENSIONS = [".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"]


def is_image_file(filename: str) -> bool:
    filename_lower = filename.lower()
    return any(filename_lower.endswith(ext) for ext in IMG_EXTENSIONS)


def clahe_lab(rgb: np.ndarray, clip_limit: float = 2.0, tile_grid_size: Tuple[int, int] = (8, 8)) -> np.ndarray:
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
    l = clahe.apply(l)
    lab = cv2.merge((l, a, b))
    rgb_enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    return rgb_enhanced


def detect_and_filter_salt_pepper(rgb: np.ndarray, threshold_ratio: float = 0.02) -> np.ndarray:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    total = gray.size
    num_min = np.count_nonzero(gray == 0)
    num_max = np.count_nonzero(gray == 255)
    ratio = (num_min + num_max) / float(total)
    if ratio >= threshold_ratio:
        # 使用中值滤波抑制椒盐噪声
        filtered = cv2.medianBlur(rgb, ksize=3)
        return filtered
    return rgb


def random_flip_rotate(img: np.ndarray, mask: np.ndarray, p_flip: float = 0.5) -> Tuple[np.ndarray, np.ndarray]:
    # 随机水平/垂直翻转
    if np.random.rand() < p_flip:
        img = np.flip(img, axis=1).copy()
        mask = np.flip(mask, axis=1).copy()
    if np.random.rand() < p_flip:
        img = np.flip(img, axis=0).copy()
        mask = np.flip(mask, axis=0).copy()
    # 随机 0/90/180/270 旋转
    k = np.random.choice([0, 1, 2, 3])
    if k > 0:
        img = np.rot90(img, k, axes=(0, 1)).copy()
        mask = np.rot90(mask, k, axes=(0, 1)).copy()
    return img, mask


def resize_pair(img: np.ndarray, mask: np.ndarray, size: Tuple[int, int]) -> Tuple[np.ndarray, np.ndarray]:
    h, w = size
    img_r = cv2.resize(img, (w, h), interpolation=cv2.INTER_LINEAR)
    mask_r = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
    return img_r, mask_r


class DefectDataset(Dataset):
    """缺陷分割数据集

    期望目录结构：
    - images_dir: 存放 RGB 原图
    - masks_dir:  存放掩膜，单通道，像素值为 {0,1,2,3}

    也可以通过 file_list 指定文件名（不含扩展名）子集。

    对于原始掩膜为 0/255 的二分类数据集，可设置 binary_mask=True，
    将所有非零像素转换为前景类别 1。
    """

    def __init__(
        self,
        images_dir: str,
        masks_dir: str,
        size: Tuple[int, int] = (200, 200),
        augment: bool = True,
        apply_clahe: bool = True,
        sp_threshold: float = 0.02,
        file_list: Optional[List[str]] = None,
        transform: Optional[Callable] = None,
        num_classes: int = 4,
        binary_mask: bool = False,
    ) -> None:
        super().__init__()
        self.images_dir = images_dir
        self.masks_dir = masks_dir
        self.size = size
        self.augment = augment
        self.apply_clahe = apply_clahe
        self.sp_threshold = sp_threshold
        self.transform = transform
        self.num_classes = num_classes
        self.binary_mask = binary_mask

        if file_list is None:
            imgs = []
            for ext in IMG_EXTENSIONS:
                imgs.extend(glob.glob(os.path.join(images_dir, f"*{ext}")))
            imgs = sorted(imgs)
            self.ids = [os.path.splitext(os.path.basename(p))[0] for p in imgs]
        else:
            self.ids = file_list

        if len(self.ids) == 0:
            raise RuntimeError(f"No images found in {images_dir}")

    def __len__(self) -> int:
        return len(self.ids)

    def _load_pair(self, sample_id: str) -> Tuple[np.ndarray, np.ndarray]:
        img_path = None
        for ext in IMG_EXTENSIONS:
            p = os.path.join(self.images_dir, sample_id + ext)
            if os.path.exists(p):
                img_path = p
                break
        if img_path is None:
            raise FileNotFoundError(f"Image not found for id={sample_id}")

        # 掩膜优先尝试常见扩展
        mask_path = None
        for ext in [".png", ".bmp", ".jpg", ".jpeg", ".tif", ".tiff"]:
            p = os.path.join(self.masks_dir, sample_id + ext)
            if os.path.exists(p):
                mask_path = p
                break
        if mask_path is None:
            raise FileNotFoundError(f"Mask not found for id={sample_id}")

        # BGR -> RGB
        img_bgr = cv2.imread(img_path, cv2.IMREAD_COLOR)
        if img_bgr is None:
            raise RuntimeError(f"Failed to read image: {img_path}")
        img = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

        mask_any = cv2.imread(mask_path, cv2.IMREAD_UNCHANGED)
        if mask_any is None:
            raise RuntimeError(f"Failed to read mask: {mask_path}")

        # 将彩色掩膜映射回类别索引：
        # 约定颜色（来源于 convert_masks_to_colors.py）：
        # 背景=黑(0,0,0)，1=红(255,0,0)，2=绿(0,255,0)，3=蓝(0,0,255)
        # 注意：cv2 读入为 BGR 顺序。
        if mask_any.ndim == 3:
            if mask_any.shape[2] == 4:
                mask_bgr = cv2.cvtColor(mask_any, cv2.COLOR_BGRA2BGR)
            else:
                mask_bgr = mask_any

            # 背景判断：三通道全为 0 的像素为 0 类
            is_bg = (mask_bgr[:, :, 0] == 0) & (mask_bgr[:, :, 1] == 0) & (mask_bgr[:, :, 2] == 0)

            # 对非背景像素，用通道最大值的位置区分 B/G/R -> 3/2/1
            argmax_c = np.argmax(mask_bgr, axis=2)  # 0=B,1=G,2=R
            mapping = np.array([3, 2, 1], dtype=np.uint8)
            mask_idx = mapping[argmax_c]
            mask_idx[is_bg] = 0
            mask = mask_idx.astype(np.uint8)
        else:
            # 单通道灰度掩膜可直接作为类别索引；二分类 0/255 掩膜需先转换为 0/1。
            mask = (mask_any > 0).astype(np.uint8) if self.binary_mask else mask_any.astype(np.uint8)

        return img, mask

    def __getitem__(self, index: int):
        sample_id = self.ids[index]
        img, mask = self._load_pair(sample_id)

        # 噪声检测与过滤（椒盐）
        img = detect_and_filter_salt_pepper(img, threshold_ratio=self.sp_threshold)

        # CLAHE 增强
        if self.apply_clahe:
            img = clahe_lab(img)

        # 基础几何增强
        if self.augment:
            img, mask = random_flip_rotate(img, mask)

        # 尺寸归一化到 200x200
        img, mask = resize_pair(img, mask, self.size)

        # 额外自定义变换（如归一化等）
        if self.transform is not None:
            img, mask = self.transform(img, mask)

        # 转 Tensor
        img = img.astype(np.float32) / 255.0
        img_t = torch.from_numpy(img).permute(2, 0, 1).contiguous()  # C,H,W
        # 将超出类别范围的像素（如 255）映射为背景类 0，避免损失函数越界
        mask = mask.astype(np.int64)
        if self.num_classes is not None:
            invalid = mask >= self.num_classes
            if invalid.any():
                mask[invalid] = 0

        mask_t = torch.from_numpy(mask)  # H,W (Long)

        return {
            "id": sample_id,
            "image": img_t,
            "mask": mask_t,
        }

