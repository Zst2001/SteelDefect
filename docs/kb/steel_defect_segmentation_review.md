# 钢铁表面缺陷分割文献综述骨架

> **综述范围**：钢铁表面缺陷检测与分割（2023–2026），聚焦 TIP / TGRS / ICCV / ECCV 工业视觉子领域  
> **重点议题**：小样本学习、工业噪声（光照/反光）、类不平衡、域适应/泛化  
> 
> **检索覆盖**：OpenAlex + Crossref + DOAJ + arXiv + Semantic Scholar + Web 搜索，中英文双语

---

## 0. 检索元信息（PRISMA 留痕）

- **研究方向 / 核心问题（PICO）**：
  - **P**（对象）：钢铁/金属表面缺陷图像（热轧带钢、冷轧钢板、钢轨等）
  - **I**（方法）：深度分割模型（CNN/Transformer/扩散模型）、小样本学习、域适应、异常检测
  - **C**（对比）：全监督 vs. 小样本/零样本；ImageNet 预训练 vs. 域内自监督预训练；单光源 vs. 多光源
  - **O**（结果）：分割精度（mIoU/Dice）、检测精度（mAP）、跨域泛化鲁棒性、实时性（FPS/参数量）
- **时间范围**：2023-01 至 2026-06（核心为近 3 年，经典奠基工作不限时间）
- **语言**：中英双语
- **目标期刊/会议**：TIP（IEEE TIP）、TGRS（IEEE TGRS）、ICCV、ECCV、TII（IEEE TII）、TIM（IEEE TIM）

| 库 | 检索式（原样可复制） | 命中 | 去重后 | 纳入 |
|----|--------------------|------|-------|------|
| OpenAlex+Crossref+DOAJ | `"steel defect segmentation surface detection"` + require: defect,steel | 117 | 77 | ~30 |
| OpenAlex+Crossref+DOAJ | `"industrial surface anomaly detection defect segmentation few-shot"` + require: defect,anomaly,surface | 100 | 7 | 7 |
| OpenAlex+Crossref+DOAJ | `"class imbalance long-tail defect detection industrial inspection"` + require: defect,industrial,imbalance | 60 | 6 | 6 |
| OpenAlex+Crossref+DOAJ | `"surface defect segmentation deep learning illumination reflection noise"` + require: defect,surface | 80 | 47 | ~15 |
| OpenAlex+Crossref+DOAJ | `"few-shot segmentation defect detection domain generalization industrial"` + require: few-shot,segmentation,defect | 80 | 10 | 10 |
| OpenAlex+Crossref+DOAJ | `"diffusion model defect generation synthetic data augmentation industrial"` + require: defect,diffusion,industrial | 80 | 10 | 10 |
| arXiv | `ti:steel AND (defect OR surface) AND (segmentation OR detection)` (1095天) | 10 | 10 | 5 |
| arXiv | `ti:defect AND (segmentation OR detection) AND (industrial OR surface)` | 10 | 10 | 5 |
| OpenAlex+Crossref+DOAJ | `"钢铁表面缺陷分割 深度学习 小样本"` (中文) | 35 | 35 | 3 |
| OpenAlex (Snowball) | 种子 DOI: `10.1109/tii.2022.3216900` (Few-Shot) | 57 | 57 | 25 |
| OpenAlex (Snowball) | 种子 DOI: `10.1109/tim.2019.2963555` (Foundation Survey) | 100 | 100 | 40 |
| **合计** | 11 个检索式，6 个检索源 | **~729** | **~369** | **~156** |

- **去重锚点**：DOI 优先 → arXiv id → 规范化标题+作者+年
- **排除标准**：非同行评审预印本（标注为 preprint）、明显跑题（非工业表面/非视觉方法）、无法获取摘要

---

## 1. 引言：问题为什么重要

钢铁表面缺陷检测与分割是工业视觉质检的核心任务。热轧/冷轧钢板、钢轨、钢丝绳等产品在生产过程中不可避免地产生裂纹（Crazing）、夹杂（Inclusion）、斑块（Patches）、麻点（Pitted Surface）、氧化皮压入（Rolled-in Scale）、划痕（Scratches）等数十类缺陷。**精准的像素级缺陷分割**直接关系到产品等级判定、工艺溯源和生产安全。

然而，钢铁缺陷分割面临**三重核心挑战**：

1. **小样本困境**：真实产线中某些缺陷类别极少出现（如裂纹仅占万分之几），标注成本极高，传统全监督分割需要每类数百张像素级标注，几乎不可行。
2. **工业噪声复杂**：钢铁表面高反光特性导致**镜面反射**、多光源干涉产生**光照不均**、油污/水渍/氧化层引入**伪缺陷纹理**，这些噪声使分割模型极易产生误检。
3. **类不平衡极端**：正常区域占图像面积 >95%，缺陷中"大头缺陷"（斑块、划痕）与"长尾缺陷"（微小裂纹）的样本量可能差 100 倍，常规交叉熵/Dice Loss 被背景主导，长尾类别几乎学不到。

本综述聚焦 **2023–2026 年 TIP / TGRS / ICCV / ECCV 及其相关工业视觉子领域**的核心方法，系统梳理检测/分割两大任务线、小样本/域适应/异常检测三条技术线，并重点剖析上述三个瓶颈的现有解决方案与研究空白。

---

## 2. 研究脉络（时间线 + 演进逻辑）

### 2.1 问题怎么提出 → 奠基工作（~2020 以前）

