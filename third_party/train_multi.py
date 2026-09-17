import os
import argparse
from typing import Tuple, Dict, Any
import time
import random
import csv
import json
import numpy as np

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from compare import (UNet, NestedUNet, DeepLabV3Plus, PSPNet, SegFormer, Mask2Former, UNetAxial,
                    SegFormerImproved, SETR, SETR_PUP, ConvNeXtSegmentation, EfficientNetV2Segmentation,
                    FastSCNN, FastSCNNPlus, BiSeNet, BiSeNetV2, CCNet, DANet, MoESteelUnet,
                    MoESteelUNetPDF, MoESteelUNetPDFFigure5, MoESteelUNetLast,
                    FDSNet, A3Net)
from compare.moe_ablation_config import (
    MOE_ABLATION_CONFIGS,
    LAST_MOE_ABLATION_CONFIGS,
    ALL_FORMAL_MOE_ABLATION_MODELS,
)
from compare.moesteelunet_pdf import EXPERT_ORDER as PDF_EXPERT_ORDER, expert_specialization_loss
from MoEMamba1 import MoESteelUNetMamba1
from MoEMamba11 import MoESteelUNetMamba11
from moemambacnn import MoESteelUNetMambaCNN
from xiaorongmoemambacnn import (
    FRAMEWORK_ABLATION_CONFIGS,
    FRAMEWORK_ABLATION_MODELS,
    HOMOGENEOUS_EXPERT_HIDDEN_CHANNELS,
    MorphoMoEFrameworkAblation,
    build_framework_ablation_model,
    get_frozen_lpdm_config,
    write_framework_parameter_report,
)
from dataset_defects import DefectDataset
from dataset_magnetic_tile import MagneticTileDataset
from dataset_severstal import SeverstalDataset
from utils_losses_metrics import DiceLoss, compute_confusion_matrix, metrics_from_confmat






from ablation import UNetDepthwise,MultiUNet


def get_num_classes_for_dataset(dataset: str) -> int:
    """Return the fixed semantic-class count used by each supported dataset."""
    return {
        "neu": 4,
        "magnetic": 6,
        "severstal": 4,
        "bsdata": 2,
    }[dataset]

def parse_args():
    p = argparse.ArgumentParser(description="Multi-model training: UNet, UNet++, UNetAxial")
    p.add_argument("--dataset", type=str, default="magnetic", choices=["neu", "magnetic", "severstal", "bsdata"],
                   help="选择数据集: neu(NEU_Seg), magnetic(Magnetic-tile), severstal(Severstal Steel), bsdata(BSData)")
    p.add_argument("--data_root", type=str, default="/root/My/data", help="数据根目录")
    p.add_argument("--train_split", type=str, default="train")
    p.add_argument("--test_split", type=str, default="test")
    p.add_argument("--epochs", type=int, default=200)
    p.add_argument("--batch_size", type=int, default=16)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--optimizer", type=str, default="adamw", choices=["adam", "adamw"],
                   help="优化器类型；论文版实验使用 adam")
    p.add_argument("--weight_decay", type=float, default=1e-4,
                   help="优化器权重衰减；论文版实验使用 1e-5")
    p.add_argument("--early_stopping_patience", type=int, default=0,
                   help="验证集 mIoU 连续多少轮不提升后早停；0 表示禁用")
    p.add_argument("--num_classes", type=int, default=4)
    p.add_argument("--num_workers", type=int, default=4)
    p.add_argument("--device", type=str, default="cuda" if torch.cuda.is_available() else "cpu")
    p.add_argument("--save_dir", type=str, default="/root/My/code/models")
    p.add_argument(
        "--run_name", type=str, default=None,
        help=("Optional run directory below <save_dir>/<dataset>. Use it to keep "
              "checkpoints and reports from separate runs from overwriting each other."),
    )
    p.add_argument("--no_augment", action="store_true")
    p.add_argument("--no_clahe", action="store_true")
    p.add_argument("--sp_threshold", type=float, default=0.02)
    p.add_argument("--random_seed", type=int, default=42, help="随机种子")
    p.add_argument(
        "--pdf_spec_loss_weight", type=float, default=0.0,
        help=("论文版 MoESteelUNet 的专家专门化损失权重。默认 0 表示不启用；"
              "启用时必须同时提供 --pdf_class_to_expert。"),
    )
    p.add_argument(
        "--pdf_class_to_expert", type=str, default=None,
        help=("论文版 MoESteelUNet 的语义类别到专家映射，例如 "
              "'1:sde,2:rde,3:cse'。背景类别 0 不应映射。"),
    )
    p.add_argument("--scheduler", type=str, default="plateau", choices=["plateau", "cosine", "step", "exponential"],
                   help="学习率调度器类型")
    p.add_argument("--lr_patience", type=int, default=8, help="ReduceLROnPlateau的patience")
    p.add_argument("--lr_factor", type=float, default=0.8, help="学习率衰减因子")
    p.add_argument("--min_lr", type=float, default=1e-6, help="最小学习率")
    p.add_argument(
        "--a3net_pretrained_backbone", action="store_true",
        help="为 A3Net 加载原项目使用的 ImageNet Res2Net-50 预训练骨干（首次运行会下载权重）",
    )
    p.add_argument("--models", nargs="+", default=
        [
        # 消融实验    
        # "UNetDepthwise",
         # "MultiUNet",   
        "danet",
            
        # 消融实验      
        "unet", 
        "unetpp", 
        # "unetaxial", 
        "deeplabv3", 
        "pspnet", 
        "segformer",
        # "mask2former",
        # "segformer_improved",
        # "setr",
        # "setr_pup",
        # "convnext",
        # "efficientnetv2",
        # "fast_scnn",
        # "fast_scnn_plus",
        "bisenet",
        # "bisenet_v2"
        ], 
                   choices=["unet", "unetpp", "unetaxial", "deeplabv3", "pspnet", "segformer", "mask2former",
                           "segformer_improved", "setr", "setr_pup", "convnext", "efficientnetv2",
                           "fast_scnn", "fast_scnn_plus", "bisenet", "bisenet_v2", "ccnet", "danet",
                           "fdsnet", "a3net", "moesteelunet_pdf", "moesteelunet_pdf_figure5",
                           "moesteelunet_last", "moesteelunet_mamba1", "moesteelunet_mamba11",
                           "moemambacnn",
                           *FRAMEWORK_ABLATION_MODELS,
                           *MOE_ABLATION_CONFIGS.keys(),
                           *LAST_MOE_ABLATION_CONFIGS.keys()],
                   help="Models to train: unet, unetpp, unetaxial, deeplabv3, pspnet, segformer, mask2former, "
                        "segformer_improved, setr, setr_pup, convnext, efficientnetv2, fast_scnn, fast_scnn_plus, "
                        "bisenet, bisenet_v2, ccnet, danet, fdsnet, a3net, moesteelunet_pdf, "
                        "moesteelunet_pdf_figure5, moesteelunet_last, moesteelunet_mamba1, "
                        "moesteelunet_mamba11, moemambacnn, "
                        "MorphoMoE framework M1-M8, and legacy/final "
                        "MoESteelUNet ablation variants")
    return p.parse_args()


