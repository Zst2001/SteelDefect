# 钢铁表面缺陷检测文献综述骨架

> **综述范围**：钢铁 / 金属表面缺陷的**目标检测**（边界框 + 类别），与像素级分割、图级分类分开讨论。  
> **时间范围**：核心为 2019–2026；奠基综述与数据集不限年份。  
> **对照文档**：同目录 `steel_defect_segmentation_review.md`（分割方向）。本篇不把分割 SOTA、异常检测 ICCV/ECCV 条目当成检测结果。  
> **检索覆盖**：OpenAlex + Crossref DOI 直查 + 中文题名检索。被引数为 OpenAlex `cited_by_count`，快照 **2026-10-14**，跨库不可直接比。  
> **指标纪律**：正文不抄未回原表核对的 mAP / FPS。需要数字时回原文表，并写清数据集划分与 IoU 协议。

---

## 0. 检索元信息（PRISMA 留痕）

- **研究方向 / 核心问题（PICO）**
  - **P**：钢铁及相近金属表面图像（热轧带钢、冷轧钢板、金属板材等）
  - **I**：深度学习目标检测（双阶段 / YOLO 单阶段 / 无锚点 / Transformer 检测）、小样本检测、轻量化
  - **C**：传统纹理 + 分类器；图级分类；像素级分割；仅正常样本的异常检测
  - **O**：框级定位与分类（mAP 族）、实时性、小目标与细长缺陷、跨数据集泛化
- **语言**：中英双语（中文题名在 OpenAlex 上命中很少，中文核心成果需知网/万方补检）
- **目标期刊**：IEEE TIM / TII、Measurement、Sensors、IET Image Processing、Artificial Intelligence Review；中文如《红外与激光工程》

| 库 | 检索式（原样） | 说明 | 标题筛后纳入本篇 |
|----|----------------|------|------------------|
| OpenAlex `search=` | `steel surface defect detection YOLO` | 被引排序噪声大，只作发现 | 人工去跑题后取 YOLO 族代表 |
| OpenAlex `search=` | `NEU-DET steel surface defect detection` | 命中 He 2019/2020、GC10、RDD-YOLO 等 | 是 |
| OpenAlex `search=` | `GC10-DET steel surface defect` | 命中 Lv 2020 数据集文 | 是 |
| OpenAlex `filter=display_name.search:` | 约 20 个精确题名（MSFT-YOLO、RDD-YOLO、Few-Shot Steel… 等） | 精确命中 | 是 |
| OpenAlex | `display_name.search:带钢表面缺陷检测` | 中文 1 条 | HDM-YOLO 2026 |
| OpenAlex | `display_name.search:钢铁表面缺陷检测` | 0 | 知网待补 |
| Crossref `GET /works/{doi}` | 32 个候选 DOI | 全部 HTTP 200 才写入 | 见附录 A |
| **排除** | 土木工程裂缝、数字孪生综述、天文/引力波等高被引跑题；分割论文冒充检测；无 DOI 且 arXiv 未核 | — | — |

- **去重锚点**：DOI → 规范化标题+作者+年
- **与分割稿的边界**：Triplet-Graph（TIM 2021）题名是 **Segmentation**，本篇只在「相邻任务」提及，不计入检测方法族。Božič 等混合监督（Computers in Industry, 2021）对象是一般工业表面，不是钢铁专用，标「工业表面相关」。

---

## 1. 引言：问题为什么重要

产线质检里，「检测」常被口语化成所有视觉检查。学术上必须拆开：

| 任务 | 输出 | 标注 | 常用指标 | 本课题组实验台 |
|------|------|------|----------|----------------|
| 分类 | 整图类别 | 图级标签 | Accuracy / F1 | 占位 |
| **检测** | 每个缺陷一个框 + 类别 | 边界框 | mAP（须声明 IoU 阈值与数据集划分） | **占位，不可提交真实任务** |
| 分割 | 每个像素类别 | 掩码 | mIoU / Dice | 第一版承诺（NEU-20 评测 ≠ NEU-DET） |

钢铁表面常见缺陷类别（NEU 系常用六类，名称以 Song 2013 / He 2020 为准）：裂纹（crazing）、夹杂（inclusion）、斑块（patches）、麻点（pitted surface）、氧化皮压入（rolled-in scale）、划痕（scratches）。**检测**要同时给出位置和类别，适合后续抽检、计数、粗定位；需要面积、边界或工艺追溯时仍应上分割。