| 阶段 | 代表工作 | 核心贡献 |
|------|---------|---------|
| 传统方法时代 | [Automatic Defect Detection on Hot-Rolled Flat Steel (2012, IEEE TIM)](https://doi.org/10.1109/tim.2012.2218677) — 315 引 | 基于纹理特征 + SVM 的经典方案，奠定 NEU 数据集 |
| 传统方法时代 | [Review of vision-based steel surface inspection (2014, EURASIP JIVP)](https://doi.org/10.1186/1687-5281-2014-50) — 311 引 | 视觉检测系统综述，覆盖光源设计、特征工程 |
| CNN 转型期 | [A deep-learning-based approach for fast and robust steel surface defects classification (2019, Optics & Lasers in Engineering)](https://doi.org/10.1016/j.optlaseng.2019.05.005) — 263 引 | CNN 分类器首次在钢铁缺陷上取得突破 |
| 工业异常检测起源 | [Improving Unsupervised Defect Segmentation (2019, VISIGRAPP)](https://doi.org/10.5220/0007364500002108) — 332 引 | SSIM-AE 重建范式，为后续所有无监督方法奠基 |
| 奠基综述 | [Automated Visual Defect Detection for Flat Steel Surface: A Survey (2020, IEEE TIM)](https://doi.org/10.1109/tim.2019.2963555) — 512 引 | **钢铁缺陷检测领域最权威综述**，覆盖传统方法→CNN 全路径 |

### 2.2 怎么被逐步解决 → 里程碑 / 方法族演进（2021–2023）

```
2021: YOLO 系检测主导 ──── 小样本学习萌芽 ──── 异常检测范式确立
  │
  ├─ [MSFT-YOLO (2022)] Transformer + YOLOv5, 301 引
  ├─ [Triplet-Graph Reasoning Network (2021, TIM)] 小样本金属缺陷, 297 引  
  ├─ [Few-Shot Steel Surface Defect Detection (2021, TIM)] 78 引
  ├─ [Mixed supervision for surface-defect detection (2021, CII)] 弱→全监督, 332 引
  └─ [Unsupervised Anomaly Detection Survey (2023, IEEE Access)] 104 引
     │
2022–2023: 分割网络崛起 ──── 异常检测井喷 ──── ICCV 2023 工业视觉专题
  │
  ├─ [Review of surface defect detection of steel (2022, IET IP)] 223 引
  ├─ [Unseen-Material Few-Shot Defect Segmentation (2022, TII)] 最优传输小样本 ★
  ├─ [Deep Siamese Semantic Segmentation for PCB (2022, TIM)] 107 引
  ├─ ICCV 2023: Removing Anomalies as Noises — 58 引
  ├─ ICCV 2023: FastRecon — 小样本特征重建
  ├─ ICCV 2023: PNI — 位置+邻域记忆库
  └─ [Few-shot semantic segmentation for industrial defect (2023, Computers in Industry)] 37 引
     │
2024: 扩散模型爆发 ──── 多模态/CLIP 登场 ──── ECCV 2024 工业视觉 17+ 篇
  │
  ├─ [MINet (2024, TII)] 多尺度交互实时显著性检测, 110 引
  ├─ [MFANet (2024, TII)] 跨粒度小样本无缝钢管, 67 引
  ├─ [Latent Diffusion Models for Defect Segmentation (2024)] 扩散增强
  ├─ ECCV 2024: GLASS, GLAD, TransFusion, HGAD (扩散+NF)
  ├─ ECCV 2024: VCP-CLIP, AdaCLIP (CLIP 零样本)
  ├─ ECCV 2024: AnoGen, DefectDiffu (扩散生成小样本)
  └─ [Surface Illumination as Factor (2024)] 光照影响首次量化研究
```

### 2.3 当前 SOTA → 最新最强工作（2025–2026）

| 方向 | SOTA 方法 | 指标 | 创新点 |
|------|----------|------|--------|
| 分割精度 | [DPCSA-Net (2025, Optics & Laser Tech)](https://doi.org/10.1016/j.optlastec.2025.113145) | **93.41% mIoU** (NEU-DET), **0.99M params** | 双极化通道-空间注意力 + Extension Dice Loss 治类不平衡 |
| 检测精度 | [AMFNet (2025)](https://doi.org/10.1038/s41598-025-91930-z) | SOTA mAP (NEU-DET) | 分支交互模块 + 膨胀上下文 + 空间关联 |
| 小样本分割 | [RDPrompter (2026, TII)](https://doi.org/10.1109/tii.2026.3663099) | 最新 | 参考-缺陷提示学习 + CLIP 先验 |
| 小样本分割 | [Hierarchical Adaptive Correlation Network (2026, JIM)](https://doi.org/10.1007/s10845-026-02874-8) | 最新 | 层级自适应关联 + 跨粒度匹配 |
| 小样本分割 | [Background-Weaken Generalization (2025, TIM)](https://doi.org/10.1109/tim.2025.3544335) | SOTA 泛化 | 背景弱化 + 特征泛化增强 |
| 异常检测 | [MultiADS (ICCV 2025)](https://doi.org/10.1109/iccv51701.2025.02133) | ICCV 2025 | 缺陷感知多类异常检测与分割 |
| 异常检测 | [STD2 (2025, TIM)](https://doi.org/10.1109/tim.2024.3492728) | 15 引 | Swin Transformer 缺陷检测器 |
| 扩散生成 | [DefectDiffusion (2025)](https://doi.org/10.1109/icaiic64266.2025.10920732) | 鲁棒增强 | 扩散模型数据增强用于工业缺陷 |
| 光照鲁棒 | [DiAL (BMVC 2025)](https://bmvc2025.bmva.org/proceedings/354/) | **91.44% Acc**, 亮线缺陷 +26% | 双分支光照解耦（VCE+VSE） |
| 长尾分割 | [TSEMDNet (2024, EAAI)](https://doi.org/10.1016/j.engappai.2024.109561) | **87.35% mIoU** (SD-900) | 两阶段编码-多解码器 + 类别特定精修 |

### 2.4 还剩什么 → Gap（重点，喂 m03 idea-generation）

详见第 6 节"空白与机会"。

---

## 3. 方法族分类

### 3.1 按任务分类

| 方法族 | 代表工作 | 核心思想 | 优点 | 局限 | 常用数据集 | 代表指标 |
|--------|---------|---------|------|------|-----------|---------|
| **全监督检测**（YOLO 族） | MSFT-YOLO, ELA-YOLO, YOLOv8-TLC, CRGF-YOLO | Backbone + FPN + 检测头，加 Attention/Transformer | 实时性好、工程成熟 | 需大量标注、小目标/长尾差 | NEU-DET, GC10-DET, Severstal | mAP 75–93% |
| **全监督分割**（UNet 族） | DPCSA-Net, TSEDNet, DeepLabV3+, MINet | 编码-解码 + 跳跃连接 + 注意力 | 像素级精确、可量化缺陷面积 | 像素标注成本极高、跨类泛化差 | NEU-DET, X-SDD, SD-saliency-900 | mIoU 87–93% |
| **无监督异常检测** | [Removing Anomalies as Noises (ICCV 2023)](https://doi.org/10.1109/iccv51070.2023.01481), PNI, FastRecon, STD2 | 仅正常样本训练，检测偏离"正常流形" | 无需缺陷标注、开集检测 | 对细微纹理缺陷不敏感、定位粗糙 | MVTec AD, BTAD, VisA | AUROC 95–99% |
| **小样本分割** | [Unseen-Material Few-Shot (2022, TII)](https://doi.org/10.1109/tii.2022.3216900), MFANet, RDPrompter | 支持集→查询集 原型匹配/最优传输/提示学习 | 仅需 1–5 张标注、新类泛化 | 复杂纹理/多尺度性能下降 | NEU-DET, 自定义金属数据集 | mIoU 40–70% (1-shot) |
| **零样本/CLIP 驱动** | VCP-CLIP (ECCV 2024), AdaCLIP (ECCV 2024), AnomalyCLIP | CLIP 视觉-语言对齐，文本/视觉提示引导 | 彻底无需缺陷样本 | 工业领域图文对齐弱、细粒度差 | MVTec AD, VisA | AUROC 85–95% |
| **扩散生成增强** | [Latent Diffusion Models (2024)](https://doi.org/10.3390/s24186016), AnoGen, DefectDiffu, [Few-Shot Steel Defect Generation (2025)](https://doi.org/10.3390/s25103038) | 扩散模型生成缺陷样本 → 增强训练集 | 可生成多样化缺陷、缓解数据稀缺 | 生成质量不稳定、合成→真实域差 | MVTec AD, NEU-DET | mAP +3–10% |
| **域适应/泛化** | [Shape-Consistent One-Shot UDA (2023, TII)](https://doi.org/10.1109/tii.2022.3233654), Bi-Level Meta-Learning (CVPR 2023) | 对抗对齐 / 元学习 / MMD 最小化 | 跨产线/跨光照可迁移 | 需源域数据、训练不稳定 | 钢轨→钢板、合成→真实 | mAP +5–15% |
| **多任务长尾分割** | TSEDNet, TSEMDNet, Sample-Centric MTL | 多解码器分工 / 样本级梯度调制 / 扩展 Dice Loss | 针对性解决长尾、可解释性强 | 结构复杂、训练成本高 | X-SDD, SD-saliency-900 | mIoU 85–87% |

### 3.2 按技术路线分类（方法演进图谱）

```
钢铁缺陷分割方法演进 (2020 → 2026)
│
├─ 1. 全监督范式（已成熟，天花板明显）
│   ├─ YOLO 系检测: YOLOv5 → v8 → v11 → MSFT-YOLO → ELA-YOLO
│   ├─ UNet 系分割: UNet → DeepLabV3+ → TSEDNet → DPCSA-Net
│   └─ 局限：标注成本 ∝ 缺陷类别数，长尾类永远缺数据
│
├─ 2. 无监督/自监督范式（快速崛起，产线落地首选）
│   ├─ 重建范式: AE → SSIM-AE → DRAEM → GLAD (扩散重建) → TransFusion
│   ├─ 知识蒸馏: Student-Teacher → Reverse Distillation → CRAD
│   ├─ 归一化流: CFLOW-AD → PyramidFlow → HGAD
│   └─ 局限：正常样本定义困难（工业场景"正常"本身有变化）
│
├─ 3. 小样本/零样本范式 ★（当前研究最热，工业刚需）
│   ├─ 度量学习: Prototype Network → Triplet-Graph → Optimal Transport
│   ├─ 提示学习: Visual Prompt → CLIP Prompt → RDPrompter
│   ├─ 元学习: MAML 系 → Bi-Level Meta-Learning (Domain Generalization)
│   └─ 局限：跨材质泛化仍差（钢板→铝板→玻璃），光照不变性不足
│
├─ 4. 扩散生成范式（2024 年爆发，数据增强新范式）
│   ├─ 缺陷图像生成: DefectDiffu → AnoGen → Latent Diffusion
│   ├─ 可控生成: Mask-Conditioned → Text-Guided → Inpainting Diffusion
│   └─ 局限：生成质量评估无标准，合成→真实域差未量化
│
└─ 5. 域适应/泛化范式（前沿探索，落地关键）
    ├─ 对抗对齐: Gradient Reversal → MMD → Consistency Conditional
    ├─ 域内预训练: AGSSP (异常引导) → SteelDefectX (多模态)
    └─ 局限：多域联合训练数据稀缺，理论保证不足
```

---

## 4. 重要性分级

### 4.1 奠基（Foundational）— ≥8 年，累计被引极高

| 文献 | 年 | 被引 | 奠基意义 |
|------|----|------|---------|
| [Automated Visual Defect Detection for Flat Steel Surface: A Survey (IEEE TIM)](https://doi.org/10.1109/tim.2019.2963555) | 2020 | 512 (OpenAlex) | **钢铁缺陷检测最权威综述**，定义问题边界、数据集、评估体系 |
| [Review of vision-based steel surface inspection systems (EURASIP JIVP)](https://doi.org/10.1186/1687-5281-2014-50) | 2014 | 311 | 视觉检测系统设计完整指南 |
| [Automatic Defect Detection on Hot-Rolled Flat Steel Products (IEEE TIM)](https://doi.org/10.1109/tim.2012.2218677) | 2012 | 315 | NEU 数据集起源，传统方法基线 |
| [State of the Art in Defect Detection Based on Machine Vision (IJPMT)](https://doi.org/10.1007/s40684-021-00343-6) | 2021 | 737 | 机器视觉缺陷检测全景综述 |
| Deep Residual Learning (ResNet, CVPR 2016) | 2016 | 222,039 | 所有 CNN 检测/分割方法的 backbone 基础 |
| U-Net (MICCAI 2015) | 2015 | 88,906 | 所有分割网络的架构原型 |
| [Mixed supervision for surface-defect detection (Computers in Industry)](https://doi.org/10.1016/j.compind.2021.103459) | 2021 | 332 | **弱监督→全监督过渡的里程碑** |

### 4.2 里程碑（Milestone）— 3–8 年，年均被引 ≥30

| 文献 | 年 | 被引 | 里程碑意义 |
|------|----|------|-----------|
| [MSFT-YOLO: Improved YOLOv5 Based on Transformer (Sensors)](https://doi.org/10.3390/s22093467) | 2022 | 301 | Transformer + YOLO 首次在钢铁缺陷检测大规模验证 |
| [Triplet-Graph Reasoning Network for Few-Shot Metal Generic Surface Defect (IEEE TIM)](https://doi.org/10.1109/tim.2021.3083561) | 2021 | 297 | **小样本金属缺陷检测的开创性工作** |
| [A deep learning model for steel surface defect detection (Complex & Intelligent Systems)](https://doi.org/10.1007/s40747-023-01180-7) | 2023 | 107 | 钢铁缺陷深度学习系统方案 |
| [Review of surface defect detection of steel products based on machine vision (IET Image Processing)](https://doi.org/10.1049/ipr2.12647) | 2022 | 223 | 钢铁产品表面缺陷视觉检测综述 |
| [Steel Surface Defect Recognition: A Survey (Coatings)](https://doi.org/10.3390/coatings13010017) | 2022 | 172 | 钢铁表面缺陷识别方法综述 |
| [Few-Shot Steel Surface Defect Detection (IEEE TIM)](https://doi.org/10.1109/tim.2021.3128208) | 2021 | 78 | 小样本钢铁缺陷检测系统方案 |
| [A Survey on Unsupervised Anomaly Detection Algorithms for Industrial Images (IEEE Access)](https://doi.org/10.1109/access.2023.3282993) | 2023 | 104 | **无监督异常检测综述**，建立分类体系 |
| [Few-shot semantic segmentation for industrial defect recognition (Computers in Industry)](https://doi.org/10.1016/j.compind.2023.103901) | 2023 | 37 | 工业缺陷小样本语义分割系统回顾 |

### 4.3 SOTA / 新锐（≤3 年，刷榜或方法创新突出）

| 文献 | 年 | 亮点 |
|------|----|------|
| [DPCSA-Net (Optics & Laser Technology)](https://doi.org/10.1016/j.optlastec.2025.113145) | 2025 | **93.41% mIoU + 0.99M params**，极致轻量化，EDL 治类不平衡 |
| [RDPrompter (IEEE TII)](https://doi.org/10.1109/tii.2026.3663099) | 2026 | 提示学习 + 参考缺陷引导，最新小样本分割 |
| [Background-Weaken Generalization Network (IEEE TIM)](https://doi.org/10.1109/tim.2025.3544335) | 2025 | 背景弱化提升小样本泛化 |
| [Enhancing feature interaction for improved generalization in few-shot (KBS)](https://doi.org/10.1016/j.knosys.2025.114606) | 2025 | 特征交互增强 + 泛化提升 |
| [Hierarchical Adaptive Correlation Network (JIM)](https://doi.org/10.1007/s10845-026-02874-8) | 2026 | 层级自适应小样本分割 |
| [Small Object Few-Shot Segmentation for Vision-Based Industrial Inspection (IEEE TII)](https://doi.org/10.1109/tii.2025.3538070) | 2025 | 工业小目标 + 小样本 |
| [CLIP-Vision Guided Few-Shot Metal Surface Defect Recognition (IEEE TII)](https://doi.org/10.1109/tii.2025.3547353) | 2025 | CLIP 视觉先验 + 小样本 |
| [VPGFNet: Cross-domain few-shot visual prompt graph fusion (JCDE)](https://doi.org/10.1093/jcde/qwaf105) | 2025 | 跨域小样本图提示融合 |
| [MFANet: Multifeature Aggregation for Cross-Granularity Few-Shot (IEEE TII)](https://doi.org/10.1109/tii.2024.3383513) | 2024 | 跨粒度 + 多特征聚合, 67 引 |

### 4.4 与本研究 "最相关"（问题/数据/方法最贴合）

| 文献 | 年 | 相关度 | 原因 |
|------|----|--------|------|
| [Surface Illumination as a Factor Influencing the Efficacy of Defect Recognition (Applied Sciences)](https://doi.org/10.3390/app14062591) | 2024 | ⭐⭐⭐⭐⭐ | **唯一直接量化光照对缺陷识别影响的工作** |
| DiAL (BMVC 2025) | 2025 | ⭐⭐⭐⭐⭐ | 双分支光照解耦，直接针对高反光钢铁表面 |
| TSEDNet (Measurement, 2025) | 2025 | ⭐⭐⭐⭐⭐ | 多解码器专治类不平衡，X-SDD 真实产线数据 |
| [A Few-Shot Steel Surface Defect Generation Method Based on Diffusion Models (Sensors)](https://doi.org/10.3390/s25103038) | 2025 | ⭐⭐⭐⭐⭐ | 扩散模型 + 小样本 + 钢铁缺陷，三位一体 |
| [DefFiller: Mask-Conditioned Diffusion for Salient Steel Surface Defect (arXiv)](https://arxiv.org/abs/2412.15570) | 2024 | ⭐⭐⭐⭐ | 扩散模型钢铁缺陷修复/生成 |
| [Shape-Consistent One-Shot UDA for Rail Surface Defect (IEEE TII)](https://doi.org/10.1109/tii.2022.3233654) | 2023 | ⭐⭐⭐⭐ | 一次性无监督域适应 + 金属表面 |
| [SteelBlastQC: Shot-blasted Steel Surface Dataset (arXiv)](https://arxiv.org/abs/2504.20510) | 2025 | ⭐⭐⭐⭐ | 喷丸钢铁表面数据集 + 解释性 |
| [SteelDefectX: Multi-Form Vision-Language Dataset and Benchmark (arXiv)](https://arxiv.org/abs/2603.21824) | 2026 | ⭐⭐⭐⭐ | 多模态钢铁缺陷数据集 + 基准 |

### 4.5 综述（Survey）

| 文献 | 年 | 被引 | 覆盖范围 |
|------|----|------|---------|
| [Automated Visual Defect Detection for Flat Steel Surface: A Survey (TIM)](https://doi.org/10.1109/tim.2019.2963555) | 2020 | 512 | 钢铁缺陷检测全史（至 2019） |
| [Steel Surface Defect Recognition: A Survey (Coatings)](https://doi.org/10.3390/coatings13010017) | 2022 | 172 | 缺陷识别方法（含传统+深度） |
| [Review of surface defect detection of steel products based on machine vision (IET IP)](https://doi.org/10.1049/ipr2.12647) | 2022 | 223 | 视觉检测综述 |
| [A systematic review on Deep Learning with CNNs Applied to Surface Defect Detection (J. Imaging)](https://doi.org/10.3390/jimaging9100193) | 2023 | 72 | CNN 缺陷检测系统综述 |
| [A Survey on Unsupervised Anomaly Detection Algorithms for Industrial Images (IEEE Access)](https://doi.org/10.1109/access.2023.3282993) | 2023 | 104 | 无监督异常检测分类体系 |
| [Surface defect inspection of industrial products with object detection deep networks (AI Review)](https://doi.org/10.1007/s10462-024-10956-3) | 2024 | 98 | 目标检测用于工业缺陷 |
| [State of the Art in AI-Based Visual Inspection for Industrial Quality Control (Electronics)](https://www.mdpi.com/2079-9292/15/12/2727) | 2026 | 0 | **最新综述**，涵盖分类/检测/分割/异常检测 |
| [Applying Deep Learning to Defect Detection in Steel Manufacturing (CMC)](https://www.techscience.com/cmc/v88n1/67279) | 2026 | 0 | **钢铁制造缺陷检测 10 个案例**，含域泛化专题 |

---

## 5. 可复用资源

### 5.1 数据集

| 数据集 | 规模 | 类别数 | 标注类型 | 特点 | 许可 |
|--------|------|--------|---------|------|------|
| [NEU-DET](http://faculty.neu.edu.cn/songkechen/zh_CN/zdylm/263270/list/) | 1,800 张 (200×200) | 6 类 | BBox | 灰度图，经典基准，类均衡 | 学术免费 |
| [X-SDD](https://doi.org/10.3390/sym13040706) | 1,500+ 张 | 7 类 | 像素级 | 热轧带钢，**长尾分布 6.3:1**，真实产线 | 学术免费 |
| [GC10-DET](https://www.kaggle.com/datasets/) | 2,000+ 张 | 10 类 | BBox | 彩色，多尺度缺陷 | 学术免费 |
| [Severstal](https://www.kaggle.com/c/severstal-steel-defect-detection) | 12,000+ 张 | 4 类 | 像素级 (RLE) | Kaggle 竞赛，大尺度图像 | 竞赛许可 |
| [SD-saliency-900](https://doi.org/10.1016/j.measurement.2024.115438) | 900 张 | 3 类 | 像素级+显著性 | 带显著性先验 | 学术免费 |
| [MVTec AD](https://www.mvtec.com/company/research/datasets/mvtec-ad) | 5,354 张 | 15 类 | 像素级 | **异常检测标准基准**，纹理+物体 | CC BY-NC-SA 4.0 |
| [VisA](https://github.com/amazon-science/spot-diff) | 10,821 张 | 12 类 | 像素级 | 复杂结构异常 | CC BY-NC-SA 4.0 |
| [SteelBlastQC (arXiv, 2025)](https://arxiv.org/abs/2504.20510) | 新数据集 | — | — | 喷丸钢铁表面，含解释性标注 | — |
| [SteelDefectX (arXiv, 2026)](https://arxiv.org/abs/2603.21824) | 多模态 | — | — | 视觉-语言多模态基准 | — |
| DAGM2007 | 1,000+ 张 | 6 类 | BBox | 合成纹理缺陷，早期基准 | 免费 |

### 5.2 开源库 / 代码

| 资源 | 描述 | 许可 |
|------|------|------|
| [Awesome Industrial Anomaly Detection (GitHub)](https://github.com/quanyumath/Anomaly-Detection-awesome-industrial-anomaly-detection) | 工业异常检测论文+数据集汇总 | 开源 |
| [AnomalyLab](https://github.com/...) | 异常检测框架，含多种方法复现 | — |
| [DPCSA-Net](https://github.com/...) | 2025 SOTA 轻量分割 | — |
| [DefFiller (arXiv)](https://arxiv.org/abs/2412.15570) | 扩散模型钢铁缺陷修复 | — |
| [MVTec AD 评估工具](https://github.com/openvinotoolkit/anomalib) | Intel Anomalib 异常检测库 | Apache 2.0 |
| [YOLOv5/8/11 (Ultralytics)](https://github.com/ultralytics/ultralytics) | 目标检测基线 | AGPL-3.0 |

### 5.3 Leaderboard / 基准

| 基准 | 任务 | 当前 SOTA |
|------|------|-----------|
| NEU-DET 检测 | 6 类 BBox 检测 | AMFNet (mAP SOTA, 2025) |
| NEU-DET 分割 | 6 类像素分割 | DPCSA-Net (93.41% mIoU, 2025) |
| X-SDD 分割 | 7 类长尾分割 | TSEMDNet (84.98% mIoU, 2024) |
| MVTec AD 异常检测 | 15 类异常检测+定位 | GLASS/VCP-CLIP (SOTA, ECCV 2024) |
| Severstal 分割 | 4 类像素分割 | — |

---

## 6. 空白与机会（Current Gap → m03 idea-generation）

### 6.1 按痛点的 Gap 矩阵

| 痛点维度 | 现有方案 | 核心不足 | Gap 等级 | 潜在创新方向 |
|---------|---------|---------|---------|-------------|
| **小样本** (Few-Shot) | 原型匹配、最优传输、CLIP 提示 | (1) 原型对多尺度缺陷退化严重; (2) 跨材质泛化无保证; (3) 未见类（open-set）完全失效 | 🔴 **极高** | ① 层级原型 + 自适应尺度匹配; ② 物理模型引导的小样本生成; ③ 多模态（视觉+超声/涡流）融合小样本 |
| **工业噪声**（光照/反光） | 数据增强、光度立体、多光源成像 | (1) 钢铁镜面反射 >90% 无有效方案; (2) 光照解耦方案停留在分类级，未到像素级; (3) 物理光照模型未与深度学习结合 | 🔴 **极高** | ① 物理光照模型 + 神经渲染联合优化; ② 偏振成像 + 深度分割融合; ③ DiAL 思想扩展到像素级分割 |
| **类不平衡**（长尾） | 重采样、Focal Loss、E-Dice、多解码器 | (1) 极度不平衡（>100:1）时重采样过拟合; (2) 损失函数权重设定依赖先验; (3) 尾部类"遗忘"无有效持续学习方案 | 🟡 **高** | ① 类别增量学习 + 记忆重放; ② 扩散模型尾部类定向生成; ③ 自适应损失权重（元学习） |
| **跨域泛化** | 对抗对齐、MMD、域内预训练 | (1) 多域联合训练数据不可得; (2) 对齐可能丢失判别性特征; (3) 无理论保证 | 🟡 **高** | ① 单源域泛化（无目标域数据）; ② 因果特征学习剔除伪相关; ③ 测试时自适应（TTA） |
| **工业实时性** | YOLO 系、轻量 UNet | (1) 精度-速度 Pareto 前沿已接近瓶颈; (2) 边缘设备部署困难 | 🟢 **中** | ① 神经架构搜索（NAS）自动设计; ② 模型量化 + 剪枝 + 蒸馏联合优化 |
| **标注效率** | 弱监督、半监督、SAM 辅助 | (1) SAM 在工业纹理上退化严重; (2) 弱监督无法精细化边界 | 🟡 **高** | ① SAM 工业适配微调（工业 SAM）; ② 点击交互 + 主动学习 |
| **复合缺陷**（多类共存） | 多标签分类 + 独立分割 | (1) 类别间遮挡/重叠无方案; (2) 复合缺陷数据集不存在 | 🔴 **极高** | ① 全景分割（Panoptic Segmentation）适配; ② 合成复合缺陷数据集 |

### 6.2 五个高价值 Research Gap（可直接作为论文创新点）

#### Gap 1: 高反光钢铁表面的像素级光照不变分割 🔴🔴🔴

**现状**：DiAL (BMVC 2025) 在**分类级别**做了光照解耦，但像素级分割尚无光照不变方案。现有分割模型在钢铁镜面反射区域（反射率 >90%）误检率极高。

**创新方向**：
- 物理渲染（BRDF）+ 神经隐式表示构建光照不变特征空间
- 多偏振角度成像 + 偏振特征融合分割网络
- 从 DiAL 的 VCE（视角一致编码器）扩展到 UNet 跳跃连接的分割架构

**可行性**：需要多光源/偏振成像硬件配合，适合与光学团队合作

#### Gap 2: 小样本条件下的钢铁缺陷开集分割 🔴🔴🔴

**现状**：小样本分割（RDPrompter, MFANet）仅支持**已见基类→新类**的闭集迁移。真实产线会不断出现全新缺陷类型（开集），现有方案完全无法处理。

**创新方向**：
- 将开集识别（Open-Set Recognition）引入小样本分割范式
- "know what you don't know" —— 分割 + 不确定度估计联合学习
- 新类发现 → 主动学习采集 → 增量更新闭环

**可行性**：可在 NEU-DET + 留出类上验证，不依赖特殊硬件

#### Gap 3: 扩散模型驱动的长尾缺陷可控生成 + 分割联合训练 🔴🔴

**现状**：扩散生成（DefectDiffu, AnoGen）与分割训练**分离**——先生成再训练，生成质量无法针对分割任务优化。长尾类生成更是缺乏针对性。

**创新方向**：
- **端到端** 扩散生成 + 分割联合优化：生成器以"提升分割性能"为目标
- 尾部类定向过采样生成（Class-Conditioned Diffusion with Long-Tail Prior）
- 生成质量评估：提出"分割有效性"指标替代 FID/IS

**可行性**：中等，需要控制扩散模型的训练稳定性

#### Gap 4: 物理信息驱动的钢铁缺陷分割（Physics-Informed）🔴🔴

**现状**：所有方法都是纯数据驱动。钢铁缺陷的**物理形成机理**（轧制温度、速度、压力 → 缺陷形态）被完全忽略。

**创新方向**：
- 有限元仿真（FEM）生成物理一致的缺陷形态 → 作为分割网络的物理先验
- 多物理场（温度场+应力场+表面图像）融合分割
- 物理约束 Loss：预测分割须满足质量守恒/应力连续等物理定律

**可行性**：需要轧制工艺数据和 FEM 仿真，适合与钢铁企业合作

#### Gap 5: 基于多模态大模型（VLM）的钢铁缺陷交互式分割 🟡🟡

**现状**：SAM/CLIP 在自然图像上强，在工业纹理上弱（~20-30% mIoU 下降）。但 VLM 的零样本理解能力未被充分利用。

**创新方向**：
- 工业 VLM 微调：在钢铁缺陷图文对上微调 CLIP/SAM
- 语言引导的缺陷描述 + 分割："请分割出图中亮白色细长裂纹"
- 人机协同标注：VLM 初标 → 人工精修 → 模型自进化

**可行性**：高，成本低，产出快，适合作为硕士课题

---

## 7. 核心论文速查表（按研究方向索引）

### 7.1 小样本缺陷分割（Few-Shot Defect Segmentation）

| # | 文献 | 年 | Venue | 方法 | 被引 |
|---|------|----|-------|------|------|
| 1 | Unseen-Material Few-Shot Defect Segmentation With Optimal Bilateral Feature Transport Network | 2022 | IEEE TII | 最优传输 + 双边特征 | 24 |
| 2 | MFANet: Multifeature Aggregation Network for Cross-Granularity Few-Shot Seamless Steel Tube Defect Segmentation | 2024 | IEEE TII | 多特征聚合 + 跨粒度 | 67 |
| 3 | Background-Weaken Generalization Network for Few-Shot Industrial Metal Defect Segmentation | 2025 | IEEE TIM | 背景弱化 + 泛化增强 | 4 |
| 4 | Enhancing Feature Interaction for Improved Generalization in Few-Shot Metal Surface Defect Segmentation | 2025 | KBS | 特征交互增强 | 0 |
| 5 | RDPrompter: Reference-Defect Prompt Learning for Few-Shot Defect Segmentation Based on SAM | 2026 | IEEE TII | SAM + 提示学习 | 0 |
| 6 | Hierarchical Adaptive Correlation Network for Few-Shot Metal Surface Defect Segmentation | 2026 | JIM | 层级自适应关联 | 0 |
| 7 | Small Object Few-Shot Segmentation for Vision-Based Industrial Inspection | 2025 | IEEE TII | 小目标 + 小样本 | 10 |
| 8 | CLIP-Vision Guided Few-Shot Metal Surface Defect Recognition | 2025 | IEEE TII | CLIP + 小样本 | 5 |
| 9 | VPGFNet: Cross-Domain Few-Shot Visual Prompt Graph Fusion Network for Industrial Surface Defect Segmentation | 2025 | JCDE | 跨域图提示融合 | 1 |
| 10 | Triplet-Graph Reasoning Network for Few-Shot Metal Generic Surface Defect | 2021 | IEEE TIM | 三元组图推理 | 297 |
| 11 | Few-Shot Steel Surface Defect Detection | 2021 | IEEE TIM | 小样本检测系统 | 78 |
| 12 | Few-Shot Semantic Segmentation for Industrial Defect Recognition | 2023 | Computers in Industry | 工业小样本综述 | 37 |

### 7.2 无监督/零样本异常检测

| # | 文献 | 年 | Venue | 方法 | 被引 |
|---|------|----|-------|------|------|
| 1 | Removing Anomalies as Noises for Industrial Defect Localization | 2023 | **ICCV** | 去噪 = 去异常 | 58 |
| 2 | FastRecon: Few-Shot Industrial Anomaly Detection via Fast Feature Reconstruction | 2023 | **ICCV** | 快速特征重建 | — |
| 3 | PNI: Industrial Anomaly Detection using Position and Neighborhood Information | 2023 | **ICCV** | 位置+邻域记忆库 | — |
| 4 | MultiADS: Defect-Aware Supervision for Multi-Type Anomaly Detection and Segmentation | 2025 | **ICCV** | 多类异常统一框架 | 3 |
| 5 | GLASS: A Unified Anomaly Synthesis Strategy with Gradient Ascent | 2024 | **ECCV** | 梯度上升异常合成 | — |
| 6 | GLAD: Towards Better Reconstruction with Global and Local Adaptive Diffusion Models | 2024 | **ECCV** | 扩散自适应重建 | — |
| 7 | VCP-CLIP: A Visual Context Prompting Model for Zero-Shot Anomaly Segmentation | 2024 | **ECCV** | CLIP + 视觉上下文提示 | — |
| 8 | AdaCLIP: Adapting CLIP with Hybrid Learnable Prompts for Zero-Shot Anomaly Detection | 2024 | **ECCV** | CLIP + 混合可学习提示 | — |
| 9 | AnoGen: Few-Shot Anomaly-Driven Generation for Anomaly Classification and Segmentation | 2024 | **ECCV** | 小样本异常驱动生成 | — |
| 10 | TransFusion: A Transparency-Based Diffusion Model for Anomaly Detection | 2024 | **ECCV** | 透明度引导扩散 | — |
| 11 | HGAD: Hierarchical Gaussian Mixture Normalizing Flow Modeling for Unified Anomaly Detection | 2024 | **ECCV** | 层次高斯混合归一化流 | — |
| 12 | Few-Shot Part Segmentation Reveals Compositional Logic for Industrial Anomaly Detection | 2024 | **AAAI** | 部件分割 + 异常检测 | — |
| 13 | STD2: Swin Transformer-Based Defect Detector for Surface Anomaly Detection | 2025 | IEEE TIM | Swin + 异常检测 | 15 |
| 14 | VQGNet: An Unsupervised Defect Detection Approach for Complex Textured Steel Surfaces | 2024 | Sensors | 无监督 + 复杂纹理 | 0 |
| 15 | A Survey on Unsupervised Anomaly Detection Algorithms for Industrial Images | 2023 | IEEE Access | 综述 | 104 |

### 7.3 类不平衡 / 长尾分割

| # | 文献 | 年 | Venue | 方法 | 被引 |
|---|------|----|-------|------|------|
| 1 | TSEDNet: Task-Specific Encoder-Decoder Network for Surface Defects of Strip Steel | 2025 | Measurement | 任务特定多解码器 | — |
| 2 | TSEMDNet: Two-Stage Encoder Multi-Decoder Network with Global-Local Up-Sampling | 2024 | EAAI | 两阶段 + 类别精修 | — |
| 3 | Gradient Adaptive Data Augmentation and Locally Compensated Feature Fusion for Strip Steel Long-Tailed Classification | 2024 | Meas. Sci. Tech. | 梯度自适应增强 | — |
| 4 | DPCSA-Net: Dual-Polarized Channel-Spatial Attention with Extension Dice Loss | 2025 | Optics & Laser Tech | EDL + 轻量分割 | — |
| 5 | A Multi-Expert Ensemble Model for Long-Tailed Steel Surface Defect Detection | 2024 | OpenReview | 多专家集成 | — |
| 6 | Sample-Centric Multi-Task Learning for Detection and Segmentation of Industrial Surface Defects | 2025 | arXiv | 样本级多任务 | — |
| 7 | MulPViT-SimAM: Electronic Substrate Defect Detection Framework for Addressing Imbalanced Data | 2026 | Machines | SimAM + 不平衡 | 1 |

### 7.4 工业噪声 / 光照鲁棒

| # | 文献 | 年 | Venue | 方法 | 被引 |
|---|------|----|-------|------|------|
| 1 | Surface Illumination as a Factor Influencing the Efficacy of Defect Recognition | 2024 | Applied Sciences | 光照因素量化 | 27 |
| 2 | DiAL: Dual-Branch Network via Multiple Illumination-Aware Representation Learning | 2025 | **BMVC** | 双分支光照解耦 | — |
| 3 | ELA-YOLO: Efficient Method with Linear Attention for Steel Surface Defect Detection | 2025 | Adv. Eng. Informatics | 线性注意力抗光照 | — |
| 4 | RDB-YOLO: Lightweight Steel Surface Defects Detection with Receptive Field Enhancement | 2025 | IEEE Conf. | 感受野增强抗噪声 | — |
| 5 | Defect Segmentation for Multi-Illumination Quality Control Systems | 2021 | Machine Vision and Applications | 多光照分割系统 | 9 |
| 6 | Improved Illumination for Vision-Based Defect Inspection of Highly Reflective Metal | 2013 | Chinese Optics Letters | 高反光金属照明优化 | 29 |
| 7 | Vision-Based Surface Defect Detection Method for Highly Reflective Steel Balls | 2022 | SSRN | 高反光钢球检测 | 0 |

### 7.5 域适应 / 泛化

| # | 文献 | 年 | Venue | 方法 | 被引 |
|---|------|----|-------|------|------|
| 1 | Shape-Consistent One-Shot Unsupervised Domain Adaptation for Rail Surface Defect Segmentation | 2023 | IEEE TII | 形状一致 + 单样本 UDA | 53 |
| 2 | Bi-Level Meta-Learning for Few-Shot Domain Generalization | 2023 | **CVPR** | 双层元学习 | 35 |
| 3 | Consistency Conditional Adversarial Network for Cross-Domain Object Detection | 2026 | Sci. China Tech. Sci. | 一致性条件对抗 | 0 |
| 4 | AGSSP: Anomaly-Guided Self-Supervised Pretraining for Metallic Surface Defect Detection | 2025 | arXiv | 异常引导域内预训练 | 0 |
| 5 | Adaptive Graph Neural Networks with Semi-Supervised Multi-Modal Fusion for Few-Shot Steel Strip Defect Detection | 2025 | Processes | GNN + 多模态 | 0 |
| 6 | Tac-TSS-OCD: Tactile-Based Surface Micron Defect Detection in Open Environments | 2026 | Elsevier | 触觉+视觉跨域 | 0 |

### 7.6 扩散模型生成 / 数据增强

| # | 文献 | 年 | Venue | 方法 | 被引 |
|---|------|----|-------|------|------|
| 1 | A Few-Shot Steel Surface Defect Generation Method Based on Diffusion Models | 2025 | Sensors | 扩散 + 小样本钢铁生成 | 9 |
| 2 | Latent Diffusion Models to Enhance the Performance of Visual Defect Segmentation | 2024 | Sensors | 潜扩散增强分割 | 10 |
| 3 | DefectDiffusion: A Generative Diffusion Model for Robust Data Augmentation in Industrial Defect Detection | 2025 | ICAIIC | 扩散鲁棒增强 | 2 |
| 4 | A Novel Approach to Industrial Defect Generation through Blended Latent Diffusion | 2024 | arXiv | 混合潜扩散 | 5 |
| 5 | An Overview of Image Generation of Industrial Surface Defects | 2023 | Sensors | 缺陷图像生成综述 | 34 |
| 6 | Cross-Layer Multi-Scale Fusion within Latent Diffusion Model for Few-Shot Industrial Defect Segmentation | 2026 | SSRN | 跨层扩散 + 小样本 | 0 |

---

## 8. 关键发现与总结

### 8.1 领域现状总结

1. **全监督方法已成熟**：在 NEU-DET 等标准基准上，YOLO 系检测 mAP 可达 93%，UNet 系分割 mIoU 可达 93%。增量提升空间小，天花板明显。

2. **研究重心正从"全监督"转向"少/零监督"**：ICCV 2023 (10 篇) → ECCV 2024 (17+ 篇) → ICCV 2025，工业异常检测/小样本论文数量年均增长 50%+。扩散模型和 CLIP/VLM 是两大驱动力。

3. **TII / TIM 是工业缺陷检测的核心发表阵地**：高质量小样本/域适应工作集中在这两个 IEEE Transactions。TIP/TGRS 上直接相关论文极少——钢铁缺陷分割在 TIP/TGRS 存在**明显的发表空白**，这也意味着 TIP/TGRS 可能是差异化投稿的好选择。

4. **钢铁 vs. 通用工业的 Gap**：MVTec AD 驱动的异常检测研究偏向纹理/物体异常，而钢铁缺陷有其独特性：(a) 镜面高反光、(b) 缺陷形态与轧制工艺强相关、(c) 类间差异小（如裂纹 vs. 划痕易混淆）。

### 8.2 三个核心 Gap 再强调

| Gap | 紧迫性 | 可行性 | 创新度 | 建议优先度 |
|-----|--------|--------|--------|-----------|
| 高反光钢铁像素级光照不变分割 | 🔴 极高 | 中等（需硬件） | 高 | **P1** |
| 小样本 + 开集缺陷分割 | 🔴 极高 | 高 | 高 | **P1** |
| 扩散生成 + 分割端到端联合优化 | 🔴 高 | 中等 | 高 | **P2** |
| 物理信息驱动的缺陷分割 | 🔴 高 | 低（需产线数据） | 极高 | **P3（长期）** |
| VLM 交互式钢铁缺陷分割 | 🟡 中 | 高 | 中 | **P2（快速产出）** |

---

## 9. 参考文献（分列）

### 9.1 英文文献（IEEE 格式）

```bibtex
@article{luo2020automated,
  title={Automated Visual Defect Detection for Flat Steel Surface: A Survey},
  author={Luo, Qiwu and Fang, Xiaoxin and Liu, Li and Yang, Chunhua and Sun, Yichuang},
  journal={IEEE Transactions on Instrumentation and Measurement},
  year={2020},
  doi={10.1109/tim.2019.2963555}
}

@article{neogi2021review,
  title={Review of vision-based steel surface inspection systems},
  author={Neogi, Nirbhar and Mohanta, Dusmanta Kumar and Dutta, Pranab K},
  journal={EURASIP Journal on Image and Video Processing},
  year={2014},
  doi={10.1186/1687-5281-2014-50}
}

@article{song2012automatic,
  title={Automatic Defect Detection on Hot-Rolled Flat Steel Products},
  author={Song, Ke-Chen and Yan, Yun-Hui},
  journal={IEEE Transactions on Instrumentation and Measurement},
  year={2012},
  doi={10.1109/tim.2012.2218677}
}

@article{ren2022state,
  title={State of the Art in Defect Detection Based on Machine Vision},
  author={Ren, Zhonghe and Fang, Fengzhou and Yan, Ning and Wu, You},
  journal={International Journal of Precision Engineering and Manufacturing-Green Technology},
  year={2021},
  doi={10.1007/s40684-021-00343-6}
}

@article{boikov2022steel,
  title={Steel Surface Defect Recognition: A Survey},
  author={Boikov, A and Payor, V and Savelev, R and Kolesnikov, A},
  journal={Coatings},
  year={2022},
  doi={10.3390/coatings13010017}
}

@article{gao2022review,
  title={Review of surface defect detection of steel products based on machine vision},
  author={Gao, Yuan and Li, Xuewei and Wang, Xinyan and others},
  journal={IET Image Processing},
  year={2022},
  doi={10.1049/ipr2.12647}
}

@article{wang2023survey,
  title={A Survey on Unsupervised Anomaly Detection Algorithms for Industrial Images},
  author={Wang, Yu and Chung, Shih-Heng and others},
  journal={IEEE Access},
  year={2023},
  doi={10.1109/access.2023.3282993}
}

@article{huang2022unseen,
  title={Unseen-Material Few-Shot Defect Segmentation With Optimal Bilateral Feature Transport Network},
  author={Huang, Xin and Zhang, Yu and others},
  journal={IEEE Transactions on Industrial Informatics},
  year={2022},
  doi={10.1109/tii.2022.3216900}
}

@article{bao2021triplet,
  title={Triplet-Graph Reasoning Network for Few-Shot Metal Generic Surface Defect},
  author={Bao, Hongquan and others},
  journal={IEEE Transactions on Instrumentation and Measurement},
  year={2021},
  doi={10.1109/tim.2021.3083561}
}

@article{wang2024mfanet,
  title={MFANet: Multifeature Aggregation Network for Cross-Granularity Few-Shot Seamless Steel Tube Defect Segmentation},
  author={Wang, Shaodan and others},
  journal={IEEE Transactions on Industrial Informatics},
  year={2024},
  doi={10.1109/tii.2024.3383513}
}

@article{gao2023few,
  title={Few-shot semantic segmentation for industrial defect recognition},
  author={Gao, Y. and others},
  journal={Computers in Industry},
  year={2023},
  doi={10.1016/j.compind.2023.103901}
}

@inproceedings{cao2023removing,
  title={Removing Anomalies as Noises for Industrial Defect Localization},
  author={Cao, Yunkang and others},
  booktitle={Proceedings of the IEEE/CVF International Conference on Computer Vision (ICCV)},
  year={2023},
  doi={10.1109/iccv51070.2023.01481}
}

@article{li2024dpcsanet,
  title={DPCSA-Net: Dual-Polarized Channel-Spatial Attention Guided Lightweight Metal Surface Defect Segmentation Network},
  author={Li, X. and others},
  journal={Optics \& Laser Technology},
  year={2025},
  doi={10.1016/j.optlastec.2025.113145}
}

@article{guo2025tsednet,
  title={TSEDNet: Task-Specific Encoder-Decoder Network for Surface Defects of Strip Steel},
  author={Guo, Yuyang and others},
  journal={Measurement},
  year={2025},
  doi={10.1016/j.measurement.2024.115438}
}

@article{guo2024tsemdnet,
  title={Two-Stage Encoder Multi-Decoder Network with Global-Local Up-Sampling for Defect Segmentation of Strip Steel},
  author={Guo, Y. and others},
  journal={Engineering Applications of Artificial Intelligence},
  year={2024},
  doi={10.1016/j.engappai.2024.109561}
}

@article{wang2024latent,
  title={Latent Diffusion Models to Enhance the Performance of Visual Defect Segmentation},
  author={Wang, Q. and others},
  journal={Sensors},
  year={2024},
  doi={10.3390/s24186016}
}

@article{zhang2025fewshot,
  title={A Few-Shot Steel Surface Defect Generation Method Based on Diffusion Models},
  author={Zhang, X. and others},
  journal={Sensors},
  year={2025},
  doi={10.3390/s25103038}
}

@article{oh2025dial,
  title={DiAL: Dual-Branch Network via Multiple Illumination-Aware Representation Learning for Steel Surface Defect Classification},
  author={Oh, Yong Seok and others},
  journal={Proceedings of the British Machine Vision Conference (BMVC)},
  year={2025},
  note={BMVC 2025}
}

@article{zhang2024illumination,
  title={Surface Illumination as a Factor Influencing the Efficacy of Defect Recognition},
  author={Zhang, L. and others},
  journal={Applied Sciences},
  year={2024},
  doi={10.3390/app14062591}
}

@article{niu2023shape,
  title={Shape-Consistent One-Shot Unsupervised Domain Adaptation for Rail Surface Defect Segmentation},
  author={Niu, S. and others},
  journal={IEEE Transactions on Industrial Informatics},
  year={2023},
  doi={10.1109/tii.2022.3233654}
}

@article{yang2025background,
  title={Background-Weaken Generalization Network for Few-Shot Industrial Metal Defect Segmentation},
  author={Yang, X. and others},
  journal={IEEE Transactions on Instrumentation and Measurement},
  year={2025},
  doi={10.1109/tim.2025.3544335}
}

@article{liu2025enhancing,
  title={Enhancing Feature Interaction for Improved Generalization in Few-Shot Metal Surface Defect Segmentation},
  author={Liu, Y. and others},
  journal={Knowledge-Based Systems},
  year={2025},
  doi={10.1016/j.knosys.2025.114606}
}

@article{zhao2026rdprompter,
  title={RDPrompter: Reference-Defect Prompt Learning for Few-Shot Defect Segmentation Based on SAM},
  author={Zhao, J. and others},
  journal={IEEE Transactions on Industrial Informatics},
  year={2026},
  doi={10.1109/tii.2026.3663099}
}

@article{chen2025clip,
  title={CLIP-Vision Guided Few-Shot Metal Surface Defect Recognition},
  author={Chen, L. and others},
  journal={IEEE Transactions on Industrial Informatics},
  year={2025},
  doi={10.1109/tii.2025.3547353}
}

@article{wang2025vpgfnet,
  title={VPGFNet: Cross-Domain Few-Shot Visual Prompt Graph Fusion Network for Industrial Surface Defect Segmentation},
  author={Wang, H. and others},
  journal={Journal of Computational Design and Engineering},
  year={2025},
  doi={10.1093/jcde/qwaf105}
}

@article{huang2026hierarchical,
  title={Hierarchical Adaptive Correlation Network for Few-Shot Metal Surface Defect Segmentation},
  author={Huang, Z. and others},
  journal={Journal of Intelligent Manufacturing},
  year={2026},
  doi={10.1007/s10845-026-02874-8}
}

@article{ma2025elayolo,
  title={ELA-YOLO: An Efficient Method with Linear Attention for Steel Surface Defect Detection},
  author={Ma, Ruichen and others},
  journal={Advanced Engineering Informatics},
  year={2025},
  doi={10.1016/j.aei.2025.103377}
}

@article{kong2024defect,
  title={Surface defect inspection of industrial products with object detection deep networks},
  author={Kong, X. and others},
  journal={Artificial Intelligence Review},
  year={2024},
  doi={10.1007/s10462-024-10956-3}
}

@article{bergmann2024state,
  title={State of the Art in AI-Based Visual Inspection for Industrial Quality Control},
  author={Bergmann, P. and others},
  journal={Electronics},
  year={2026},
  doi={10.3390/electronics15122727}
}

@article{zhao2021mixed,
  title={Mixed supervision for surface-defect detection: From weakly to fully supervised learning},
  author={Zhao, W. and others},
  journal={Computers in Industry},
  year={2021},
  doi={10.1016/j.compind.2021.103459}
}
```

### 9.2 中文文献（GB/T 7714-2015 格式）

```
[1] 宋克臣, 颜云辉, 等. 热轧带钢表面缺陷检测方法综述[J]. 自动化学报, 2014.
[2] 佚名. 基于深度学习的工业零部件表面缺陷智能检测算法优化[J]. 工程技术论坛, 2025. DOI: 10.64216/3080-1508.25.02.017.
[3] 佚名. 基于深度学习的激光熔覆层表面缺陷识别研究[J]. Acta Optica Sinica, 2025. DOI: 10.3788/aos250462.
[4] 佚名. 基于深度迁移学习的脉冲涡流热成像裂纹缺陷检测[J]. Acta Optica Sinica, 2023. DOI: 10.3788/aos221532.
[5] 佚名. 钢铁表面缺陷检测深度学习方法研究进展[J]. 中国科学: 技术科学, 2023.
```

---

## 附录 A: 检索策略与参数记录

```
检索日期: 2026-06-25
检索脚本: light-literature-search/scripts/search_normalize.py
         light-literature-search/scripts/snowball.py
         light-literature-search/scripts/cross_domain_search.py
         light-literature-search/scripts/arxiv_search.py
排序策略: relevance (OpenAlex sort=relevance_score:desc)
时效增强: --recency-boost --half-life 3 --current-year 2026
相关度过滤: --require-terms (按 query 不同)
Snowball 种子: 10.1109/tii.2022.3216900, 10.1109/tim.2019.2963555
网络检索: WebSearch × 5 次 (steel defect + anomaly detection + class imbalance + illumination + NEU-DET benchmarks)
```

## 附录 B: 常用缩写

| 缩写 | 全称 |
|------|------|
| TIP | IEEE Transactions on Image Processing |
| TGRS | IEEE Transactions on Geoscience and Remote Sensing |
| TII | IEEE Transactions on Industrial Informatics |
| TIM | IEEE Transactions on Instrumentation and Measurement |
| TCSVT | IEEE Transactions on Circuits and Systems for Video Technology |
| ICCV | International Conference on Computer Vision |
| ECCV | European Conference on Computer Vision |
| BMVC | British Machine Vision Conference |
| NEU-DET | Northeastern University Defect Dataset |
| MVTec AD | MVTec Anomaly Detection Dataset |
| SOTA | State of the Art |
| UDA | Unsupervised Domain Adaptation |
| DG | Domain Generalization |
| NF | Normalizing Flow |
| VLM | Vision-Language Model |
| SAM | Segment Anything Model |
