"""
BiSeNet模型
基于论文: BiSeNet: Bilateral Segmentation Network for Real-time Semantic Segmentation
BiSeNet是一个双路径网络，包含Spatial Path和Context Path，用于实时语义分割
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import List, Optional
import timm


class ConvBNReLU(nn.Module):
    """卷积 + BatchNorm + ReLU"""
    
    def __init__(self, in_channels: int, out_channels: int, kernel_size: int = 3,
                 stride: int = 1, padding: int = 1, groups: int = 1, bias: bool = False):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size, stride, padding, groups=groups, bias=bias)
        self.bn = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU(inplace=True)
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.relu(self.bn(self.conv(x)))


class SpatialPath(nn.Module):
    """空间路径 - 保持高分辨率特征"""
    
    def __init__(self, in_channels: int = 3):
        super().__init__()
        self.conv1 = ConvBNReLU(in_channels, 64, kernel_size=3, stride=2, padding=1)
        self.conv2 = ConvBNReLU(64, 128, kernel_size=3, stride=2, padding=1)
        self.conv3 = ConvBNReLU(128, 256, kernel_size=3, stride=2, padding=1)
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.conv1(x)  # 1/2
        x = self.conv2(x)  # 1/4
        x = self.conv3(x)  # 1/8
        return x


class AttentionRefinementModule(nn.Module):
    """注意力精炼模块"""
    
    def __init__(self, in_channels: int):
        super().__init__()
        self.global_avg_pool = nn.AdaptiveAvgPool2d(1)
        self.conv = nn.Sequential(
            nn.Conv2d(in_channels, in_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(in_channels),
            nn.Sigmoid()
        )
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # 全局平均池化
        global_features = self.global_avg_pool(x)
        
        # 生成注意力权重
        attention_weights = self.conv(global_features)
        
        # 应用注意力权重
        return x * attention_weights


class FeatureFusionModule(nn.Module):
    """特征融合模块"""
    
    def __init__(self, spatial_channels: int, context_channels: int, out_channels: int):
        super().__init__()
        self.spatial_channels = spatial_channels
        self.context_channels = context_channels
        self.out_channels = out_channels
        
        # 空间特征处理
        self.spatial_conv = nn.Sequential(
            nn.Conv2d(spatial_channels, out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels)
        )
        
        # 上下文特征处理
        self.context_conv = nn.Sequential(
            nn.Conv2d(context_channels, out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels)
        )
        
        # 注意力机制
        self.attention = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(out_channels, out_channels // 4, kernel_size=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels // 4, out_channels, kernel_size=1),
            nn.Sigmoid()
        )
        
        # 最终融合
        self.fusion_conv = nn.Sequential(
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
        
    def forward(self, spatial_feat: torch.Tensor, context_feat: torch.Tensor) -> torch.Tensor:
        # 处理空间特征
        spatial_feat = self.spatial_conv(spatial_feat)
        
        # 处理上下文特征
        context_feat = self.context_conv(context_feat)
        
        # 上采样上下文特征到空间特征尺寸
        context_feat = F.interpolate(context_feat, size=spatial_feat.shape[2:], 
                                   mode='bilinear', align_corners=False)
        
        # 特征融合
        fused_feat = spatial_feat + context_feat
        
        # 应用注意力机制
        attention_weights = self.attention(fused_feat)
        fused_feat = fused_feat * attention_weights
        
        # 最终融合
        fused_feat = self.fusion_conv(fused_feat)
        
        return fused_feat


class ContextPath(nn.Module):
    """上下文路径 - 使用预训练backbone提取语义特征"""
    
    def __init__(self, backbone_name: str = 'resnet18', pretrained: bool = True):
        super().__init__()
        self.backbone_name = backbone_name
        
        if backbone_name.startswith('resnet'):
            self._init_resnet_backbone(backbone_name, pretrained)
        else:
            # 使用timm backbone
            self._init_timm_backbone(backbone_name, pretrained)
        
        # ARM模块：与 features[-2] (1/16) 和 features[-1] (1/32) 的通道对齐
        self.arm16 = AttentionRefinementModule(self.channels[3])  # 1/16: 256 for resnet18
        self.arm32 = AttentionRefinementModule(self.channels[4])  # 1/32: 512 for resnet18
        
        # 全局平均池化：输入为 1/32 特征通道
        self.global_context = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(self.channels[4], self.channels[4], kernel_size=1, bias=False),
            nn.BatchNorm2d(self.channels[4]),
            nn.ReLU(inplace=True)
        )
        
    def _init_resnet_backbone(self, backbone_name: str, pretrained: bool):
        """初始化ResNet backbone"""
        if backbone_name == 'resnet18':
            self.backbone = timm.create_model('resnet18', pretrained=pretrained, features_only=True)
            self.channels = [64, 64, 128, 256, 512]
        elif backbone_name == 'resnet34':
            self.backbone = timm.create_model('resnet34', pretrained=pretrained, features_only=True)
            self.channels = [64, 64, 128, 256, 512]
        elif backbone_name == 'resnet50':
            self.backbone = timm.create_model('resnet50', pretrained=pretrained, features_only=True)
            self.channels = [64, 256, 512, 1024, 2048]
        else:
            raise ValueError(f"Unsupported ResNet backbone: {backbone_name}")
            
    def _init_timm_backbone(self, backbone_name: str, pretrained: bool):
        """初始化timm backbone"""
        self.backbone = timm.create_model(backbone_name, pretrained=pretrained, features_only=True)
        
        # 获取特征通道数
        with torch.no_grad():
            dummy_input = torch.randn(1, 3, 224, 224)
            features = self.backbone(dummy_input)
            self.channels = [f.shape[1] for f in features]
            
    def forward(self, x: torch.Tensor) -> List[torch.Tensor]:
        # 获取backbone特征
        features = self.backbone(x)
        
        # 使用最后两个特征层
        feat16 = features[-2]  # 1/16 (channels[3])
        feat32 = features[-1]  # 1/32 (channels[4])
        
        # 应用ARM
        feat16 = self.arm16(feat16)
        feat32 = self.arm32(feat32)
        
        # 全局上下文
        global_context = self.global_context(feat32)
        
        # 上采样全局上下文到feat32尺寸
        global_context = F.interpolate(global_context, size=feat32.shape[2:], 
                                     mode='bilinear', align_corners=False)
        
        # 融合全局上下文
        feat32 = feat32 + global_context
        
        return [feat16, feat32]


class BiSeNet(nn.Module):
    """BiSeNet模型"""
    
    def __init__(self, in_channels: int = 3, num_classes: int = 4,
                 backbone_name: str = 'resnet18', pretrained: bool = True):
        super().__init__()
        self.num_classes = num_classes
        
        # 空间路径
        self.spatial_path = SpatialPath(in_channels)
        
        # 上下文路径
        self.context_path = ContextPath(backbone_name, pretrained)
        
        # 特征融合模块
        self.feature_fusion = FeatureFusionModule(
            spatial_channels=256,
            context_channels=self.context_path.channels[3],  # feat16 channels after ARM (256 for resnet18)
            out_channels=256
        )
        
        # 分类器
        self.classifier = nn.Sequential(
            nn.Conv2d(256, 256, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.Dropout2d(0.1),
            nn.Conv2d(256, num_classes, kernel_size=1)
        )
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        input_size = x.shape[2:]
        
        # 空间路径
        spatial_feat = self.spatial_path(x)
        
        # 上下文路径
        context_feats = self.context_path(x)
        context_feat = context_feats[0]  # 使用1/16特征
        
        # 特征融合
        fused_feat = self.feature_fusion(spatial_feat, context_feat)
        
        # 分类
        output = self.classifier(fused_feat)
        
        # 上采样到输入尺寸
        output = F.interpolate(output, size=input_size, mode='bilinear', align_corners=False)
        
        return output


class BiSeNetV2(nn.Module):
    """BiSeNet V2 - 增强版"""
    
    def __init__(self, in_channels: int = 3, num_classes: int = 4,
                 backbone_name: str = 'resnet18', pretrained: bool = True):
        super().__init__()
        self.num_classes = num_classes
        
        # 空间路径
        self.spatial_path = SpatialPath(in_channels)
        
        # 上下文路径
        self.context_path = ContextPath(backbone_name, pretrained)
        
        # 增强特征融合模块
        self.feature_fusion = EnhancedFeatureFusionModule(
            spatial_channels=256,
            context_channels=self.context_path.channels[2],
            out_channels=256
        )
        
        # 增强分类器
        self.classifier = nn.Sequential(
            nn.Conv2d(256, 256, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.Conv2d(256, 128, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.Dropout2d(0.1),
            nn.Conv2d(128, num_classes, kernel_size=1)
        )
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        input_size = x.shape[2:]
        
        # 空间路径
        spatial_feat = self.spatial_path(x)
        
        # 上下文路径
        context_feats = self.context_path(x)
        context_feat = context_feats[0]
        
        # 特征融合
        fused_feat = self.feature_fusion(spatial_feat, context_feat)
        
        # 分类
        output = self.classifier(fused_feat)
        
        # 上采样到输入尺寸
        output = F.interpolate(output, size=input_size, mode='bilinear', align_corners=False)
        
        return output


class EnhancedFeatureFusionModule(nn.Module):
    """增强版特征融合模块"""
    
    def __init__(self, spatial_channels: int, context_channels: int, out_channels: int):
        super().__init__()
        self.spatial_channels = spatial_channels
        self.context_channels = context_channels
        self.out_channels = out_channels
        
        # 空间特征处理
        self.spatial_conv = nn.Sequential(
            nn.Conv2d(spatial_channels, out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
        
        # 上下文特征处理
        self.context_conv = nn.Sequential(
            nn.Conv2d(context_channels, out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
        
        # 多尺度注意力机制
        self.multi_scale_attention = nn.ModuleList([
            nn.Sequential(
                nn.AdaptiveAvgPool2d(1),
                nn.Conv2d(out_channels, out_channels // 4, kernel_size=1),
                nn.ReLU(inplace=True),
                nn.Conv2d(out_channels // 4, out_channels, kernel_size=1),
                nn.Sigmoid()
            ),
            nn.Sequential(
                nn.AdaptiveAvgPool2d(2),
                nn.Conv2d(out_channels, out_channels // 4, kernel_size=1),
                nn.ReLU(inplace=True),
                nn.Conv2d(out_channels // 4, out_channels, kernel_size=1),
                nn.Sigmoid()
            ),
            nn.Sequential(
                nn.AdaptiveAvgPool2d(4),
                nn.Conv2d(out_channels, out_channels // 4, kernel_size=1),
                nn.ReLU(inplace=True),
                nn.Conv2d(out_channels // 4, out_channels, kernel_size=1),
                nn.Sigmoid()
            )
        ])
        
        # 最终融合
        self.fusion_conv = nn.Sequential(
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
        
    def forward(self, spatial_feat: torch.Tensor, context_feat: torch.Tensor) -> torch.Tensor:
        # 处理空间特征
        spatial_feat = self.spatial_conv(spatial_feat)
        
        # 处理上下文特征
        context_feat = self.context_conv(context_feat)
        
        # 上采样上下文特征到空间特征尺寸
        context_feat = F.interpolate(context_feat, size=spatial_feat.shape[2:], 
                                   mode='bilinear', align_corners=False)
        
        # 特征融合
        fused_feat = spatial_feat + context_feat
        
        # 多尺度注意力
        attention_weights = []
        for attention in self.multi_scale_attention:
            weight = attention(fused_feat)
            weight = F.interpolate(weight, size=fused_feat.shape[2:], 
                                 mode='bilinear', align_corners=False)
            attention_weights.append(weight)
        
        # 融合多尺度注意力
        final_attention = sum(attention_weights) / len(attention_weights)
        fused_feat = fused_feat * final_attention
        
        # 最终融合
        fused_feat = self.fusion_conv(fused_feat)
        
        return fused_feat


def test_bisenet():
    """测试BiSeNet模型"""
    print("=== BiSeNet 模型测试 ===")
    
    # 测试BiSeNet
    model_bisenet = BiSeNet(in_channels=3, num_classes=4, backbone_name='resnet18', pretrained=False)
    x = torch.randn(2, 3, 224, 224)
    y = model_bisenet(x)
    print(f"BiSeNet - 输入: {x.shape}, 输出: {y.shape}")
    
    # 测试BiSeNet V2
    model_bisenet_v2 = BiSeNetV2(in_channels=3, num_classes=4, backbone_name='resnet18', pretrained=False)
    y = model_bisenet_v2(x)
    print(f"BiSeNet V2 - 输入: {x.shape}, 输出: {y.shape}")
    
    # 计算参数量
    total_params = sum(p.numel() for p in model_bisenet.parameters() if p.requires_grad)
    print(f"BiSeNet 参数量: {total_params/1e6:.2f}M")
    
    total_params = sum(p.numel() for p in model_bisenet_v2.parameters() if p.requires_grad)
    print(f"BiSeNet V2 参数量: {total_params/1e6:.2f}M")


if __name__ == "__main__":
    test_bisenet()