检测方向的核心难点（与分割同源，但评价对象是框）：

1. **尺度与形态异质**：点状麻点、大面积斑块、细长划痕/裂纹并存；IoU 对细长框很敏感。
2. **低对比与纹理背景**：轧制纹理、氧化、油污造成假阳性。
3. **小样本与长尾**：稀有缺陷框少，全监督 YOLO 在标准集上好看，换产线即掉点。
4. **速度与部署**：产线要实时，论文 GPU FPS 与本站 CPU dummy 测速不是一回事。
5. **协议混乱**：不少工作在 NEU-DET 上报 mAP，但不写清 train/val/test 划分与 IoU=0.5 还是 COCO 风格；**禁止把不同协议的数字横比，更禁止把本站 NEU-20 写成 NEU-DET 官方测试集**。

本篇只梳理**框检测**主线：数据从哪来、方法族怎么走、必读综述与代表工作、还剩什么缺口。分割、异常检测、扩散生成详见分割稿。

---

## 2. 研究脉络

### 2.1 问题怎么提出 → 奠基（~2019 以前）

| 阶段 | 代表工作 | 角色 | 核验 |
|------|---------|------|------|
| 传统视觉检测 | Ghorai 等，Automatic Defect Detection on Hot-Rolled Flat Steel Products，IEEE TIM，Crossref 年份 **2013**，DOI `10.1109/tim.2012.2218677` | 热轧板传统特征 + 检测流程，**不是 NEU 数据集论文** | Crossref 200；OpenAlex 被引 317 |
| 视觉系统综述 | Neogi, Mohanta, Dutta. Review of vision-based steel surface inspection systems. EURASIP JIVP, 2014. DOI `10.1186/1687-5281-2014-50` | 光源、采集、传统流程 | Crossref 200；被引 321 |
| NEU 图像起源 | Song, Yan. A noise robust method based on completed local binary patterns… Applied Surface Science, 2013. DOI `10.1016/j.apsusc.2013.09.002` | **热轧带钢缺陷图 / 纹理分类**，后续 NEU-DET 的图像源头 | Crossref 200；被引 1005 |
| 通用检测范式 | Faster R-CNN（Ren 等，TPAMI 2017，DOI `10.1109/tpami.2016.2577031`）；YOLO v1（Redmon 等，CVPR 2016，DOI `10.1109/cvpr.2016.91`） | 双阶段 vs 单阶段，钢铁检测几乎都从这里迁移 | Crossref 200 |

### 2.2 怎么被逐步解决 → 里程碑（2019–2023）

```
2019–2020  检测设定落地
  ├─ He 等 TIM：多层特征融合，端到端钢缺陷检测（NEU-DET 检测设定）
  ├─ Luo 等 TIM：平板钢表面缺陷视觉检测综述（约 120 篇、连铸/热轧/冷轧）
  └─ Lv 等 Sensors：GC10-DET 金属表面十类检测基准 + 检测网络

2020–2022  专用检测器
  ├─ Cheng & Yu TIM：DEA-RetinaNet（通道注意力 + 自适应空间融合）
  ├─ DCC-CenterNet：无锚点、强调速度
  ├─ Kou 等 Measurement：YOLOv3 带钢表面
  ├─ MSFT-YOLO：YOLOv5 + Transformer，钢表面
  └─ Wang 等 TIM：Few-Shot Steel Surface Defect Detection

2022–2023  YOLO 工程改型密集 + 综述更新
  ├─ Wang 等 Access：YOLOv7 带钢
  ├─ RDD-YOLO：改 YOLO 做钢表面
  ├─ Wen 等 Coatings：缺陷识别综述（含传统→深度，识别≠只检测）
  ├─ Tang 等 IET：钢产品表面缺陷视觉检测综述
  └─ Liu 等 AIR：实时表面缺陷检测深度学习综述（工业面更宽）
```

### 2.3 当前工作（2024–2026，不宣称「唯一 SOTA」）

