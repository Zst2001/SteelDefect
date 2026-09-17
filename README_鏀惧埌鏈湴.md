# 解压到 Windows 本地 Steel_lab

本包已在服务器打好，对应需求：CPU 三档 baseline（UNet / DeepLabV3+ / UNet++）+ NEU 权重 + 20 对样例。

**本环境无法直接写入** `F:\360MoveData\Users\40336\Desktop\Bofang\Steel_lab`。请把压缩包下载到那台 Windows 电脑后再解压。

## 服务器上的文件

| 路径 | 说明 |
|------|------|
| `/root/My/exports/Steel_lab_payload/` | 已展开的目录（可直接在 Cursor 远程工作区里看） |
| `/root/My/exports/Steel_lab_payload.tar.gz` | 约 280MB，建议用这个拷走 |

## 拷到本机（任选一种）

在 **Windows PowerShell**（把用户名/IP 换成你 SSH 进这台机的账号）：

```powershell
scp USER@SERVER:/root/My/exports/Steel_lab_payload.tar.gz "F:\360MoveData\Users\40336\Desktop\Bofang\"
```

或用 WinSCP / Cursor 远程资源管理器：下载 `Steel_lab_payload.tar.gz`。

解压到网站仓库根目录，使结构为：

```text
F:\360MoveData\Users\40336\Desktop\Bofang\Steel_lab\
  third_party\
    compare\          unet.py / deeplabv3_plus.py / unet_plus_plus.py / __init__.py
    dataset_defects.py
    utils_losses_metrics.py
    viz_color.py
    load_checkpoint.py
  assets\
    baselines\neu\    best_unet.pth / best_deeplabv3.pth / best_unetpp.pth
    samples\neu\      images\ + masks\  （000001–000020）
  docs\
    本地需拷贝资源清单.md
```

若 `Steel_lab` 里已经有你自己的 `docs/` 需求文档，只覆盖 `third_party/` 和 `assets/`，不要覆盖你已写好的需求分析。

## 加载约定（写网站时用）

- 权重键一般是 `model_state`，不是裸 `state_dict`
- NEU `num_classes = 4`
- DeepLab 必须 `pretrained=False`（CPU 机没有 ImageNet 权重也没关系）
- 对比预处理必须走 `dataset_defects.py`（CLAHE / 椒盐 / resize），与训练一致
- 上色用 `viz_color.py`（BGR）
- **不要**再拷 `compare/__init__.py` 原文件（会 import Mamba）

## 未包含（有意）

- 完整 NEU 训练集 / 全部 840 张 test
- Mamba / MorphoMoE 权重与代码
- `train_multi.py` / `eval.py` 全文
- `fast_scnn`（服务器上没有对应 `.pth`）
- `bisenet`（可选；需要再拷 `bisenet.py` + `best_bisenet.pth` + 装 `timm`）