def count_parameters(model):
    """计算模型参数量"""
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def parse_pdf_class_to_expert(spec: str, num_classes: int) -> Dict[int, int]:
    """Parse an explicit ``class_id:expert_name`` mapping for paper loss (31)."""
    if not spec or not spec.strip():
        raise ValueError("--pdf_class_to_expert is required when PDF specialization loss is enabled")
    expert_indices = {name: index for index, name in enumerate(PDF_EXPERT_ORDER)}
    mapping: Dict[int, int] = {}
    for item in spec.split(","):
        parts = item.strip().split(":", 1)
        if len(parts) != 2:
            raise ValueError(
                "Invalid --pdf_class_to_expert item. Expected class_id:expert_name"
            )
        try:
            class_id = int(parts[0])
        except ValueError as exc:
            raise ValueError(f"Invalid semantic class id: {parts[0]!r}") from exc
        expert_name = parts[1].strip().lower()
        if class_id <= 0 or class_id >= num_classes:
            raise ValueError(
                f"Semantic class id {class_id} must be between 1 and {num_classes - 1}"
            )
        if expert_name not in expert_indices:
            raise ValueError(
                f"Unknown PDF expert {expert_name!r}; expected one of {PDF_EXPERT_ORDER}"
            )
        if class_id in mapping:
            raise ValueError(f"Semantic class id {class_id} is mapped more than once")
        mapping[class_id] = expert_indices[expert_name]
    return mapping


def pdf_expert_targets_from_masks(
    masks: torch.Tensor, class_to_expert: Dict[int, int], ignore_index: int = -1
) -> torch.Tensor:
    """Build one sample-level expert target from mapped foreground pixel area.

    Background-only images and foreground classes absent from the explicit map
    are ignored.  If an image contains classes assigned to different experts,
    their foreground pixels are accumulated per expert and the expert with the
    largest mapped area becomes the target.  Exact ties remain ignored instead
    of being resolved by an arbitrary expert-order preference.
    """
    if masks.ndim != 3:
        raise ValueError("masks must have shape [batch, height, width]")
    targets = torch.full(
        (masks.shape[0],), ignore_index, dtype=torch.long, device=masks.device
    )
    for sample_index, mask in enumerate(masks):
        pixels_per_expert: Dict[int, int] = {}
        for class_id, expert_index in class_to_expert.items():
            pixel_count = int((mask == class_id).sum().item())
            if pixel_count > 0:
                pixels_per_expert[expert_index] = (
                    pixels_per_expert.get(expert_index, 0) + pixel_count
                )
        if not pixels_per_expert:
            continue
        largest_area = max(pixels_per_expert.values())
        dominant_experts = [
            expert_index
            for expert_index, pixel_count in pixels_per_expert.items()
            if pixel_count == largest_area
        ]
        if len(dominant_experts) == 1:
            targets[sample_index] = dominant_experts[0]
    return targets


def get_class_reporting_spec(dataset: str, num_classes: int):
    """Return ``(display_name, label_id)`` pairs in the paper-table order."""
    if dataset == "magnetic":
        spec = [("Free", 0), ("Blowhole", 1), ("Break", 2), ("Crack", 3),
                ("Fray", 4), ("Uneven", 5)]
    elif dataset == "neu":
        # NEU internal labels are 0=Background, 1=Inclusion, 2=Patch, 3=Scratch.
        # The paper table presents them as Background, Scratch, Patch, Inclusion.
        spec = [("Background", 0), ("Scratch", 3), ("Patch", 2), ("Inclusion", 1)]
    elif dataset == "bsdata":
        spec = [("Background", 0), ("Defect", 1)]
    elif dataset == "severstal":
        spec = [("Background", 0), ("Defect_1", 1), ("Defect_2", 2), ("Defect_3", 3)]
    else:
        spec = [(f"Class_{index}", index) for index in range(num_classes)]
    if len(spec) != num_classes:
        return [(f"Class_{index}", index) for index in range(num_classes)]
    return spec


def get_class_names(dataset: str, num_classes: int):
    """Return class names in the paper-table reporting order."""
    return [name for name, _ in get_class_reporting_spec(dataset, num_classes)]


def ordered_per_class_metric(metrics: Dict[str, Any], key: str, dataset: str, num_classes: int):
    """Reorder a label-indexed metric into the paper-table reporting order."""
    raw_values = metric_values(metrics, key)
    return [raw_values[label_id] for _, label_id in get_class_reporting_spec(dataset, num_classes)]


def metric_values(metrics: Dict[str, Any], key: str):
    """Serialize a tensor/list metric as ordinary floats for checkpoints and reports."""
    values = metrics[key]
    if isinstance(values, torch.Tensor):
        values = values.detach().cpu().tolist()
    return [float(value) for value in values]


def get_dataset_save_dir(save_dir: str, args) -> str:
    """Return the run-isolated output directory for one dataset."""
    dataset_save_dir = os.path.join(save_dir, args.dataset)
    return os.path.join(dataset_save_dir, args.run_name) if args.run_name else dataset_save_dir