| 方向 | 代表 | 说明 |
|------|------|------|
| 工业产品 + 目标检测综述 | Ma 等，AIR 2024，DOI `10.1007/s10462-024-10956-3` | 系统综述目标检测用于工业表面；摘要强调尺度变化、精度–速度、检测难度 |
| 特征融合检测 | AMFNet，JIM 2025，DOI `10.1007/s10845-025-02613-5` | 多层特征交互融合；分割稿里另一条 Scientific Reports DOI **本篇未核到同一条目，不用那条** |
| 线性注意力 YOLO | ELA-YOLO，Advanced Engineering Informatics 2025，DOI `10.1016/j.aei.2025.103377` | 制造场景钢表面，强调效率 |
| YOLO11 改型 | FD-YOLO11，IEEE Access 2025，DOI `10.1109/access.2025.3559733` | 特征增强；新作被引低，当「工程改型样本」而非奠基 |
| 中文 YOLO | HDM-YOLO，红外与激光工程 2026，DOI `10.3788/irla20250608` | 带钢表面；OpenAlex 中文题名几乎只命中这一条 |

Transformer 检测桥：通用 DETR（Carion 等，ECCV 2020，DOI `10.1007/978-3-030-58452-8_13`）；钢表面一例为 Tang 等 IET 2022 Swin 检测（DOI `10.1049/ipr2.12715`，被引 35，代表「可以迁」，不是领域默认骨干）。

### 2.4 还剩什么

见第 6 节。一句话：标准集上的 YOLO 改模块已经拥挤；缺口在小目标/细长缺陷协议、跨产线泛化、少样本框标注、以及检测与分割的任务边界被写混。

---

## 3. 方法族分类

### 3.1 按检测范式

| 方法族 | 代表（均已核 DOI） | 核心思想 | 优点 | 局限 | 常用数据 |
|--------|-------------------|----------|------|------|----------|
| 双阶段 / 多层融合 | He 等 TIM 2020 | 分类+定位复合任务，融多层特征 | 设定清楚，是 NEU-DET 检测入门文 | 速度通常不如后来 YOLO | NEU 系 |
| 单阶段 RetinaNet 改 | DEA-RetinaNet（Cheng & Yu, TIM，Crossref 2021） | 通道注意力 + 自适应空间融合 | 针对钢缺陷特征融合 | 仍依赖全监督框 | 钢表面 |
| 无锚点 | DCC-CenterNet（Tian & Jia, Measurement，Crossref 2022） | CenterNet 系，强调快速 | 少锚框超参 | 细长目标中心表示不稳 | 钢表面 |
| YOLO 族 | Kou YOLOv3；MSFT-YOLO；YOLOv7 带钢；RDD-YOLO；ELA-YOLO；FD-YOLO11；HDM-YOLO | 单阶段实时 + 注意力/多尺度补丁 | 工程成熟、易部署叙事 | 模块堆叠同质化；YOLOv8/11 **工程版不是顶会论文** | NEU-DET、GC10-DET |
| Transformer 骨干 | Tang 等 Swin 检测；通用 DETR | 层次化 / 集合预测 | 长程上下文，对细长缺陷在机理上更有利 | 数据与算力更贵；钢领域被引远低于 YOLO 改型 | NEU 等 |
| 小样本检测 | Wang 等 TIM Few-Shot Steel Surface Defect Detection（Crossref 2022） | 标注框不足时的检测 | 对准产线稀有缺陷 | 协议与基类/新类划分必须写清 | 钢表面 |
| 工业表面弱/混监督 | Božič 等 2021（非钢铁专用） | 弱标签→全监督过渡 | 降标注成本思路 | 数据不是 NEU/GC10 | 一般工业表面 |

### 3.2 演进（只画检测，不把 U-Net / MVTec 画进来）

```
传统特征与分类器（Ghorai / Song 纹理分类）
        ↓
通用检测器迁入（Faster R-CNN / YOLO / RetinaNet / CenterNet）
        ↓
钢表面专用头与融合（He 多层特征、DEA-RetinaNet、MSFT-YOLO…）
        ↓
实时与轻量化改 YOLO（v3→v5/v7→v11 改型，拥挤）
        ↓
少样本 / 跨域 / 细长与小目标（缺口，见第 6 节）
```

---

## 4. 重要性分级

被引 = OpenAlex，2026-10-14。角色按「对钢缺陷**检测**的贡献」而不是纯被引。

### 4.1 奠基

