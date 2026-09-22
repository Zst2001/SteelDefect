import torch
import torch.nn as nn
import torch.nn.functional as F
import timm


class _PositionAttentionModule(nn.Module):
    """ Position attention module """

    def __init__(self, in_channels):
        super().__init__()
        self.conv_b = nn.Conv2d(in_channels, in_channels // 8, 1)
        self.conv_c = nn.Conv2d(in_channels, in_channels // 8, 1)
        self.conv_d = nn.Conv2d(in_channels, in_channels, 1)
        self.alpha = nn.Parameter(torch.zeros(1))
        self.softmax = nn.Softmax(dim=-1)

    def forward(self, x):
        batch_size, _, height, width = x.size()
        feat_b = self.conv_b(x).view(batch_size, -1, height * width).permute(0, 2, 1)
        feat_c = self.conv_c(x).view(batch_size, -1, height * width)
        attention_s = self.softmax(torch.bmm(feat_b, feat_c))
        feat_d = self.conv_d(x).view(batch_size, -1, height * width)
        feat_e = torch.bmm(feat_d, attention_s.permute(0, 2, 1)).view(batch_size, -1, height, width)
        out = self.alpha * feat_e + x
        return out


class _ChannelAttentionModule(nn.Module):
    """ Channel attention module """

    def __init__(self):
        super().__init__()
        self.beta = nn.Parameter(torch.zeros(1))
        self.softmax = nn.Softmax(dim=-1)

    def forward(self, x):
        batch_size, _, height, width = x.size()
        feat_a = x.view(batch_size, -1, height * width)
        feat_a_transpose = x.view(batch_size, -1, height * width).permute(0, 2, 1)
        attention = torch.bmm(feat_a, feat_a_transpose)
        attention_new = torch.max(attention, dim=-1, keepdim=True)[0].expand_as(attention) - attention
        attention = self.softmax(attention_new)
        feat_e = torch.bmm(attention, feat_a).view(batch_size, -1, height, width)
        out = self.beta * feat_e + x
        return out


class _DAHead(nn.Module):
    def __init__(self, in_channels, nclass, aux=True, norm_layer=nn.BatchNorm2d):
        super().__init__()
        self.aux = aux
        inter_channels = in_channels // 4
        self.conv_p1 = nn.Sequential(
            nn.Conv2d(in_channels, inter_channels, 3, padding=1, bias=False),
            norm_layer(inter_channels),
            nn.ReLU(True)
        )
        self.conv_c1 = nn.Sequential(
            nn.Conv2d(in_channels, inter_channels, 3, padding=1, bias=False),
            norm_layer(inter_channels),
            nn.ReLU(True)
        )
        self.pam = _PositionAttentionModule(inter_channels)
        self.cam = _ChannelAttentionModule()
        self.conv_p2 = nn.Sequential(
            nn.Conv2d(inter_channels, inter_channels, 3, padding=1, bias=False),
            norm_layer(inter_channels),
            nn.ReLU(True)
        )
        self.conv_c2 = nn.Sequential(
            nn.Conv2d(inter_channels, inter_channels, 3, padding=1, bias=False),
            norm_layer(inter_channels),
            nn.ReLU(True)
        )
        self.out = nn.Sequential(
            nn.Dropout(0.1),
            nn.Conv2d(inter_channels, nclass, 1)
        )
        if aux:
            self.conv_p3 = nn.Sequential(
                nn.Dropout(0.1),
                nn.Conv2d(inter_channels, nclass, 1)
            )
            self.conv_c3 = nn.Sequential(
                nn.Dropout(0.1),
                nn.Conv2d(inter_channels, nclass, 1)
            )

    def forward(self, x):
        feat_p = self.conv_p1(x)
        feat_p = self.pam(feat_p)
        feat_p = self.conv_p2(feat_p)

        feat_c = self.conv_c1(x)
        feat_c = self.cam(feat_c)
        feat_c = self.conv_c2(feat_c)

        feat_fusion = feat_p + feat_c

        outputs = []
        fusion_out = self.out(feat_fusion)
        outputs.append(fusion_out)
        if self.aux:
            p_out = self.conv_p3(feat_p)
            c_out = self.conv_c3(feat_c)
            outputs.append(p_out)
            outputs.append(c_out)
        return tuple(outputs)


class DANet(nn.Module):
    def __init__(self, in_channels=3, num_classes=4, backbone_name='resnet18', pretrained=False, aux=False):
        super().__init__()
        self.aux = aux
        self.encoder = timm.create_model(backbone_name, pretrained=pretrained, features_only=True)
        # 依据 timm resnet：channels 例如 resnet18 -> [64, 64, 128, 256, 512]
        with torch.no_grad():
            dummy = torch.zeros(1, 3, 224, 224)
            feats = self.encoder(dummy)
            self.channels = [f.shape[1] for f in feats]
        in_ch = self.channels[-1]
        c3_ch = self.channels[-2]
        self.head = _DAHead(in_ch, num_classes, aux=aux)
        if aux:
            self.aux_identity = nn.Identity()  # 保留接口一致性
        self._c3_ch = c3_ch

    def forward(self, x):
        size = x.size()[2:]
        feats = self.encoder(x)
        c3 = feats[-2]
        c4 = feats[-1]
        outputs = []
        head_outs = self.head(c4)
        x0 = F.interpolate(head_outs[0], size, mode='bilinear', align_corners=True)
        outputs.append(x0)
        if self.aux and len(head_outs) > 2:
            x1 = F.interpolate(head_outs[1], size, mode='bilinear', align_corners=True)
            x2 = F.interpolate(head_outs[2], size, mode='bilinear', align_corners=True)
            outputs.append(x1)
            outputs.append(x2)
        return outputs[0]