def get_model(model_name: str, num_classes: int, device: torch.device,
              a3net_pretrained_backbone: bool = False) -> nn.Module:
    """根据模型名称创建对应的模型"""
    # ``moesteelunet`` is the paper's complete SDE+RDE+CSE model.  Keep this
    # direct construction separate from ``moesteelunet_all``, which is the
    # identically configured row used by the expert-combination ablation.
    if model_name == "moesteelunet_pdf":
        model = MoESteelUNetPDF(
            in_channels=3,
            num_classes=num_classes,
            bilinear=True,
        )
    elif model_name == "moesteelunet_pdf_figure5":
        model = MoESteelUNetPDFFigure5(
            in_channels=3,
            num_classes=num_classes,
            bilinear=True,
        )
    elif model_name == "moesteelunet_last":
        model = MoESteelUNetLast(
            in_channels=3,
            num_classes=num_classes,
            bilinear=True,
        )
    elif model_name == "moesteelunet_mamba1":
        model = MoESteelUNetMamba1(
            in_channels=3,
            num_classes=num_classes,
            bilinear=True,
        )
    elif model_name == "moesteelunet_mamba11":
        model = MoESteelUNetMamba11(
            in_channels=3,
            num_classes=num_classes,
            bilinear=True,
        )
    elif model_name == "moemambacnn":
        model = MoESteelUNetMambaCNN(
            in_channels=3,
            num_classes=num_classes,
            bilinear=True,
        )
    elif model_name in FRAMEWORK_ABLATION_CONFIGS:
        model = build_framework_ablation_model(
            model_name=model_name,
            in_channels=3,
            num_classes=num_classes,
            bilinear=True,
        )
    elif model_name in LAST_MOE_ABLATION_CONFIGS:
        model = MoESteelUNetLast(
            in_channels=3,
            num_classes=num_classes,
            bilinear=True,
            active_experts=LAST_MOE_ABLATION_CONFIGS[model_name],
        )
    elif model_name == "moesteelunet":
        model = MoESteelUnet(
            in_channels=3,
            num_classes=num_classes,
            bilinear=True,
        )
    elif model_name in MOE_ABLATION_CONFIGS:
        model = MoESteelUnet(
            in_channels=3,
            num_classes=num_classes,
            bilinear=True,
            active_experts=MOE_ABLATION_CONFIGS[model_name],
        )
    elif model_name == "unet":
        model = UNet(in_channels=3, num_classes=num_classes, bilinear=True)
    elif model_name == "unetpp":
        model = NestedUNet(in_channels=3, num_classes=num_classes, deep_supervision=False)
    elif model_name == "unetaxial":
        model = UNetAxial(in_channels=3, num_classes=num_classes, base_channels=16)
    elif model_name == "deeplabv3":
        model = DeepLabV3Plus(in_channels=3, num_classes=num_classes, backbone='resnet50', pretrained=False)
    elif model_name == "pspnet":
        model = PSPNet(in_channels=3, num_classes=num_classes, backbone='resnet50', pretrained=False)
    elif model_name == "segformer":
        model = SegFormer(in_channels=3, num_classes=num_classes)
    elif model_name == "mask2former":
        model = Mask2Former(in_channels=3, num_classes=num_classes, num_queries=50)
    # Transformer模型
    elif model_name == "segformer_improved":
        model = SegFormerImproved(in_channels=3, num_classes=num_classes, backbone_name='mit_b0', pretrained=False)
    elif model_name == "setr":
        model = SETR(in_channels=3, num_classes=num_classes, backbone_name='vit_base_patch16_224', pretrained=False)
    elif model_name == "setr_pup":
        model = SETR_PUP(in_channels=3, num_classes=num_classes, backbone_name='vit_base_patch16_224', pretrained=False)
    # 现代CNN模型
    elif model_name == "convnext":
        model = ConvNeXtSegmentation(in_channels=3, num_classes=num_classes, backbone_name='convnext_tiny', pretrained=False)
    elif model_name == "efficientnetv2":
        model = EfficientNetV2Segmentation(in_channels=3, num_classes=num_classes, backbone_name='efficientnetv2_s', pretrained=False)
    # 轻量级实时分割模型
    elif model_name == "fast_scnn":
        model = FastSCNN(in_channels=3, num_classes=num_classes)
    elif model_name == "fast_scnn_plus":
        model = FastSCNNPlus(in_channels=3, num_classes=num_classes)
    elif model_name == "bisenet":
        model = BiSeNet(in_channels=3, num_classes=num_classes, backbone_name='resnet18', pretrained=False)
    elif model_name == "bisenet_v2":
        model = BiSeNetV2(in_channels=3, num_classes=num_classes, backbone_name='resnet18', pretrained=False)
    elif model_name == "ccnet":
        model = CCNet(in_channels=3, num_classes=num_classes, backbone_name='resnet101', pretrained=False)
    elif model_name == "danet":
        model = DANet(in_channels=3, num_classes=num_classes, backbone_name='resnet18', pretrained=False, aux=False)
    elif model_name == "fdsnet":
        # Keep the source model's boundary and semantic-presence auxiliary
        # branches. Their targets are derived from the semantic mask below.
        model = FDSNet(num_classes=num_classes, aux=True)
    elif model_name == "a3net":
        # The standalone A3Net keeps the source Res2Net-50 backbone and five
        # deeply-supervised decoder predictions.  Match the other baselines by
        # training the backbone from scratch in this shared pipeline.
        model = A3Net(
            num_classes=num_classes,
            pretrained_backbone=a3net_pretrained_backbone,
        )
    # 消融实验
    elif model_name == "UNetDepthwise":
        model = UNetDepthwise(in_channels=3, num_classes=num_classes, base_channels=16)
    elif model_name == "MultiUNet":
        model = MultiUNet(in_channels=3, num_classes=num_classes, base_channels=16)
    else:   
        raise ValueError(f"Unknown model: {model_name}")
    
    return model.to(device)


def segmentation_outputs(output):
    """Normalize a model result to a non-empty tuple of BCHW logits.

    Most baselines return one tensor, FDSNet returns a one-element tuple, and
    A3Net returns five full-resolution tensors for deep supervision.
    """
    if torch.is_tensor(output):
        outputs = (output,)
    elif isinstance(output, (tuple, list)):
        outputs = tuple(output)
    else:
        raise TypeError(f"Expected segmentation tensor(s), got {type(output).__name__}")
    if not outputs or any(not torch.is_tensor(item) or item.ndim != 4 for item in outputs):
        raise TypeError("Segmentation outputs must be a non-empty collection of BCHW tensors")
    return outputs


def resize_segmentation_outputs(outputs, spatial_size):
    """Resize every deep-supervision prediction to the target-mask size."""
    return tuple(
        output if output.shape[-2:] == spatial_size else torch.nn.functional.interpolate(
            output, size=spatial_size, mode="bilinear", align_corners=False
        )
        for output in outputs
    )


def fdsnet_auxiliary_targets(masks, num_classes):
    """Derive FDSNet boundary and foreground-class presence targets."""
    edges = torch.zeros_like(masks, dtype=torch.bool)
    vertical = masks[:, 1:, :] != masks[:, :-1, :]
    horizontal = masks[:, :, 1:] != masks[:, :, :-1]
    edges[:, 1:, :] |= vertical
    edges[:, :-1, :] |= vertical
    edges[:, :, 1:] |= horizontal
    edges[:, :, :-1] |= horizontal
    edge_target = edges.unsqueeze(1).float()
    semantic_target = torch.stack(
        [(masks == class_id).flatten(1).any(dim=1) for class_id in range(1, num_classes)],
        dim=1,
    ).float()
    return edge_target, semantic_target


def seed_dataloader_worker(worker_id: int):
    """Seed Python/NumPy augmentation RNGs from the loader's torch generator."""
    worker_seed = torch.initial_seed() % (2 ** 32)
    random.seed(worker_seed)
    np.random.seed(worker_seed)


def make_dataloaders_train_test(dataset: str, data_root: str, train_split: str, test_split: str, batch_size: int, num_workers: int,
                                apply_clahe: bool, sp_threshold: float, augment: bool, num_classes: int, random_seed: int) -> Tuple[DataLoader, DataLoader]:
    """根据数据集类型创建数据加载器"""
    
    if dataset == "neu":
        # NEU_Seg数据集
        neu_root = os.path.join(data_root, "NEU_Seg-main")
        train_images = os.path.join(neu_root, "images", train_split)
        train_masks = os.path.join(neu_root, "masks", train_split)
        test_images = os.path.join(neu_root, "images", test_split)
        test_masks = os.path.join(neu_root, "masks", test_split)

        train_set = DefectDataset(images_dir=train_images, masks_dir=train_masks, apply_clahe=apply_clahe, sp_threshold=sp_threshold, augment=augment, num_classes=num_classes)
        test_set = DefectDataset(images_dir=test_images, masks_dir=test_masks, apply_clahe=apply_clahe, sp_threshold=sp_threshold, augment=False, num_classes=num_classes)
        
    elif dataset == "magnetic":
        # Magnetic-tile数据集
        magnetic_root = os.path.join(data_root, "Magnetic-tile")
        train_set = MagneticTileDataset(data_root=magnetic_root, split="train", augment=augment, apply_clahe=apply_clahe, sp_threshold=sp_threshold, num_classes=6, random_seed=random_seed)
        test_set = MagneticTileDataset(data_root=magnetic_root, split="test", augment=False, apply_clahe=apply_clahe, sp_threshold=sp_threshold, num_classes=6, random_seed=random_seed)
        
    elif dataset == "severstal":
        # Severstal Steel数据集
        severstal_root = os.path.join(data_root, "Severstal Steel Dataset")
        train_set = SeverstalDataset(data_root=severstal_root, split="train", augment=augment, apply_clahe=apply_clahe, sp_threshold=sp_threshold, num_classes=4, random_seed=random_seed)
        test_set = SeverstalDataset(data_root=severstal_root, split="valid", augment=False, apply_clahe=apply_clahe, sp_threshold=sp_threshold, num_classes=4, random_seed=random_seed)

    elif dataset == "bsdata":
        # BSData: train/test 均为 images/ 与 mask/，掩膜使用 0=背景、255=缺陷。
        bsdata_root = os.path.join(data_root, "BSData")
        train_set = DefectDataset(
            images_dir=os.path.join(bsdata_root, train_split, "images"),
            masks_dir=os.path.join(bsdata_root, train_split, "mask"),
            apply_clahe=apply_clahe,
            sp_threshold=sp_threshold,
            augment=augment,
            num_classes=2,
            binary_mask=True,
        )
        test_set = DefectDataset(
            images_dir=os.path.join(bsdata_root, test_split, "images"),
            masks_dir=os.path.join(bsdata_root, test_split, "mask"),
            apply_clahe=apply_clahe,
            sp_threshold=sp_threshold,
            augment=False,
            num_classes=2,
            binary_mask=True,
        )
        
    else:
        raise ValueError(f"Unknown dataset: {dataset}")

    # Each model receives a fresh loader with the same sampling and augmentation
    # sequence. This prevents an earlier model from advancing shared RNG state.
    train_generator = torch.Generator()
    train_generator.manual_seed(random_seed)
    test_generator = torch.Generator()
    test_generator.manual_seed(random_seed + 1)
    train_loader = DataLoader(
        train_set, batch_size=batch_size, shuffle=True, num_workers=num_workers,
        pin_memory=True, generator=train_generator, worker_init_fn=seed_dataloader_worker,
    )
    test_loader = DataLoader(
        test_set, batch_size=batch_size, shuffle=False, num_workers=num_workers,
        pin_memory=True, generator=test_generator, worker_init_fn=seed_dataloader_worker,
    )
    return train_loader, test_loader