| 文献 | 年（Crossref） | 被引 | 意义 |
|------|----------------|------|------|
| Song & Yan, Appl. Surf. Sci. `10.1016/j.apsusc.2013.09.002` | 2013 | 1005 | NEU 热轧缺陷图源头（**分类/纹理**，不是框检测） |
| Neogi 等, EURASIP JIVP `10.1186/1687-5281-2014-50` | 2014 | 321 | 钢表面视觉检测系统综述 |
| Luo 等, IEEE TIM `10.1109/tim.2019.2963555` | 2020 | 550 | 平板钢表面自动视觉缺陷检测综述，覆盖连铸/热轧/冷轧约 20 年 |
| He 等, IEEE TIM `10.1109/tim.2019.2915404` | 2020 | 1333 | **检测任务设定 + 多层特征融合**；NEU-DET 入门必读 |
| Faster R-CNN / YOLO v1 | 2017 / 2016 | （通用，不在此比被引） | 双阶段 / 单阶段范式 |

Ghorai 等 TIM（DOI `10.1109/tim.2012.2218677`，Crossref 2013，被引 317）是传统热轧检测，**不要写成 NEU 数据集起源**。

### 4.2 里程碑（数据集 + 钢表面专用检测器）

| 文献 | 年 | 被引 | 意义 |
|------|----|------|------|
| Lv 等, Sensors `10.3390/s20061562` | 2020 | 593 | **GC10-DET** 十类金属表面检测基准 |
| Cheng & Yu, TIM `10.1109/tim.2020.3040485` | 2021 | 349 | DEA-RetinaNet |
| Kou 等, Measurement `10.1016/j.measurement.2021.109454` | 2021 | 294 | YOLOv3 带钢 |
| Tian & Jia, Measurement `10.1016/j.measurement.2021.110211` | 2022 | 222 | DCC-CenterNet |
| Guo 等, Sensors `10.3390/s22093467` | 2022 | 311 | MSFT-YOLO（YOLOv5+Transformer） |
| Wang 等, TIM `10.1109/tim.2021.3128208` | 2022 | 82 | 小样本钢表面缺陷**检测** |
| Zhao 等, Measurement `10.1016/j.measurement.2023.112776` | 2023 | 385 | RDD-YOLO |
| Wang 等, IEEE Access `10.1109/access.2022.3230894` | 2022 | 222 | YOLOv7 带钢 |

### 4.3 新锐（≤3 年，当样本不当时下定论）

| 文献 | 年 | 被引 | 说明 |
|------|----|------|------|
| ELA-YOLO, AEI `10.1016/j.aei.2025.103377` | 2025 | 50 | 线性注意力 + 制造场景 |
| AMFNet, JIM `10.1007/s10845-025-02613-5` | 2025 | 14 | 多层特征交互融合 |
| FD-YOLO11, Access `10.1109/access.2025.3559733` | 2025 | 26 | YOLO11 特征增强，venue 一般 |
| HDM-YOLO, 红外与激光工程 `10.3788/irla20250608` | 2026 | 0 | 中文带钢 YOLO，新文 |

### 4.4 综述（Survey，不作原创证据）

| 文献 | 年 | 被引 | 覆盖 |
|------|----|------|------|
| Luo 等 TIM 2020 | 2020 | 550 | 平板钢，传统→早期深度 |
| Wen, Shan, He, Song, Coatings `10.3390/coatings13010017` | 2022 | 193 | 钢表面缺陷**识别**（分类/检测都可能出现） |
| Tang 等 IET IP `10.1049/ipr2.12647` | 2022 | 271 | 钢产品表面视觉检测，约 170 篇 |
| Chen 等 Appl. Sci. `10.3390/app11167657` | 2021 | 443 | 工业产品表面缺陷方法（面比钢铁宽） |
| Ren 等 IJPEM-GT `10.1007/s40684-021-00343-6` | 2021 | 797 | 机器视觉缺陷检测全景，不单是钢 |
| Cumbajin 等 J. Imaging `10.3390/jimaging9100193` | 2023 | 95 | CNN 表面缺陷系统综述 |
| Liu, Zhang, Dong, AIR `10.1007/s10462-023-10475-7` | 2023 | 125 | 实时表面缺陷深度学习 |
| Ma 等 AIR `10.1007/s10462-024-10956-3` | 2024 | 157 | **目标检测网络**做工业表面缺陷 |
| Hussain, Machines `10.3390/machines11070677` | 2023 | 1198 | YOLO 族与工业质检（不是钢专用） |
| Li, Wei, Hassaballah, Complex Intell. Syst. `10.1007/s40747-023-01180-7` | 2023 | 120 | 钢表面缺陷检测深度学习模型（方法文，常被当综述引用，阅读时看清体裁） |

