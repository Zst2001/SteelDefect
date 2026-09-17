import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import models


class ASPPConv(nn.Module):
    def __init__(self, in_channels, out_channels, dilation):
        super(ASPPConv, self).__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, 3, padding=dilation, dilation=dilation, bias=False)
        self.bn = self._gn(out_channels)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        return self.relu(self.bn(self.conv(x)))

    @staticmethod
    def _gn(c: int) -> nn.GroupNorm:
        num_groups = min(32, c)
        while c % num_groups != 0 and num_groups > 1:
            num_groups -= 1
        return nn.GroupNorm(num_groups=num_groups, num_channels=c)


class ASPPPooling(nn.Module):
    def __init__(self, in_channels, out_channels):
        super(ASPPPooling, self).__init__()
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.conv = nn.Conv2d(in_channels, out_channels, 1, bias=False)
        self.bn = self._gn(out_channels)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        size = x.shape[-2:]
        x = self.pool(x)
        x = self.relu(self.bn(self.conv(x)))
        return F.interpolate(x, size=size, mode='bilinear', align_corners=False)

    @staticmethod
    def _gn(c: int) -> nn.GroupNorm:
        num_groups = min(32, c)
        while c % num_groups != 0 and num_groups > 1:
            num_groups -= 1
        return nn.GroupNorm(num_groups=num_groups, num_channels=c)


class ASPP(nn.Module):
    def __init__(self, in_channels, out_channels=256):
        super(ASPP, self).__init__()
        dilations = [1, 6, 12, 18]
        
        self.convs = nn.ModuleList()
        self.convs.append(ASPPConv(in_channels, out_channels, dilations[0]))
        self.convs.append(ASPPConv(in_channels, out_channels, dilations[1]))
        self.convs.append(ASPPConv(in_channels, out_channels, dilations[2]))
        self.convs.append(ASPPConv(in_channels, out_channels, dilations[3]))
        self.convs.append(ASPPPooling(in_channels, out_channels))
        
        self.project = nn.Sequential(
            nn.Conv2d(5 * out_channels, out_channels, 1, bias=False),
            self._gn(out_channels),
            nn.ReLU(inplace=True),
            nn.Dropout(0.5)
        )

    def forward(self, x):
        res = []
        for conv in self.convs:
            res.append(conv(x))
        res = torch.cat(res, dim=1)
        return self.project(res)

    @staticmethod
    def _gn(c: int) -> nn.GroupNorm:
        num_groups = min(32, c)
        while c % num_groups != 0 and num_groups > 1:
            num_groups -= 1
        return nn.GroupNorm(num_groups=num_groups, num_channels=c)


class DeepLabV3Plus(nn.Module):
    def __init__(self, in_channels=3, num_classes=4, backbone='resnet50', pretrained=False):
        super(DeepLabV3Plus, self).__init__()
        
        if backbone == 'resnet50':
            self.backbone = models.resnet50(weights=None if not pretrained else models.ResNet50_Weights.DEFAULT)
            low_level_channels = 256
            high_level_channels = 2048
        elif backbone == 'resnet101':
            self.backbone = models.resnet101(weights=None if not pretrained else models.ResNet101_Weights.DEFAULT)
            low_level_channels = 256
            high_level_channels = 2048
        else:
            raise ValueError(f"Unsupported backbone: {backbone}")
        
        # ASPP module
        self.aspp = ASPP(high_level_channels, 256)
        
        # Low-level feature processing
        self.low_level_conv = nn.Sequential(
            nn.Conv2d(low_level_channels, 48, 1, bias=False),
            self._gn(48),
            nn.ReLU(inplace=True)
        )
        
        # Final classifier
        self.classifier = nn.Sequential(
            nn.Conv2d(256 + 48, 256, 3, padding=1, bias=False),
            self._gn(256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.5),
            nn.Conv2d(256, 256, 3, padding=1, bias=False),
            self._gn(256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.1),
            nn.Conv2d(256, num_classes, 1)
        )

    def forward(self, x):
        input_size = x.shape[-2:]
        
        # Extract features using ResNet backbone
        x = self.backbone.conv1(x)
        x = self.backbone.bn1(x)
        x = self.backbone.relu(x)
        x = self.backbone.maxpool(x)
        x = self.backbone.layer1(x)
        low_level_features = x
        x = self.backbone.layer2(x)
        x = self.backbone.layer3(x)
        x = self.backbone.layer4(x)
        
        # ASPP on high-level features (2048 channels)
        x = self.aspp(x)
        
        # Upsample to 1/4 size
        x = F.interpolate(x, size=(input_size[0]//4, input_size[1]//4), 
                         mode='bilinear', align_corners=False)
        
        # Process low-level features
        low_level_features = self.low_level_conv(low_level_features)
        
        # Concatenate
        x = torch.cat([x, low_level_features], dim=1)
        
        # Final classification
        x = self.classifier(x)
        
        # Upsample to original size
        x = F.interpolate(x, size=input_size, mode='bilinear', align_corners=False)
        
        return x

    @staticmethod
    def _gn(c: int) -> nn.GroupNorm:
        num_groups = min(32, c)
        while c % num_groups != 0 and num_groups > 1:
            num_groups -= 1
        return nn.GroupNorm(num_groups=num_groups, num_channels=c)


if __name__ == "__main__":
    # 简单自检
    model = DeepLabV3Plus(in_channels=3, num_classes=4, backbone='resnet50', pretrained=False)
    model.eval()
    with torch.no_grad():
        x = torch.randn(1, 3, 200, 200)
        y = model(x)
        print("DeepLabV3+ Output:", tuple(y.shape))