def train_one_epoch(
    model, loader, optimizer, ce_loss, dice_loss, device, num_classes,
    pdf_spec_loss_weight=0.0, pdf_class_to_expert=None,
):
    if (
        isinstance(model, MorphoMoEFrameworkAblation)
        and pdf_spec_loss_weight != 0
    ):
        raise ValueError(
            "M1-M8 framework ablations freeze the objective to CE + Dice; "
            "pdf_spec_loss_weight must be 0"
        )
    model.train()
    running_loss = 0.0
    for batch in loader:
        images = batch["image"].to(device)
        masks = batch["mask"].to(device)

        if isinstance(model, (MoESteelUNetPDF, MoESteelUNetLast)):
            logits, pdf_aux = model(images, return_aux=True)
            logits = resize_segmentation_outputs((logits,), masks.shape[-2:])[0]
            loss = ce_loss(logits, masks) + dice_loss(
                logits, masks, num_classes=num_classes
            )
            if pdf_spec_loss_weight > 0:
                target_experts = pdf_expert_targets_from_masks(
                    masks, pdf_class_to_expert or {}
                )
                loss = loss + pdf_spec_loss_weight * expert_specialization_loss(
                    pdf_aux["gate_weights"], target_experts
                )
        elif isinstance(model, FDSNet) and model.aux:
            raw_outputs = model(images)
            logits, edge_prediction, semantic_prediction = raw_outputs
            logits = resize_segmentation_outputs((logits,), masks.shape[-2:])[0]
            edge_target, semantic_target = fdsnet_auxiliary_targets(masks, num_classes)
            if edge_prediction.shape[-2:] != masks.shape[-2:]:
                edge_prediction = torch.nn.functional.interpolate(
                    edge_prediction, size=masks.shape[-2:], mode="bilinear", align_corners=False
                )
            main_loss = ce_loss(logits, masks) + dice_loss(
                logits, masks, num_classes=num_classes
            )
            loss = (
                main_loss
                + 0.5 * torch.nn.functional.binary_cross_entropy(edge_prediction, edge_target)
                + 0.5 * torch.nn.functional.binary_cross_entropy(
                    semantic_prediction, semantic_target
                )
            )
        else:
            raw_outputs = model(images)
            outputs = resize_segmentation_outputs(
                segmentation_outputs(raw_outputs), masks.shape[-2:]
            )
            # A3Net's source trainer supervises all five decoder predictions.
            # Apply this pipeline's CE+Dice objective to every prediction.
            loss = sum(
                ce_loss(logits, masks) + dice_loss(logits, masks, num_classes=num_classes)
                for logits in outputs
            )

        optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
        optimizer.step()

        running_loss += loss.item() * images.size(0)

    return running_loss / len(loader.dataset)


@torch.no_grad()
def evaluate(model, loader, ce_loss, dice_loss, device, num_classes):
    model.eval()
    total_loss = 0.0
    cm_total = torch.zeros((num_classes, num_classes), dtype=torch.long, device=device)
    gate_sum = None
    route_counts = None
    gate_entropy_sum = 0.0
    gate_samples = 0
    for batch in loader:
        images = batch["image"].to(device)
        masks = batch["mask"].to(device)
        if isinstance(model, (MoESteelUnet, MoESteelUNetPDF, MoESteelUNetLast)):
            logits, aux = model(images, return_aux=True)
            # Existing MoE models omit this flag and retain their historical
            # adaptive-gate statistics. Framework average rows explicitly set
            # it false so fixed 1/3 weights are never labelled as learned gates.
            if bool(aux.get("is_adaptive_gating", True)):
                gate_weights = aux["gate_weights"]
                if gate_sum is None:
                    gate_sum = torch.zeros(gate_weights.shape[1], dtype=torch.float64, device=device)
                    route_counts = torch.zeros(gate_weights.shape[1], dtype=torch.float64, device=device)
                gate_sum += gate_weights.sum(dim=0).to(torch.float64)
                route_counts += torch.bincount(
                    gate_weights.argmax(dim=1), minlength=gate_weights.shape[1]
                ).to(torch.float64)
                gate_entropy_sum += float(
                    -(gate_weights * torch.log(gate_weights.clamp_min(1e-12))).sum(dim=1).sum().item()
                )
                gate_samples += gate_weights.shape[0]
        elif isinstance(model, FDSNet):
            logits = model(images)[0]
        else:
            logits = segmentation_outputs(model(images))[0]
        # 保证 logits 与 masks 的空间尺寸一致
        if logits.shape[-2:] != masks.shape[-2:]:
            logits = torch.nn.functional.interpolate(logits, size=masks.shape[-2:], mode="bilinear", align_corners=False)
        loss_ce = ce_loss(logits, masks)
        loss_dice = dice_loss(logits, masks, num_classes=num_classes)
        loss = loss_ce + loss_dice
        total_loss += loss.item() * images.size(0)

        preds = torch.argmax(logits, dim=1)
        cm = compute_confusion_matrix(preds, masks, num_classes=num_classes)
        cm_total += cm.to(device)

    metrics = metrics_from_confmat(cm_total.cpu())
    gate_stats = None
    if gate_sum is not None:
        mean_weights = (gate_sum / gate_samples).cpu().tolist()
        usage = (route_counts / gate_samples).cpu().tolist()
        entropy = gate_entropy_sum / gate_samples
        normalized_entropy = entropy / np.log(len(mean_weights)) if len(mean_weights) > 1 else 0.0
        gate_stats = {
            "active_experts": list(model.active_experts),
            "mean_gate_weight": dict(zip(model.active_experts, mean_weights)),
            "argmax_usage": dict(zip(model.active_experts, usage)),
            "entropy": entropy,
            "normalized_entropy": normalized_entropy,
        }
    return total_loss / len(loader.dataset), metrics, gate_stats


