from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PreprocessSpec:
    """Must be persisted on each task. Do not silently change size."""

    height: int = 200
    width: int = 200
    apply_clahe: bool = True
    sp_threshold: float = 0.02
    dataset: str = "neu"
    num_classes: int = 4
    in_channels: int = 3

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> PreprocessSpec:
        if not data:
            return cls()
        return cls(
            height=int(data.get("height", 200)),
            width=int(data.get("width", 200)),
            apply_clahe=bool(data.get("apply_clahe", True)),
            sp_threshold=float(data.get("sp_threshold", 0.02)),
            dataset=str(data.get("dataset", "neu")),
            num_classes=int(data.get("num_classes", 4)),
            in_channels=int(data.get("in_channels", 3)),
        )

    @property
    def size(self) -> tuple[int, int]:
        return (self.height, self.width)


NEU_DEFAULT = PreprocessSpec()

# 模型中心 / 对比 / 评测 / 公开演示共用的 CPU 内置 baseline。
# 演示与快速对比每次仍只可选 1–3 个；正式评测可全选当前内置集合。学生模型永远不进 F-DEMO。
BUILTIN_SLUGS = (
    "unet",
    "deeplabv3",
    "unetpp",
    "bisenet",
    "danet",
    "pspnet",
    "segformer",
)
DEMO_MODEL_SLUGS = BUILTIN_SLUGS
COMPARE_BASELINE_LIMIT = 3
EVAL_BASELINE_LIMIT = len(BUILTIN_SLUGS)
DEMO_CATALOG_KIND = "demo_samples"
DEMO_DISCLAIMER = "公开演示 / 预备样例 / 不代表测试集性能"

BUILTIN_DISPLAY_NAMES = {
    "unet": "UNet",
    "deeplabv3": "DeepLabV3+",
    "unetpp": "UNet++",
    "bisenet": "BiSeNet",
    "danet": "DANet",
    "pspnet": "PSPNet",
    "segformer": "SegFormer",
}

BUILTIN_WEIGHT_FILES = {
    "unet": "baselines/neu/best_unet.pth",
    "deeplabv3": "baselines/neu/best_deeplabv3.pth",
    "unetpp": "baselines/neu/best_unetpp.pth",
    "bisenet": "baselines/neu/best_bisenet.pth",
    "danet": "baselines/neu/best_danet.pth",
    "pspnet": "baselines/neu/best_pspnet.pth",
    "segformer": "baselines/neu/best_segformer.pth",
}


def builtin_sort_key(slug: str) -> int:
    """Keep UNet / DeepLabV3+ / UNet++ first so compare/eval default 1–3 stay unchanged."""
    try:
        return BUILTIN_SLUGS.index(slug)
    except ValueError:
        return len(BUILTIN_SLUGS)


NEU_CLASS_MAP = {
    "0": "背景",
    "1": "夹渣",
    "2": "斑块",
    "3": "划痕",
}

NEU_LEGEND = [
    {"id": 1, "name": "夹渣", "color": "#e23d2e"},
    {"id": 2, "name": "斑块", "color": "#2f9e44"},
    {"id": 3, "name": "划痕", "color": "#2f6fed"},
]

BATCH_REFERENCE_SCOPE = "batch_reference"
BATCH_REFERENCE_DISCLAIMER = "快速对比参考指标，不代表完整测试集性能"
OFFICIAL_SPLIT_SCOPE = "official_split"
OFFICIAL_SPLIT_DISCLAIMER = (
    "本数据版本全量指标，与训练脚本同一套 4 类 mIoU。"
    "当前固定集为 NEU-20，不是论文完整 test split。"
)

# OpenCV BGR colours for TP/FP/FN/swap maps (mill orange + NEU palette).
ERROR_COLORS_BGR = {
    "tn": (0, 0, 0),
    "tp": (68, 158, 47),
    "fp": (38, 92, 196),
    "fn": (237, 111, 47),
    "swap": (0, 220, 255),
}

ERROR_LEGEND = [
    {"id": "tp", "name": "正确检出", "color": "#2f9e44"},
    {"id": "fp", "name": "误报", "color": "#c45c26"},
    {"id": "fn", "name": "漏检", "color": "#2f6fed"},
    {"id": "swap", "name": "类别错分", "color": "#ffdc00"},
]