### 4.5 通用检测必读（入门，非钢数据）

与 `docs/kb/课题组学习路线安排.md` 阶段 4A 对齐：YOLO v1、Faster R-CNN、YOLOv3（arXiv:`1804.02767`，预印本）、DETR。不要把 Ultralytics YOLOv8 写成 CVPR/ECCV 论文。

---

## 5. 可复用资源

### 5.1 数据集（检测框）

精确张数、许可、下载页以发布方为准；下表只写本篇已核到论文或组内已锁口径。

| 名称 | 任务 | 已核文献 | 入门时要知道的 |
|------|------|----------|----------------|
| NEU 图像 | 原为分类 | Song & Yan 2013 | 热轧六类缺陷图来源 |
| **NEU-DET** | **框检测** | He 等 2020 | 在 NEU 图上做检测；常用口径为 6 类、约 1800 张、200×200。**划分与协议以原文/发布页为准** |
| **GC10-DET** | **框检测** | Lv 等 2020 Sensors | 十类金属表面、尺度与类别挑战大于早期小集 |
| 本站 **NEU-20** | 分割评测用 20 张 | 需求书 / 审定种子 | **不是** NEU-DET 官方 test，**不是**完整检测评测 |

Severstal Kaggle、DAGM 等可用于相关实验，但 Severstal 主标注是像素 RLE（分割竞赛），不要默认当成检测框基准。MVTec AD / VisA 是异常检测，不是钢缺陷框检测。

### 5.2 开源与工程

| 资源 | 用法 | 注意 |
|------|------|------|
| Ultralytics YOLO | 常见复现基线 | AGPL；版本号是工程发布，不是顶会 DOI |
| 各论文是否放码 | 以原文脚注为准 | 未核到的 GitHub 不写进本篇 |
| 本站模型中心 | 可运行分割 baseline | catalog 文献卡片**没有**检测推理管道 |

### 5.3 读数时的协议清单（比刷榜重要）

1. 数据集名称：NEU-DET 还是 GC10-DET，有没有自己增广。  
2. 划分是否与前作一致。  
3. mAP@0.5 还是 COCO mAP。  
4. 输入分辨率、NMS 阈值。  
5. 速度：GPU 型号、是否含后处理；**不是**本站 CPU `FPS=1000/ms` 协议。

---

## 6. 空白与机会

### 6.1 Gap 矩阵（检测专用）

| 痛点 | 现有常见做法 | 不足 | 等级 |
|------|--------------|------|------|
| 细长裂纹/划痕框不准 | 多尺度 YOLO、旋转框（本篇未核到足够钢表面旋转框代表作，不编） | IoU 对细框惩罚大；水平框浪费背景 | 高 |
| 小缺陷 | FPN / 额外小目标头 | 200×200 的 NEU 图上「小」与产线高分辨率上「小」不是同一回事 | 高 |
| 标准集过拟合 | 在 NEU-DET 上改 YOLO 模块 | 增量论文拥挤，跨 GC10 / 真实产线掉点少报 | 极高 |
| 少样本框 | Wang 等 TIM 一篇主线 | 远少于分割侧的 few-shot 文献量 | 高 |
| 跨产线 / 光照 | 增强、注意力 | 检测级光照解耦证据不足（分割稿中的分类级光照工作不能直接当检测结论） | 高 |
| 任务写混 | 用分割 mIoU 或分类 Accuracy 讲「检测 SOTA」 | 审稿必打；本站也禁止把演示精度当检测 mAP | 纪律 |
| 实时落地 | YOLO 轻量化 | 论文 FPS ≠ 产线相机协议 ≠ 本站测速 | 中 |

### 6.2 可执行的研究问题（给新生，不是替你定 idea）

1. **同一骨干、两种协议**：NEU-DET 与 GC10-DET 上固定划分，只改头或融合，报告 mAP@0.5 与小目标 AP，避免只报一个总 mAP。  
2. **细长缺陷专项**：把划痕/裂纹单独列出 AP，讨论水平框是否够用。  
3. **少样本检测**：在 Wang 等 2022 设定上复现，再考虑迁 DETR/YOLO 的 few-shot 变体；不要把分割 few-shot 数字写成检测。  
4. **检测→分割衔接**：框只做粗定位，精细边界交给分割（与组内实验台能力匹配）。