def build_checkpoint(model, model_name, epoch, metrics, num_params, args, gate_stats=None):
    """Build a self-describing checkpoint without changing non-MoE checkpoint semantics."""
    checkpoint = {
        "model_state": model.state_dict(),
        "model_name": model_name,
        "epoch": epoch,
        "mIoU": float(metrics["mIoU"]),
        "mDice": float(metrics["mDice"]),
        "Acc": float(metrics["Acc"]),
        "IoU_per_class": metric_values(metrics, "IoU_per_class"),
        "Dice_per_class": metric_values(metrics, "Dice_per_class"),
        "Acc_per_class": metric_values(metrics, "Acc_per_class"),
        "num_classes": args.num_classes,
        "num_params": num_params,
        "args": vars(args),
    }
    if isinstance(model, (MoESteelUnet, MoESteelUNetPDF, MoESteelUNetLast)):
        if (
            isinstance(model, MorphoMoEFrameworkAblation)
            and not model.is_adaptive_gating
        ):
            gate_stats = None
        checkpoint.update({
            "model_class": type(model).__name__,
            "model_config": model.get_model_config(),
            "active_experts": list(model.active_experts),
            "gate_stats": gate_stats,
        })
    return checkpoint


def update_moe_ablation_reports(dataset_save_dir: str, results):
    """Upsert formal MoE ablation results so later batches do not erase prior rows."""
    ablation_results = [
        r for r in results
        if r["model_name"] in ALL_FORMAL_MOE_ABLATION_MODELS
    ]
    if not ablation_results:
        return

    csv_path = os.path.join(dataset_save_dir, "moe_ablation_results.csv")
    fieldnames = ["model_name", "active_experts", "num_params", "best_epoch", "mIoU", "mDice", "Acc", "training_time"]
    existing = {}
    if os.path.exists(csv_path):
        with open(csv_path, newline="", encoding="utf-8") as f:
            existing = {row["model_name"]: row for row in csv.DictReader(f)}
    for result in ablation_results:
        metrics = result["best_metrics"]
        existing[result["model_name"]] = {
            "model_name": result["model_name"],
            "active_experts": "+".join(result["active_experts"]),
            "num_params": str(result["num_params"]),
            "best_epoch": str(metrics["epoch"]),
            "mIoU": f"{metrics['mIoU']:.6f}",
            "mDice": f"{metrics['mDice']:.6f}",
            "Acc": f"{metrics['Acc']:.6f}",
            "training_time": f"{result['training_time']:.2f}",
        }
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing[name] for name in sorted(existing))

    gate_path = os.path.join(dataset_save_dir, "moe_ablation_gate_stats.json")
    gate_records = {}
    if os.path.exists(gate_path):
        with open(gate_path, encoding="utf-8") as f:
            gate_records = json.load(f)
    for result in ablation_results:
        gate_records[result["model_name"]] = result.get("best_gate_stats")
    with open(gate_path, "w", encoding="utf-8") as f:
        json.dump(gate_records, f, ensure_ascii=False, indent=2)

    text_path = os.path.join(dataset_save_dir, "moe_ablation_results.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write("MoESteelUNet expert-combination ablation results\n")
        f.write("model_name,active_experts,num_params,best_epoch,mIoU,mDice,Acc,training_time\n")
        for name in sorted(existing):
            row = existing[name]
            f.write(",".join(row[field] for field in fieldnames) + "\n")


def update_framework_ablation_reports(dataset_save_dir: str, results):
    """Incrementally upsert the independent M1-M8 framework reports.

    The canonical model tuple, rather than lexical sorting, fixes every output
    in M1-to-M8 order.  Average rows record fixed weights separately and keep
    ``gate_stats`` null.
    """

    framework_results = [
        result
        for result in results
        if result["model_name"] in FRAMEWORK_ABLATION_CONFIGS
    ]
    if not framework_results:
        return None

    os.makedirs(dataset_save_dir, exist_ok=True)
    csv_path = os.path.join(
        dataset_save_dir, "framework_ablation_results.csv"
    )
    fieldnames = [
        "ablation_id",
        "model_name",
        "encoder_type",
        "expert_type",
        "fusion_type",
        "num_params",
        "best_epoch",
        "mIoU",
        "mDice",
        "Acc",
        "training_time",
        "checkpoint_path",
    ]
    existing_rows = {}
    if os.path.exists(csv_path):
        with open(csv_path, newline="", encoding="utf-8") as handle:
            existing_rows = {
                row["model_name"]: row for row in csv.DictReader(handle)
            }

    for result in framework_results:
        model_name = result["model_name"]
        factors = FRAMEWORK_ABLATION_CONFIGS[model_name]
        metrics = result["best_metrics"]
        existing_rows[model_name] = {
            "ablation_id": factors["ablation_id"],
            "model_name": model_name,
            "encoder_type": factors["encoder_type"],
            "expert_type": factors["expert_type"],
            "fusion_type": factors["fusion_type"],
            "num_params": str(result["num_params"]),
            "best_epoch": str(metrics["epoch"]),
            "mIoU": "{:.6f}".format(metrics["mIoU"]),
            "mDice": "{:.6f}".format(metrics["mDice"]),
            "Acc": "{:.6f}".format(metrics["Acc"]),
            "training_time": "{:.2f}".format(result["training_time"]),
            "checkpoint_path": result["save_path"],
        }

    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for model_name in FRAMEWORK_ABLATION_MODELS:
            if model_name in existing_rows:
                writer.writerow(
                    {
                        field: existing_rows[model_name].get(field, "")
                        for field in fieldnames
                    }
                )

    config_path = os.path.join(
        dataset_save_dir, "framework_ablation_config.json"
    )
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as handle:
            config_payload = json.load(handle)
    else:
        config_payload = {
            "schema_version": 1,
            "design": "2x2x2",
            "model_order": list(FRAMEWORK_ABLATION_MODELS),
            "canonical_configs": {
                name: {
                    "model_name": name,
                    **FRAMEWORK_ABLATION_CONFIGS[name],
                }
                for name in FRAMEWORK_ABLATION_MODELS
            },
            "homogeneous_expert_hidden_channels": (
                HOMOGENEOUS_EXPERT_HIDDEN_CHANNELS
            ),
            "frozen_lpdm_config": get_frozen_lpdm_config(),
            "completed_models": {},
            "training_protocol": None,
        }

    for result in framework_results:
        protocol = result.get("training_protocol")
        recorded_protocol = config_payload.get("training_protocol")
        if protocol is not None:
            if recorded_protocol is not None and recorded_protocol != protocol:
                raise ValueError(
                    "Refusing to merge framework rows trained with different "
                    "formal settings: existing={} new={}".format(
                        recorded_protocol, protocol
                    )
                )
            config_payload["training_protocol"] = protocol
        model_name = result["model_name"]
        fusion_type = FRAMEWORK_ABLATION_CONFIGS[model_name]["fusion_type"]
        config_payload.setdefault("completed_models", {})[model_name] = {
            "model_config": result.get("model_config"),
            "gate_stats": (
                result.get("best_gate_stats")
                if fusion_type == "adaptive"
                else None
            ),
            "fixed_fusion_weights": (
                [1.0 / 3.0] * 3 if fusion_type == "average" else None
            ),
            "checkpoint_path": result["save_path"],
        }
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(config_payload, handle, ensure_ascii=False, indent=2)

    text_path = os.path.join(
        dataset_save_dir, "framework_ablation_results.txt"
    )
    with open(text_path, "w", encoding="utf-8") as handle:
        handle.write(
            "MorphoMoE whole-framework ablation (formal metrics only)\n"
        )
        handle.write(
            "Model | LPDM | Heterogeneous Experts | Adaptive Gating | "
            "mIoU | mDice | Acc\n"
        )
        handle.write("-" * 92 + "\n")
        for model_name in FRAMEWORK_ABLATION_MODELS:
            factors = FRAMEWORK_ABLATION_CONFIGS[model_name]
            row = existing_rows.get(model_name)
            handle.write(
                "{} | {} | {} | {} | {} | {} | {}\n".format(
                    factors["ablation_id"],
                    "yes" if factors["encoder_type"] == "lpdm" else "",
                    "yes"
                    if factors["expert_type"] == "heterogeneous"
                    else "",
                    "yes" if factors["fusion_type"] == "adaptive" else "",
                    row["mIoU"] if row else "",
                    row["mDice"] if row else "",
                    row["Acc"] if row else "",
                )
            )

    parameter_path = os.path.join(
        dataset_save_dir, "framework_ablation_parameter_report.txt"
    )
    if not os.path.exists(parameter_path):
        completed_config = framework_results[0].get("model_config") or {}
        write_framework_parameter_report(
            dataset_save_dir,
            num_classes=int(completed_config.get("num_classes", 4)),
        )
    return {
        "csv": csv_path,
        "text": text_path,
        "config": config_path,
        "parameters": parameter_path,
    }


def get_scheduler(optimizer, scheduler_type: str, args):
    """根据类型创建学习率调度器"""
    if scheduler_type == "plateau":
        return torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='max', factor=args.lr_factor, patience=args.lr_patience, 
            verbose=True, min_lr=args.min_lr
        )
    elif scheduler_type == "cosine":
        return torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, T_max=args.epochs, eta_min=args.min_lr
        )
    elif scheduler_type == "step":
        return torch.optim.lr_scheduler.StepLR(
            optimizer, step_size=args.epochs//3, gamma=args.lr_factor
        )
    elif scheduler_type == "exponential":
        return torch.optim.lr_scheduler.ExponentialLR(
            optimizer, gamma=0.98  # 更温和的衰减
        )
    else:
        raise ValueError(f"Unknown scheduler type: {scheduler_type}")


