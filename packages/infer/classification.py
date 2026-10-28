"""Trusted NEU-CLS builtins. No student Python, training, downloads or API imports.

Catalog reads use only the standard library. Torch/TorchVision are imported only
by the worker/explicit offline validation. Administrator-owned assets are checked
again before every load; one invocation holds only one model, with no model cache.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from importlib.metadata import version
import json
import math
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "mobilenet_v3_small"
MODEL_NAMES = {
    DEFAULT_MODEL: "MobileNetV3-Small", "resnet18": "ResNet18",
    "efficientnet_b0": "EfficientNet-B0", "resnet50": "ResNet50",
    "densenet121": "DenseNet121", "convnext_tiny": "ConvNeXt-Tiny",
}
MODEL_SLUGS = tuple(MODEL_NAMES)
DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "assets/classification/neu_cls_v1"
CLASS_HASH = "df62ab880bf84cf7ba81ca113a8eb9f135864ba6e3a9d5c4e7f4732eb764d46c"
PREPROCESS_HASH = "e4a62a818de5ac98bdc714a98b6748a7d070443cd055d4104c07351341a3bbe3"
HEADS = {"mobilenet_v3_small": ("classifier", 3), "resnet18": ("fc", None),
         "efficientnet_b0": ("classifier", 1), "resnet50": ("fc", None),
         "densenet121": ("classifier", None), "convnext_tiny": ("classifier", 2)}
THREADS = 2
MAX_BATCH_IMAGES = 50
MAX_PIXELS = 16_000_000
MAX_RESIZED_PIXELS = 224 * 896


class ClassificationError(ValueError):
    """Public message is deliberately free of local paths/tracebacks."""


def canonical_hash(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict:
    if path.stat().st_size > 64 * 1024:
        raise ClassificationError("分类模型配置文件过大")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ClassificationError("分类模型配置格式不合法")
    return result


def runtime_versions() -> dict[str, str]:
    return {name: version(name) for name in ("torch", "torchvision", "Pillow")}


@dataclass(frozen=True)
class Asset:
    slug: str
    name: str
    classes: list[dict]
    preprocess: dict
    spec: dict
    weight_path: Path
    weight_sha256: str
    classes_hash: str
    preprocess_hash: str
    protocol_hash: str
    asset_hash: str
    param_count: int


def inspect_asset(slug: str, root: Path | None = None, *, require_validated: bool = True) -> Asset:
    if slug not in MODEL_NAMES:
        raise ClassificationError("不支持的内置分类模型")
    base = Path(root or DEFAULT_ROOT).resolve()
    folder = base / slug
    try:
        if folder.is_symlink() or folder.resolve().parent != base:
            raise ClassificationError("分类模型目录无效")
        files = {name: folder / name for name in
                 ("classes.json", "preprocess.json", "model_spec.json", "metadata.json", "weights.pth")}
        if any(p.is_symlink() or p.resolve().parent != folder.resolve() for p in files.values()):
            raise ClassificationError("分类模型文件路径无效")
        classes, preprocess, spec, meta = (_json(files[name]) for name in
                                         ("classes.json", "preprocess.json", "model_spec.json", "metadata.json"))
        ch, ph = canonical_hash(classes), canonical_hash(preprocess)
        if ch != CLASS_HASH or ch != meta.get("classes_hash"):
            raise ClassificationError("分类类别映射与审定协议不一致")
        if ph != PREPROCESS_HASH or ph != meta.get("preprocess_hash"):
            raise ClassificationError("分类预处理与审定协议不一致")
        entries = classes.get("classes", [])
        if (classes.get("num_classes") != 6 or classes.get("normal_class") is not False
                or [c.get("id") for c in entries] != list(range(6))
                or [c.get("key") for c in entries] != meta.get("class_keys")
                or classes.get("class_to_idx") != {c["key"]: c["id"] for c in entries}):
            raise ClassificationError("分类类别顺序无效")
        if (spec.get("model_name") != slug or spec.get("builder") != slug
                or meta.get("model_name") != slug or spec.get("framework") != "torchvision"
                or spec.get("input") != [3, 224, 224] or spec.get("output") != ["B", 6]
                or spec.get("num_classes") != 6 or meta.get("num_classes") != 6
                or (spec.get("head_attr"), spec.get("head_index")) != HEADS[slug]
                or meta.get("task") != "classification"):
            raise ClassificationError("分类网络声明与已审定结构不一致")
        weights = files["weights.pth"]
        if not 1 < weights.stat().st_size <= 150 * 1024 * 1024:
            raise ClassificationError("分类权重大小无效")
        wh = file_hash(weights)
        if wh != meta.get("weights_sha256"):
            raise ClassificationError("分类权重 SHA-256 校验失败")
        protocol = canonical_hash({"classes": ch, "preprocess": ph})
        fingerprint = canonical_hash({"classes": ch, "preprocess": ph, "weights": wh,
                                      "spec": canonical_hash(spec), "metadata": canonical_hash(meta)})
        params = meta.get("params")
        if type(params) is not int or params <= 0:
            raise ClassificationError("分类参数量声明无效")
        if require_validated:
            receipt_path = folder / "validated.json"
            if receipt_path.is_symlink() or receipt_path.resolve().parent != folder.resolve():
                raise ClassificationError("分类校验记录路径无效")
            receipt = _json(receipt_path)
            if (receipt.get("ok") is not True or receipt.get("asset_hash") != fingerprint
                    or receipt.get("runtime") != runtime_versions()
                    or receipt.get("shape_b1") != [1, 6] or receipt.get("shape_b2") != [2, 6]):
                raise ClassificationError("分类模型需要在当前 CPU 环境重新校验")
        return Asset(slug, MODEL_NAMES[slug], entries, preprocess, spec, weights,
                     wh, ch, ph, protocol, fingerprint, params)
    except ClassificationError:
        raise
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, ImportError) as exc:
        raise ClassificationError("分类资产缺失或配置无法读取，请联系管理员校验") from exc


def catalog(root: Path | None = None) -> list[dict]:
    result = []
    for slug, name in MODEL_NAMES.items():
        row = {"slug": slug, "name": name, "available": False, "status": "unavailable",
               "reason": None, "param_count": None}
        try:
            item = inspect_asset(slug, root)
            row.update(available=True, status="available", param_count=item.param_count,
                       weight_sha256=item.weight_sha256, classes_hash=item.classes_hash,
                       preprocess_hash=item.preprocess_hash, protocol_hash=item.protocol_hash,
                       classes=item.classes)
        except ClassificationError as exc:
            row["reason"] = str(exc)
        result.append(row)
    return result


def build_preprocess(asset: Asset):
    from torchvision import transforms
    from torchvision.transforms import InterpolationMode
    # Export uses Resize(int), i.e. short edge=224, aspect preserved. No crop,
    # stretch, augmentation, CLAHE or segmentation normalization is introduced.
    return transforms.Compose([
        transforms.Grayscale(num_output_channels=3),
        transforms.Resize(asset.preprocess["resize"], interpolation=InterpolationMode.BILINEAR,
                          antialias=asset.preprocess["antialias"]),
        transforms.ToTensor(),
        transforms.Normalize(asset.preprocess["normalize_mean"], asset.preprocess["normalize_std"]),
    ])


def image_tensor(path: Path, asset: Asset):
    from PIL import Image, UnidentifiedImageError
    try:
        with Image.open(path) as image:
            w, h = image.size
            if (image.format not in {"PNG", "JPEG", "BMP", "TIFF"}
                    or getattr(image, "n_frames", 1) != 1
                    or image.mode not in {"L", "RGB", "RGBA", "P"}
                    or min(w, h) < 1 or w * h > MAX_PIXELS
                    or 224 * int(224 * max(w, h) / min(w, h)) > MAX_RESIZED_PIXELS):
                raise ClassificationError("图像格式、尺寸或长宽比不受支持")
            image.load()
            return build_preprocess(asset)(image).unsqueeze(0)
    except ClassificationError:
        raise
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ClassificationError("图像损坏或无法读取") from exc


def load_model(asset: Asset):
    import torch
    from torchvision import models
    torch.set_num_threads(THREADS)
    builders = {slug: getattr(models, slug) for slug in MODEL_SLUGS}
    try:
        module = builders[asset.slug](weights=None, num_classes=6)
        # Check the exact stream deserialized, not only an earlier pathname read.
        with asset.weight_path.open("rb") as stream:
            digest = sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
            if digest.hexdigest() != asset.weight_sha256:
                raise ClassificationError("分类权重在加载前已变更")
            stream.seek(0)
            state = torch.load(stream, map_location="cpu", weights_only=True)
        if not isinstance(state, dict) or not state or any(
                not isinstance(k, str) or not isinstance(v, torch.Tensor) for k, v in state.items()):
            raise ClassificationError("分类权重不是完整 state_dict")
        module.load_state_dict(state, strict=True)
        if sum(p.numel() for p in module.parameters()) != asset.param_count:
            raise ClassificationError("分类参数量与导出声明不一致")
        module.eval()
        return module
    except ClassificationError:
        raise
    except Exception as exc:
        raise ClassificationError("分类权重严格加载失败") from exc


def validate_logits(logits, batch: int) -> None:
    import torch
    if (not isinstance(logits, torch.Tensor) or not torch.is_floating_point(logits)
            or tuple(logits.shape) != (batch, 6) or not bool(torch.isfinite(logits).all())):
        raise ClassificationError("分类输出必须为有限浮点 B×6 logits")


def prediction_rows(logits, classes: list[dict]) -> list[dict]:
    import torch
    validate_logits(logits, logits.shape[0] if isinstance(logits, torch.Tensor) and logits.ndim else 0)
    probabilities = torch.softmax(logits.double(), dim=1).cpu().tolist()
    rows = []
    for scores in probabilities:
        if any(not math.isfinite(x) for x in scores):
            raise ClassificationError("分类得分必须为有限数值")
        ranked = sorted(range(6), key=lambda idx: (-scores[idx], idx))
        def entry(idx):
            return {"class_id": idx, "key": classes[idx]["key"], "display_zh": classes[idx]["display_zh"],
                    "score": float(scores[idx])}
        rows.append({**entry(ranked[0]), "scores": scores, "topk": [entry(i) for i in ranked[:3]]})
    return rows


def predict_images(slug: str, paths: list[Path], root: Path | None = None) -> list[dict]:
    if not paths or len(paths) > MAX_BATCH_IMAGES:
        raise ClassificationError("分类任务需要 1–50 张图像")
    import torch
    asset = inspect_asset(slug, root)
    module = load_model(asset)
    rows = []
    # Sequential batch=1 accommodates exported Resize(int) on rectangular input,
    # bounds activation memory, and never loads all six networks concurrently.
    with torch.inference_mode():
        for path in paths:
            tensor = image_tensor(Path(path), asset)
            logits = module(tensor)
            validate_logits(logits, 1)
            rows.extend(prediction_rows(logits, asset.classes))
    del module
    return rows


def classification_metrics(true_ids: list[int] | None, predicted_ids: list[int]) -> dict:
    if true_ids is None:
        return {"available": False}
    if (not true_ids or len(true_ids) != len(predicted_ids)
            or any(type(x) is not int or not 0 <= x < 6 for x in true_ids + predicted_ids)):
        raise ClassificationError("分类指标需要完整合法的逐图标签")
    matrix = [[0 for _ in range(6)] for _ in range(6)]
    for target, pred in zip(true_ids, predicted_ids):
        matrix[target][pred] += 1
    f1 = []
    for k in range(6):
        tp = matrix[k][k]
        denominator = sum(matrix[k]) + sum(row[k] for row in matrix)
        f1.append(2 * tp / denominator if denominator else 0.0)
    return {"available": True, "n": len(true_ids),
            "accuracy": sum(matrix[k][k] for k in range(6)) / len(true_ids),
            "macro_f1": sum(f1) / 6, "confusion_matrix": matrix,
            "class_ids": list(range(6)), "macro_f1_policy": "all_6_classes_zero_division_0"}