---

## 7. 核心论文速查

### 7.1 数据集与任务设定

| 文献 | 年 | Venue | DOI |
|------|----|-------|-----|
| Song & Yan | 2013 | Appl. Surf. Sci. | `10.1016/j.apsusc.2013.09.002` |
| He, Song, Meng, Yan | 2020 | IEEE TIM | `10.1109/tim.2019.2915404` |
| Lv, Duan, Jiang, Fu 等 | 2020 | Sensors | `10.3390/s20061562` |

### 7.2 钢 / 金属表面检测器

| 文献 | 年 | 方法 | DOI |
|------|----|------|-----|
| Cheng & Yu | 2021 | DEA-RetinaNet | `10.1109/tim.2020.3040485` |
| Kou 等 | 2021 | YOLOv3 带钢 | `10.1016/j.measurement.2021.109454` |
| Tian & Jia | 2022 | DCC-CenterNet | `10.1016/j.measurement.2021.110211` |
| Guo 等 | 2022 | MSFT-YOLO | `10.3390/s22093467` |
| Wang 等 | 2022 | YOLOv7 带钢 | `10.1109/access.2022.3230894` |
| Tang 等 | 2022 | Swin 检测 | `10.1049/ipr2.12715` |
| Zhao 等 | 2023 | RDD-YOLO | `10.1016/j.measurement.2023.112776` |
| Li, Wei, Hassaballah | 2023 | 钢表面深度检测模型 | `10.1007/s40747-023-01180-7` |
| Wang, Li, Wang | 2022 | 小样本钢表面检测 | `10.1109/tim.2021.3128208` |
| Wei 等 | 2025 | AMFNet | `10.1007/s10845-025-02613-5` |
| Ma 等 | 2025 | ELA-YOLO | `10.1016/j.aei.2025.103377` |
| Dang & Wang | 2025 | FD-YOLO11 | `10.1109/access.2025.3559733` |
| 邸志刚 等 | 2026 | HDM-YOLO | `10.3788/irla20250608` |

### 7.3 综述

见 §4.4，此处不重复。

### 7.4 相邻但不计入检测主表

| 文献 | 为何相邻 |
|------|----------|
| Bao 等 Triplet-Graph，TIM 2021，`10.1109/tim.2021.3083561` | **分割** + 小样本金属表面，被引 318 |
| Božič 等混合监督，2021，`10.1016/j.compind.2021.103459` | 工业表面弱监督，被引 371，非钢专用 |
| 分割稿中的 U-Net / MVTec / ICCV 异常检测 | 任务不是框检测 |

---

## 8. 关键发现与本站口径

1. **检测主线已经从「有没有深度模型」变成「YOLO 改模块竞赛」。** 入门应先读 He 2020 + Luo 2020 + Lv 2020，再挑 1 个 YOLO 改型复现，而不是从 YOLOv8 仓库倒推领域史。  
2. **NEU-DET 与 GC10-DET 是检测基准双门。** 只刷其中一个不够；两者图像尺度、类别数不同。  
3. **小样本检测文献明显少于小样本分割。** 这是检测方向可写空间，也说明可引用的钢专用前作少，不要把分割 few-shot 表贴过来。  
4. **中文题名在 OpenAlex 几乎搜不到。** 本篇仅核到 HDM-YOLO；知网/万方需人工补。  
5. **本站**：实验台第一版只承诺语义分割；检测菜单是占位。学术上可以做钢铁缺陷检测，但不能把首页 catalog、NEU-20、公开演示说成已落地的检测评测。本机 FPS 文案锁死为 CPU、batch=1、dummy 输入，`FPS=1000/ms/图`。

---

## 9. 新生怎么读（对接学习路线）

与课题组知识库中的《课题组学习路线安排》阶段 4A→5A 一致（仓库内路径：`docs/kb/课题组学习路线安排.md`）：

1. 不会框 / IoU / mAP → 先读 YOLO v1 与 Faster R-CNN，不要上钢数据。  
2. 已完成 4A → Song 2013（图从哪来）→ He 2020（检测设定）→ Luo 2020 或 Tang 2022 综述。  
3. 要复现 → 在 NEU-DET 或 GC10-DET 上跑通一个官方 YOLO，再读 MSFT-YOLO 或 RDD-YOLO 看「改了什么」。  
4. 问 Transformer 检测 → DETR 通用篇，再看 Tang 2022 Swin 钢表面一例。  
5. 问本站能不能跑 YOLO → 不能；训练在 AutoDL，本站检测管道未就绪。