def create_optimizer(model: nn.Module, args):
    """Create the requested optimizer without silently changing old defaults."""
    if args.weight_decay < 0:
        raise ValueError("--weight_decay must be non-negative")
    if args.optimizer == "adam":
        return torch.optim.Adam(
            model.parameters(), lr=args.lr, weight_decay=args.weight_decay
        )
    if args.optimizer == "adamw":
        return torch.optim.AdamW(
            model.parameters(), lr=args.lr, weight_decay=args.weight_decay
        )
    raise ValueError(f"Unknown optimizer: {args.optimizer}")


def train_model(model_name: str, train_loader: DataLoader, val_loader: DataLoader, 
                args, device: torch.device, save_dir: str) -> Dict[str, Any]:
    """训练单个模型"""
    print(f"\n{'='*60}")
    print(f"开始训练模型: {model_name.upper()}")
    print(f"{'='*60}")
    
    # 创建模型
    model = get_model(
        model_name,
        args.num_classes,
        device,
        a3net_pretrained_backbone=args.a3net_pretrained_backbone,
    )

    pdf_class_to_expert = None
    if isinstance(model, MorphoMoEFrameworkAblation):
        if args.pdf_spec_loss_weight != 0:
            raise ValueError(
                "M1-M8 framework ablations freeze the objective to CE + Dice; "
                "--pdf_spec_loss_weight must be 0"
            )
        print(
            "整体框架消融 {}: encoder={}, expert={}, fusion={}; "
            "仅使用 CE + Dice。".format(
                model.ablation_id,
                model.encoder_type,
                model.expert_type,
                model.fusion_type,
            )
        )
    elif isinstance(model, (MoESteelUNetPDF, MoESteelUNetLast)):
        if args.pdf_spec_loss_weight < 0:
            raise ValueError("--pdf_spec_loss_weight must be non-negative")
        if args.pdf_spec_loss_weight > 0:
            if tuple(model.active_experts) != tuple(PDF_EXPERT_ORDER):
                raise ValueError(
                    "--pdf_spec_loss_weight is only defined for the complete "
                    "SDE+RDE+CSE model; use 0 for expert-subset ablations"
                )
            pdf_class_to_expert = parse_pdf_class_to_expert(
                args.pdf_class_to_expert, args.num_classes
            )
            readable_mapping = {
                class_id: PDF_EXPERT_ORDER[expert_index]
                for class_id, expert_index in pdf_class_to_expert.items()
            }
            print(
                f"启用 PDF 专家专门化损失: lambda={args.pdf_spec_loss_weight}, "
                f"class_to_expert={readable_mapping}"
            )
        else:
            print("PDF 专家专门化损失未启用（lambda=0，仅使用 CE + Dice）。")
    
    # 计算并输出模型参数量
    num_params = count_parameters(model)
    print(f"模型参数量: {num_params/1e6:.2f}M ({num_params:,})")
    
    # 优化器和损失函数
    optimizer = create_optimizer(model, args)
    scheduler = get_scheduler(optimizer, args.scheduler, args)
    ce_loss = nn.CrossEntropyLoss()
    dice_loss = DiceLoss()
    
    print(f"优化器: {args.optimizer} (weight_decay={args.weight_decay})")
    print(f"使用学习率调度器: {args.scheduler}")
    print(f"初始学习率: {args.lr}")
    
    # 保存路径 - 根据数据集名称创建子文件夹
    dataset_save_dir = get_dataset_save_dir(save_dir, args)
    model_save_path = os.path.join(dataset_save_dir, f"best_{model_name}.pth")
    last_model_save_path = os.path.join(dataset_save_dir, f"last_{model_name}.pth")
    os.makedirs(dataset_save_dir, exist_ok=True)
    
    best_miou = -1.0
    best_metrics = {}
    best_gate_stats = None
    last_metrics = None
    last_gate_stats = None
    last_epoch = 0
    epochs_without_improvement = 0
    start_time = time.time()
    
    for epoch in range(1, args.epochs + 1):
        last_epoch = epoch
        train_loss = train_one_epoch(
            model, train_loader, optimizer, ce_loss, dice_loss, device, args.num_classes,
            pdf_spec_loss_weight=args.pdf_spec_loss_weight,
            pdf_class_to_expert=pdf_class_to_expert,
        )
        val_loss, val_metrics, val_gate_stats = evaluate(
            model, val_loader, ce_loss, dice_loss, device, args.num_classes
        )
        last_metrics = val_metrics
        last_gate_stats = val_gate_stats
        
        miou = float(val_metrics["mIoU"])
        mdice = float(val_metrics["mDice"])
        acc = float(val_metrics["Acc"])
        
        print(f"Epoch {epoch:03d}: train_loss={train_loss:.4f} val_loss={val_loss:.4f} mIoU={miou:.4f} mDice={mdice:.4f} Acc={acc:.4f}")
        
        # 更新学习率调度器
        if args.scheduler == "plateau":
            scheduler.step(miou)  # ReduceLROnPlateau需要传入指标
        else:
            scheduler.step()  # 其他调度器不需要参数
        
        # 打印当前学习率
        current_lr = optimizer.param_groups[0]['lr']
        print(f"当前学习率: {current_lr:.2e}")
        
        if miou > best_miou:
            best_miou = miou
            best_metrics = {
                "mIoU": miou,
                "mDice": mdice,
                "Acc": acc,
                "epoch": epoch,
                "IoU_per_class": metric_values(val_metrics, "IoU_per_class"),
                "Dice_per_class": metric_values(val_metrics, "Dice_per_class"),
                "Acc_per_class": metric_values(val_metrics, "Acc_per_class"),
            }
            best_gate_stats = val_gate_stats
            torch.save(
                build_checkpoint(model, model_name, epoch, val_metrics, num_params, args, val_gate_stats),
                model_save_path,
            )
            print(f"Saved best {model_name} model to {model_save_path} (mIoU={best_miou:.4f})")
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1

        if (
            args.early_stopping_patience > 0
            and epochs_without_improvement >= args.early_stopping_patience
        ):
            print(
                f"Early stopping at epoch {epoch}: validation mIoU did not improve "
                f"for {args.early_stopping_patience} consecutive epochs."
            )
            break

    torch.save(
        build_checkpoint(model, model_name, last_epoch, last_metrics, num_params, args, last_gate_stats),
        last_model_save_path,
    )
    
    training_time = time.time() - start_time
    print(f"\n{model_name.upper()} 训练完成!")
    print(f"最佳 mIoU: {best_miou:.4f}")
    class_names = get_class_names(args.dataset, args.num_classes)
    per_class_iou = ordered_per_class_metric(
        best_metrics, "IoU_per_class", args.dataset, args.num_classes
    )
    print("最佳 mIoU epoch 的类别 IoU: " + ", ".join(
        f"{name}={iou * 100:.2f}%" for name, iou in zip(class_names, per_class_iou)
    ))
    print(f"训练时间: {training_time:.2f} 秒")
    
    return {
        "model_name": model_name,
        "best_miou": best_miou,
        "best_metrics": best_metrics,
        "training_time": training_time,
        "save_path": model_save_path,
        "last_save_path": last_model_save_path,
        "num_params": num_params,
        "active_experts": list(model.active_experts)
        if isinstance(model, (MoESteelUnet, MoESteelUNetPDF, MoESteelUNetLast)) else [],
        "best_gate_stats": best_gate_stats,
        "model_config": model.get_model_config()
        if isinstance(model, MorphoMoEFrameworkAblation)
        else None,
        "training_protocol": {
            "dataset": args.dataset,
            "data_root": os.path.abspath(args.data_root),
            "train_split": args.train_split,
            "test_split": args.test_split,
            "augment": not args.no_augment,
            "clahe": not args.no_clahe,
            "sp_threshold": args.sp_threshold,
            "random_seed": args.random_seed,
            "optimizer": args.optimizer,
            "learning_rate": args.lr,
            "weight_decay": args.weight_decay,
            "scheduler": args.scheduler,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "gradient_clip_max_norm": 5.0,
            "loss": "CrossEntropyLoss + DiceLoss",
            "pdf_spec_loss_weight": args.pdf_spec_loss_weight,
            "best_checkpoint_metric": "mIoU",
        }
        if isinstance(model, MorphoMoEFrameworkAblation)
        else None,
    }


