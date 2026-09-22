import torch
import torch.nn as nn
import torch.nn.functional as F
import math


class OverlapPatchEmbed(nn.Module):
    """Image to Patch Embedding with overlapping"""
    
    def __init__(self, img_size=224, patch_size=7, stride=4, in_chans=3, embed_dim=768):
        super().__init__()
        self.img_size = img_size
        self.patch_size = patch_size
        self.proj = nn.Conv2d(in_chans, embed_dim, kernel_size=patch_size, stride=stride,
                              padding=(patch_size // 2, patch_size // 2))
        self.norm = nn.LayerNorm(embed_dim)

    def forward(self, x):
        x = self.proj(x)
        _, _, H, W = x.shape
        x = x.flatten(2).transpose(1, 2)
        x = self.norm(x)
        return x, H, W


class EfficientSelfAttention(nn.Module):
    """Efficient Self-Attention"""
    
    def __init__(self, dim, num_heads=8, qkv_bias=False, attn_drop=0., proj_drop=0., sr_ratio=1):
        super().__init__()
        assert dim % num_heads == 0, f"dim {dim} should be divided by num_heads {num_heads}."
        
        self.dim = dim
        self.num_heads = num_heads
        head_dim = dim // num_heads
        self.scale = head_dim ** -0.5
        
        self.q = nn.Linear(dim, dim, bias=qkv_bias)
        self.kv = nn.Linear(dim, dim * 2, bias=qkv_bias)
        self.attn_drop = nn.Dropout(attn_drop)
        self.proj = nn.Linear(dim, dim)
        self.proj_drop = nn.Dropout(proj_drop)
        
        self.sr_ratio = sr_ratio
        if sr_ratio > 1:
            self.sr = nn.Conv2d(dim, dim, kernel_size=sr_ratio, stride=sr_ratio)
            self.norm = nn.LayerNorm(dim)

    def forward(self, x, H, W):
        B, N, C = x.shape
        q = self.q(x).reshape(B, N, self.num_heads, C // self.num_heads).permute(0, 2, 1, 3)
        
        if self.sr_ratio > 1:
            x_ = x.permute(0, 2, 1).reshape(B, C, H, W)
            x_ = self.sr(x_).reshape(B, C, -1).permute(0, 2, 1)
            x_ = self.norm(x_)
            kv = self.kv(x_).reshape(B, -1, 2, self.num_heads, C // self.num_heads).permute(2, 0, 3, 1, 4)
        else:
            kv = self.kv(x).reshape(B, -1, 2, self.num_heads, C // self.num_heads).permute(2, 0, 3, 1, 4)
        k, v = kv[0], kv[1]
        
        attn = (q @ k.transpose(-2, -1)) * self.scale
        attn = attn.softmax(dim=-1)
        attn = self.attn_drop(attn)
        
        x = (attn @ v).transpose(1, 2).reshape(B, N, C)
        x = self.proj(x)
        x = self.proj_drop(x)
        
        return x


class MixFFN(nn.Module):
    """Mix-FFN"""
    
    def __init__(self, in_features, hidden_features=None, out_features=None, act_layer=nn.GELU, drop=0.):
        super().__init__()
        out_features = out_features or in_features
        hidden_features = hidden_features or in_features
        self.fc1 = nn.Linear(in_features, hidden_features)
        self.dwconv = nn.Conv2d(hidden_features, hidden_features, 3, 1, 1, bias=True, groups=hidden_features)
        self.act = act_layer()
        self.fc2 = nn.Linear(hidden_features, out_features)
        self.drop = nn.Dropout(drop)

    def forward(self, x, H, W):
        x = self.fc1(x)
        x = x.transpose(1, 2).view(-1, x.size(-1), H, W)
        x = self.dwconv(x)
        x = x.flatten(2).transpose(1, 2)
        x = self.act(x)
        x = self.drop(x)
        x = self.fc2(x)
        x = self.drop(x)
        return x


class TransformerBlock(nn.Module):
    """Transformer Block"""
    
    def __init__(self, dim, num_heads, mlp_ratio=4., qkv_bias=False, drop=0., attn_drop=0.,
                 drop_path=0., act_layer=nn.GELU, norm_layer=nn.LayerNorm, sr_ratio=1):
        super().__init__()
        self.norm1 = norm_layer(dim)
        self.attn = EfficientSelfAttention(
            dim, num_heads=num_heads, qkv_bias=qkv_bias, attn_drop=attn_drop, proj_drop=drop, sr_ratio=sr_ratio)
        self.drop_path = nn.Identity()  # Simplified drop path
        self.norm2 = norm_layer(dim)
        mlp_hidden_dim = int(dim * mlp_ratio)
        self.mlp = MixFFN(in_features=dim, hidden_features=mlp_hidden_dim, act_layer=act_layer, drop=drop)

    def forward(self, x, H, W):
        x = x + self.drop_path(self.attn(self.norm1(x), H, W))
        x = x + self.drop_path(self.mlp(self.norm2(x), H, W))
        return x


class SegFormer(nn.Module):
    """SegFormer: Simple and Efficient Design for Semantic Segmentation"""
    
    def __init__(self, in_channels=3, num_classes=4, embed_dims=[64, 128, 320, 512], 
                 num_heads=[1, 2, 5, 8], mlp_ratios=[4, 4, 4, 4], qkv_bias=False,
                 drop_rate=0.0, attn_drop_rate=0.0, drop_path_rate=0.1):
        super().__init__()
        
        self.num_classes = num_classes
        self.embed_dims = embed_dims
        
        # Patch embeddings
        self.patch_embed1 = OverlapPatchEmbed(img_size=224, patch_size=7, stride=4, 
                                            in_chans=in_channels, embed_dim=embed_dims[0])
        self.patch_embed2 = OverlapPatchEmbed(img_size=224, patch_size=3, stride=2, 
                                            in_chans=embed_dims[0], embed_dim=embed_dims[1])
        self.patch_embed3 = OverlapPatchEmbed(img_size=224, patch_size=3, stride=2, 
                                            in_chans=embed_dims[1], embed_dim=embed_dims[2])
        self.patch_embed4 = OverlapPatchEmbed(img_size=224, patch_size=3, stride=2, 
                                            in_chans=embed_dims[2], embed_dim=embed_dims[3])
        
        # Transformer blocks
        self.block1 = nn.ModuleList([
            TransformerBlock(dim=embed_dims[0], num_heads=num_heads[0], mlp_ratio=mlp_ratios[0], 
                           qkv_bias=qkv_bias, drop=drop_rate, attn_drop=attn_drop_rate, sr_ratio=8)
            for _ in range(2)
        ])
        self.block2 = nn.ModuleList([
            TransformerBlock(dim=embed_dims[1], num_heads=num_heads[1], mlp_ratio=mlp_ratios[1], 
                           qkv_bias=qkv_bias, drop=drop_rate, attn_drop=attn_drop_rate, sr_ratio=4)
            for _ in range(2)
        ])
        self.block3 = nn.ModuleList([
            TransformerBlock(dim=embed_dims[2], num_heads=num_heads[2], mlp_ratio=mlp_ratios[2], 
                           qkv_bias=qkv_bias, drop=drop_rate, attn_drop=attn_drop_rate, sr_ratio=2)
            for _ in range(6)
        ])
        self.block4 = nn.ModuleList([
            TransformerBlock(dim=embed_dims[3], num_heads=num_heads[3], mlp_ratio=mlp_ratios[3], 
                           qkv_bias=qkv_bias, drop=drop_rate, attn_drop=attn_drop_rate, sr_ratio=1)
            for _ in range(3)
        ])
        
        # Decoder
        self.decode_head = SegFormerHead(embed_dims, num_classes)
        
    def forward(self, x):
        B = x.shape[0]
        input_size = x.shape[-2:]
        
        # Encoder
        x, H, W = self.patch_embed1(x)
        for blk in self.block1:
            x = blk(x, H, W)
        x1 = x.reshape(B, H, W, -1).permute(0, 3, 1, 2).contiguous()
        
        x, H, W = self.patch_embed2(x1)
        for blk in self.block2:
            x = blk(x, H, W)
        x2 = x.reshape(B, H, W, -1).permute(0, 3, 1, 2).contiguous()
        
        x, H, W = self.patch_embed3(x2)
        for blk in self.block3:
            x = blk(x, H, W)
        x3 = x.reshape(B, H, W, -1).permute(0, 3, 1, 2).contiguous()
        
        x, H, W = self.patch_embed4(x3)
        for blk in self.block4:
            x = blk(x, H, W)
        x4 = x.reshape(B, H, W, -1).permute(0, 3, 1, 2).contiguous()
        
        # Decoder
        x = self.decode_head([x1, x2, x3, x4])
        
        # 上采样到输入分辨率
        x = F.interpolate(x, size=input_size, mode='bilinear', align_corners=False)
        return x


class SegFormerHead(nn.Module):
    """SegFormer Head"""
    
    def __init__(self, embed_dims, num_classes):
        super().__init__()
        self.linear_c = nn.ModuleList([nn.Linear(embed_dims[i], embed_dims[0]) for i in range(4)])
        self.linear_fuse = nn.Conv2d(embed_dims[0] * 4, embed_dims[0], 1)
        self.linear_pred = nn.Conv2d(embed_dims[0], num_classes, 1)
        self.dropout = nn.Dropout2d(0.1)
        
    def forward(self, inputs):
        c1, c2, c3, c4 = inputs
        n, _, h, w = c4.shape
        
        _c4 = self.linear_c[3](c4.permute(0, 2, 3, 1)).permute(0, 3, 1, 2)
        _c4 = F.interpolate(_c4, size=c1.size()[2:], mode='bilinear', align_corners=False)
        
        _c3 = self.linear_c[2](c3.permute(0, 2, 3, 1)).permute(0, 3, 1, 2)
        _c3 = F.interpolate(_c3, size=c1.size()[2:], mode='bilinear', align_corners=False)
        
        _c2 = self.linear_c[1](c2.permute(0, 2, 3, 1)).permute(0, 3, 1, 2)
        _c2 = F.interpolate(_c2, size=c1.size()[2:], mode='bilinear', align_corners=False)
        
        _c1 = self.linear_c[0](c1.permute(0, 2, 3, 1)).permute(0, 3, 1, 2)
        
        _c = self.linear_fuse(torch.cat([_c4, _c3, _c2, _c1], dim=1))
        
        x = self.dropout(_c)
        x = self.linear_pred(x)
        
        return x


if __name__ == "__main__":
    # 简单自检
    model = SegFormer(in_channels=3, num_classes=4)
    model.eval()
    with torch.no_grad():
        x = torch.randn(1, 3, 200, 200)
        y = model(x)
        print("SegFormer Output:", tuple(y.shape))

