import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import models


class PSPModule(nn.Module):
    def __init__(self, in_channels, out_channels, pool_sizes=[1, 2, 3, 6]):
        super(PSPModule, self).__init__()
        self.pool_sizes = pool_sizes
        self.stages = nn.ModuleList()
        
        def gn(c: int) -> nn.GroupNorm:
            # 使用 GroupNorm 以避免在 1x1 特征图 + batch=1 时的 BN 统计报错
            num_groups = min(32, c)
            # 确保可整除
            while c % num_groups != 0 and num_groups > 1:
                num_groups -= 1
            return nn.GroupNorm(num_groups=num_groups, num_channels=c)
        
        for pool_size in pool_sizes:
            self.stages.append(nn.Sequential(
                nn.AdaptiveAvgPool2d(pool_size),
                nn.Conv2d(in_channels, out_channels, 1, bias=False),
                gn(out_channels),
                nn.ReLU(inplace=True)
            ))
        
        self.bottleneck = nn.Sequential(
            nn.Conv2d(in_channels + len(pool_sizes) * out_channels, out_channels, 3, padding=1, bias=False),
            gn(out_channels),
            nn.ReLU(inplace=True),
            nn.Dropout(0.1)
        )

    def forward(self, x):
        h, w = x.size(2), x.size(3)
        pyramids = [x]
        
        for stage in self.stages:
            pyramid = stage(x)
            pyramid = F.interpolate(pyramid, size=(h, w), mode='bilinear', align_corners=False)
            pyramids.append(pyramid)
        
        output = torch.cat(pyramids, dim=1)
        output = self.bottleneck(output)
        return output


class PSPNet(nn.Module):
    def __init__(self, in_channels=3, num_classes=4, backbone='resnet50', pretrained=True):
        super(PSPNet, self).__init__()
        
        if backbone == 'resnet50':
            self.backbone = models.resnet50(pretrained=pretrained)
            feature_channels = 2048
        elif backbone == 'resnet101':
            self.backbone = models.resnet101(pretrained=pretrained)
            feature_channels = 2048
        else:
            raise ValueError(f"Unsupported backbone: {backbone}")
        
        # Remove the last two layers (avgpool and fc)
        self.backbone = nn.Sequential(*list(self.backbone.children())[:-2])
        
        # PSP module
        self.psp = PSPModule(feature_channels, feature_channels // 4)
        
        # Final classifier
        self.classifier = nn.Sequential(
            nn.Conv2d(feature_channels // 4, 512, 3, padding=1, bias=False),
            nn.BatchNorm2d(512),
            nn.ReLU(inplace=True),
            nn.Dropout(0.1),
            nn.Conv2d(512, num_classes, 1)
        )

    def forward(self, x):
        input_size = x.shape[-2:]
        
        # Extract features through backbone
        x = self.backbone(x)
        
        # PSP module
        x = self.psp(x)
        
        # Final classification
        x = self.classifier(x)
        
        # Upsample to original size
        x = F.interpolate(x, size=input_size, mode='bilinear', align_corners=False)
        
        return x


if __name__ == "__main__":
    # 简单自检
    model = PSPNet(in_channels=3, num_classes=4, backbone='resnet50', pretrained=False)
    model.eval()
    with torch.no_grad():
        x = torch.randn(1, 3, 200, 200)
        y = model(x)
        print("PSPNet Output:", tuple(y.shape))