def write_per_class_iou_report(dataset_save_dir: str, dataset: str, num_classes: int, results):
    """Write the per-class IoU at each model's best-mIoU epoch for paper tables."""
    class_names = get_class_names(dataset, num_classes)
    csv_path = os.path.join(dataset_save_dir, "per_class_iou.csv")
    fields = ["model_name", "best_epoch", *[f"{name}_IoU" for name in class_names],
              "mIoU", "mDice", "Acc", "training_time"]
    existing = {}
    if os.path.exists(csv_path):
        with open(csv_path, newline="", encoding="utf-8") as f:
            existing = {row["model_name"]: row for row in csv.DictReader(f)}

    for result in results:
        metrics = result["best_metrics"]
        ordered_iou = ordered_per_class_metric(metrics, "IoU_per_class", dataset, num_classes)
        row = {
            "model_name": result["model_name"],
            "best_epoch": metrics["epoch"],
            "mIoU": f"{metrics['mIoU']:.6f}",
            "mDice": f"{metrics['mDice']:.6f}",
            "Acc": f"{metrics['Acc']:.6f}",
            "training_time": f"{result['training_time']:.2f}",
        }
        row.update({f"{name}_IoU": f"{iou:.6f}" for name, iou in zip(class_names, ordered_iou)})
        existing[result["model_name"]] = row

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for model_name in sorted(existing):
            writer.writerow({field: existing[model_name].get(field, "") for field in fields})
    return csv_path


def print_dataset_info(train_loader: DataLoader, val_loader: DataLoader, dataset_name: str):
    """输出数据集信息"""
    print(f"\n{'='*60}")
    print(f"数据集信息: {dataset_name.upper()}")
    print(f"{'='*60}")
    
    # 获取第一个样本的信息
    train_sample = next(iter(train_loader))
    val_sample = next(iter(val_loader))
    
    # 图像尺寸信息
    train_img_shape = train_sample['image'].shape
    val_img_shape = val_sample['image'].shape
    print(f"训练集图像尺寸: {train_img_shape[3]}x{train_img_shape[2]} (WxH)")
    print(f"验证集图像尺寸: {val_img_shape[3]}x{val_img_shape[2]} (WxH)")
    
    # 掩码信息
    train_mask = train_sample['mask']
    val_mask = val_sample['mask']
    
    # 统计训练集掩码中的唯一值
    train_unique = torch.unique(train_mask)
    val_unique = torch.unique(val_mask)
    
    print(f"训练集掩码唯一值: {train_unique.tolist()}")
    print(f"验证集掩码唯一值: {val_unique.tolist()}")
    print(f"训练集掩码种类数: {len(train_unique)}")
    print(f"验证集掩码种类数: {len(val_unique)}")
    
    # 统计所有训练样本的掩码种类
    all_train_labels = set()
    all_val_labels = set()
    
    # 检查前100个训练样本
    for i, batch in enumerate(train_loader):
        if i >= 100:  # 只检查前100个批次
            break
        unique_labels = torch.unique(batch['mask'])
        all_train_labels.update(unique_labels.tolist())
    
    # 检查所有验证样本
    for batch in val_loader:
        unique_labels = torch.unique(batch['mask'])
        all_val_labels.update(unique_labels.tolist())
    
    print(f"训练集(前100批次)所有掩码种类: {sorted(list(all_train_labels))}")
    print(f"验证集所有掩码种类: {sorted(list(all_val_labels))}")
    print(f"训练集(前100批次)掩码种类总数: {len(all_train_labels)}")
    print(f"验证集掩码种类总数: {len(all_val_labels)}")
    
    # 根据数据集类型显示特定信息
    if dataset_name == "severstal":
        print(f"\nSeverstal Steel数据集信息:")
        print(f"- 缺陷类型: 0=无缺陷, 1=缺陷类型1, 2=缺陷类型2, 3=缺陷类型3")
        print(f"- 图像尺寸: 1600x256 (原始尺寸，无resize)")
    elif dataset_name == "magnetic":
        print(f"\nMagnetic-tile数据集信息:")
        print(f"- 缺陷类型: 0-5 (6种类型)")
        print(f"- 图像尺寸: 512x512 (resize后)")
    elif dataset_name == "neu":
        print(f"\nNEU_Seg数据集信息:")
        print(f"- 缺陷类型: 0-3 (4种类型)")
        print(f"- 图像尺寸: 256x256 (resize后)")
    elif dataset_name == "bsdata":
        print(f"\nBSData数据集信息:")
        print(f"- 缺陷类型: 0=背景, 1=缺陷 (二分类)")
        print(f"- 原始掩膜: 0/255，读取时转换为 0/1")