---

## 10. 参考文献（已核 DOI）

英文条目按 IEEE 习惯列出 DOI；中文按 GB/T 7714 列出。年份以 Crossref `issued` 为准。

**数据集与设定**

1. K. Song and Y. Yan, “A noise robust method based on completed local binary patterns for hot-rolled steel strip surface defects,” *Appl. Surf. Sci.*, 2013, doi: 10.1016/j.apsusc.2013.09.002.  
2. Y. He, K. Song, Q. Meng, and Y. Yan, “An end-to-end steel surface defect detection approach via fusing multiple hierarchical features,” *IEEE Trans. Instrum. Meas.*, 2020, doi: 10.1109/tim.2019.2915404.  
3. X. Lv, F. Duan, J. Jiang, X. Fu, et al., “Deep metallic surface defect detection: The new benchmark and detection network,” *Sensors*, 2020, doi: 10.3390/s20061562.

**综述**

4. N. Neogi, D. K. Mohanta, and P. K. Dutta, “Review of vision-based steel surface inspection systems,” *EURASIP J. Image Video Process.*, 2014, doi: 10.1186/1687-5281-2014-50.  
5. Q. Luo, X. Fang, L. Liu, C. Yang, et al., “Automated visual defect detection for flat steel surface: A survey,” *IEEE Trans. Instrum. Meas.*, 2020, doi: 10.1109/tim.2019.2963555.  
6. X. Wen, J. Shan, Y. He, and K. Song, “Steel surface defect recognition: A survey,” *Coatings*, 2022, doi: 10.3390/coatings13010017.  
7. B. Tang, L. Chen, W. Sun, Z. Lin, et al., “Review of surface defect detection of steel products based on machine vision,” *IET Image Process.*, 2022, doi: 10.1049/ipr2.12647.  
8. Y. Chen, Y. Ding, F. Zhao, and E. Zhang, “Surface defect detection methods for industrial products: A review,” *Appl. Sci.*, 2021, doi: 10.3390/app11167657.  
9. Z. Ren, F. Fang, N. Yan, and Y. Wu, “State of the art in defect detection based on machine vision,” *Int. J. Precis. Eng. Manuf.-Green Tech.*, 2021, doi: 10.1007/s40684-021-00343-6.  
10. E. Cumbajin, N. Rodrigues, P. Costa, et al., “A systematic review on deep learning with CNNs applied to surface defect detection,” *J. Imaging*, 2023, doi: 10.3390/jimaging9100193.  
11. Y. Liu, C. Zhang, and X. Dong, “A survey of real-time surface defect inspection methods based on deep learning,” *Artif. Intell. Rev.*, 2023, doi: 10.1007/s10462-023-10475-7.  
12. Y. Ma, J. Yin, F. Huang, Q. Li, et al., “Surface defect inspection of industrial products with object detection deep networks: a systematic review,” *Artif. Intell. Rev.*, 2024, doi: 10.1007/s10462-024-10956-3.  
13. M. Hussain, “YOLO-v1 to YOLO-v8, the rise of YOLO and its complementary nature toward digital manufacturing and industrial defect detection,” *Machines*, 2023, doi: 10.3390/machines11070677.

**检测器**