def set_random_seed(seed: int):
    """设置随机种子"""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def main():
    args = parse_args()
    device = torch.device(args.device)
    args.num_classes = get_num_classes_for_dataset(args.dataset)

    # Dataset-level initialization. Each model below repeats the seed reset
    # and data-loader construction, preserving independent ablation rows.
    set_random_seed(args.random_seed)

    print(f"设备: {device}")
    print(f"数据集: {args.dataset}")
    print(f"训练模型: {args.models}")
    print(f"训练轮数: {args.epochs}")
    print(f"批次大小: {args.batch_size}")
    print(f"学习率: {args.lr}")
    print(f"随机种子: {args.random_seed}")

    # 创建数据加载器
    train_loader, val_loader = make_dataloaders_train_test(
        args.dataset,
        args.data_root,
        args.train_split,
        args.test_split,
        args.batch_size,
        args.num_workers,
        apply_clahe=not args.no_clahe,
        sp_threshold=args.sp_threshold,
        augment=not args.no_augment,
        num_classes=args.num_classes,
        random_seed=args.random_seed,
    )
    
    print(f"训练集大小: {len(train_loader.dataset)}")
    print(f"测试集大小: {len(val_loader.dataset)}")
    
    print_dataset_info(train_loader, val_loader, args.dataset)
    
    # 训练所有模型
    results = []
    total_start_time = time.time()
    
    for model_name in args.models:
        # Isolation boundary: do not let the preceding model's initialization,
        # DataLoader sampling, or augmentation RNG affect this model.
        set_random_seed(args.random_seed)
        train_loader, val_loader = make_dataloaders_train_test(
            args.dataset,
            args.data_root,
            args.train_split,
            args.test_split,
            args.batch_size,
            args.num_workers,
            apply_clahe=not args.no_clahe,
            sp_threshold=args.sp_threshold,
            augment=not args.no_augment,
            num_classes=args.num_classes,
            random_seed=args.random_seed,
        )
        print(f"\n[实验隔离] 重置 seed={args.random_seed}，为 {model_name} 创建独立 DataLoader。")
        result = train_model(model_name, train_loader, val_loader, args, device, args.save_dir)
        results.append(result)

        # Persist completed models immediately. If a later model crashes or is
        # stopped, the already completed models retain their best-epoch rows.
        dataset_save_dir = get_dataset_save_dir(args.save_dir, args)
        update_moe_ablation_reports(dataset_save_dir, results)
        framework_paths = update_framework_ablation_reports(
            dataset_save_dir, results
        )
        per_class_csv_path = write_per_class_iou_report(
            dataset_save_dir, args.dataset, args.num_classes, results
        )
        if any(
            item["model_name"] in ALL_FORMAL_MOE_ABLATION_MODELS
            for item in results
        ):
            print(
                "已写入当前已完成模型的专家消融结果: "
                f"{os.path.join(dataset_save_dir, 'moe_ablation_results.txt')}"
            )
        if framework_paths is not None:
            print(
                "已按 M1-M8 固定顺序增量写入整体框架消融结果: "
                f"{framework_paths['text']}"
            )
    
    total_time = time.time() - total_start_time
    
    # 打印最终结果对比
    print(f"\n{'='*80}")
    print("训练结果对比")
    print(f"{'='*80}")
    print(f"{'模型':<12} {'参数量(M)':<10} {'最佳mIoU':<10} {'最佳mDice':<10} {'最佳Acc':<10} {'训练时间(秒)':<12}")
    print("-" * 100)
    
    for result in results:
        print(f"{result['model_name']:<12} {result['num_params']/1e6:<10.2f} {result['best_miou']:<10.4f} "
              f"{result['best_metrics']['mDice']:<10.4f} {result['best_metrics']['Acc']:<10.4f} "
              f"{result['training_time']:<12.2f}")

    class_names = get_class_names(args.dataset, args.num_classes)
    print(f"\n最佳 mIoU epoch 的类别 IoU（%）")
    print(f"{'模型':<20}" + "".join(f"{name:<12}" for name in class_names))
    print("-" * (20 + 12 * len(class_names)))
    for result in results:
        ious = ordered_per_class_metric(
            result["best_metrics"], "IoU_per_class", args.dataset, args.num_classes
        )
        print(f"{result['model_name']:<20}" + "".join(f"{iou * 100:<12.2f}" for iou in ious))
    
    print(f"\n总训练时间: {total_time:.2f} 秒")
    print(f"模型保存目录: {dataset_save_dir}")
    
    # 保存结果到文件 - 根据数据集名称保存
    dataset_save_dir = get_dataset_save_dir(args.save_dir, args)
    result_file = os.path.join(dataset_save_dir, "result.txt")
    with open(result_file, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("多模型训练结果对比\n")
        f.write("="*80 + "\n")
        f.write(f"训练时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"训练轮数: {args.epochs}\n")
        f.write(f"批次大小: {args.batch_size}\n")
        f.write(f"学习率: {args.lr}\n")
        f.write(f"总训练时间: {total_time:.2f} 秒\n\n")
        
        f.write(f"{'模型':<12} {'参数量(M)':<10} {'最佳mIoU':<10} {'最佳mDice':<10} {'最佳Acc':<10} {'训练时间(秒)':<12}\n")
        f.write("-" * 100 + "\n")
        
        for result in results:
            f.write(f"{result['model_name']:<12} {result['num_params']/1e6:<10.2f} {result['best_miou']:<10.4f} "
                   f"{result['best_metrics']['mDice']:<10.4f} {result['best_metrics']['Acc']:<10.4f} "
                   f"{result['training_time']:<12.2f}\n")

        f.write("\n最佳 mIoU epoch 的类别 IoU（%）\n")
        f.write(f"{'模型':<20}" + "".join(f"{name:<12}" for name in class_names) + "\n")
        f.write("-" * (20 + 12 * len(class_names)) + "\n")
        for result in results:
            ious = ordered_per_class_metric(
                result["best_metrics"], "IoU_per_class", args.dataset, args.num_classes
            )
            f.write(f"{result['model_name']:<20}" + "".join(f"{iou * 100:<12.2f}" for iou in ious) + "\n")
        
        f.write("\n" + "="*80 + "\n")
    
    print(f"训练结果已保存到: {result_file}")
    print(f"各类别 IoU 已保存到: {per_class_csv_path}")


if __name__ == "__main__":
    main()