14. X. Cheng and J. Yu, “RetinaNet with difference channel attention and adaptively spatial feature fusion for steel surface defect detection,” *IEEE Trans. Instrum. Meas.*, 2021, doi: 10.1109/tim.2020.3040485.  
15. X. Kou, S. Liu, K. Cheng, Y. Qian, et al., “Development of a YOLO-V3-based model for detecting defects on steel strip surface,” *Measurement*, 2021, doi: 10.1016/j.measurement.2021.109454.  
16. R. Tian and M. Jia, “DCC-CenterNet: A rapid detection method for steel surface defects,” *Measurement*, 2022, doi: 10.1016/j.measurement.2021.110211.  
17. Z. Guo, C. Wang, G. Yang, Z. Huang, et al., “MSFT-YOLO: Improved YOLOv5 based on Transformer for detecting defects of steel surface,” *Sensors*, 2022, doi: 10.3390/s22093467.  
18. Y. Wang, H. Wang, and Z. Xin, “Efficient detection model of steel strip surface defects based on YOLO-V7,” *IEEE Access*, 2022, doi: 10.1109/access.2022.3230894.  
19. B. Tang, Z. Song, W. Sun, X. Wang, et al., “An end-to-end steel surface defect detection approach via Swin transformer,” *IET Image Process.*, 2022, doi: 10.1049/ipr2.12715.  
20. C. Zhao, X. Shu, X. Yan, and X. Zuo, “RDD-YOLO: A modified YOLO for detection of steel surface defects,” *Measurement*, 2023, doi: 10.1016/j.measurement.2023.112776.  
21. Z. Li, X. Wei, and M. Hassaballah, “A deep learning model for steel surface defect detection,” *Complex Intell. Syst.*, 2023, doi: 10.1007/s40747-023-01180-7.  
22. H. Wang, Z. Li, and H. Wang, “Few-shot steel surface defect detection,” *IEEE Trans. Instrum. Meas.*, 2022, doi: 10.1109/tim.2021.3128208.  
23. C. Wei, Y. Bao, C. Zheng, and Z. Ji, “AMFNet: aggregated multi-level feature interaction fusion network for defect detection on steel surfaces,” *J. Intell. Manuf.*, 2025, doi: 10.1007/s10845-025-02613-5.  
24. R. Ma, J. Chen, Y. Feng, Z. Zhou, et al., “ELA-YOLO: An efficient method with linear attention for steel surface defect detection during manufacturing,” *Adv. Eng. Inform.*, 2025, doi: 10.1016/j.aei.2025.103377.  
25. Z. Dang and X. Wang, “FD-YOLO11: A feature-enhanced deep learning model for steel surface defect detection,” *IEEE Access*, 2025, doi: 10.1109/access.2025.3559733.

**中文**

26. 邸志刚, 陈帅, 鲁镇瑜, 等. 面向带钢表面缺陷检测的HDM-YOLO方法[J]. 红外与激光工程, 2026. DOI: 10.3788/irla20250608.

**通用范式**

27. S. Ren, K. He, R. Girshick, and J. Sun, “Faster R-CNN: Towards real-time object detection with region proposal networks,” *IEEE Trans. Pattern Anal. Mach. Intell.*, 2017, doi: 10.1109/tpami.2016.2577031.  
28. J. Redmon, S. Divvala, R. Girshick, and A. Farhadi, “You only look once: Unified, real-time object detection,” in *CVPR*, 2016, doi: 10.1109/cvpr.2016.91.  
29. N. Carion, F. Massa, G. Synnaeve, N. Usunier, et al., “End-to-end object detection with Transformers,” in *ECCV*, 2020, doi: 10.1007/978-3-030-58452-8_13.

**传统检测（非 NEU 起源）**

30. S. Ghorai, A. Mukherjee, M. Gangadaran, and P. K. Dutta, “Automatic defect detection on hot-rolled flat steel products,” *IEEE Trans. Instrum. Meas.*, 2013, doi: 10.1109/tim.2012.2218677.

---

## 附录 A. 元数据核验（2026-10-14）

Crossref `GET /works/{doi}` 对本篇引用 DOI 均为 200。OpenAlex 被引仅作排序参考。

**本篇明确不用或降级的条目**

| 条目 | 处理 |
|------|------|
| 分割稿把 Ghorai 2012 写成「奠定 NEU 数据集」 | 纠正：NEU 图用 Song 2013；Ghorai 是另一路传统检测 |
| 分割稿 AMFNet 的 `10.1038/s41598-025-91930-z` | 本轮按题名命中的是 JIM `10.1007/s10845-025-02613-5`；未核 Scientific Reports 那条，不混用 |
| Triplet-Graph | 题名为 Segmentation，不进检测主表 |
| Ultralytics YOLOv8/v11 文档 | 不当顶会论文 |
| NEU-Seg / BSData 独立 DOI | 检测篇不需要；分割稿已标未收录 |
| 各论文自报 mAP / 93% 一类数字 | 未回原表，不写入 |

**已知局限**

- 知网/万方无开放 API，中文只补到 OpenAlex 命中的 HDM-YOLO。  
- 宽检索 `search=` 被引排序会顶出土木裂缝、数字孪生等跑题文，本篇已剔除。  
- 没有穷尽 2025–2026 全部 YOLO 改型；新作只收 Crossref 已通过且题名明确为钢/带钢表面**检测**者。
