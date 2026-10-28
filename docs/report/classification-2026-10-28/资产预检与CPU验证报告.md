# NEU-CLS 资产预检与 CPU 推理验收

日期：2026-10-28。该报告仅是本轮分类集成的资产与推理部分，真实业务链路由主报告记录。

## 资产来源与安装

用户提供 `E:/huancun/edgehuancun/neu_cls_v1_formal_exports.zip`。压缩包保留原样；使用白名单离线安装器解包到 `assets/classification/neu_cls_v1/<slug>/`。目标存在则拒绝覆盖；路径穿越、符号链接、未知成员、重复成员和超大成员均拒绝。安装器没有联网和 `.env` 访问能力。

源归档 SHA-256：`6601bd67ab7a7aa17d8bc122c84846595ae6ac9185f06e4d44f9fa904e7a5e90`。

六个模型均具备 weights、classes、preprocess、model_spec、metadata，以及历史 cpu_validation / evaluation / predictions。后两者只留在受控本地资产目录，不作为网站任务指标或公共下载内容。本轮没有读取 NEU-20 GT、下载数据或训练。

`metadata.json` 中 `classes_hash` 和 `preprocess_hash` 的真实口径是 UTF-8 JSON（`ensure_ascii=False, sort_keys=True, separators=(',', ':')`）的 SHA-256，并非原始文件字节哈希。六包均按这个口径核对；权重按原始字节 SHA-256 与 metadata 声明核对。

## 协议与兼容性决策

- 原导出环境为 torch 2.0.0+cu118 / torchvision 0.15.1+cu118。本机实际为 torch 2.14.0+cpu / torchvision 0.29.0+cpu / Pillow 12.3.0。本轮没有升级、重装依赖；通过六个真实 state_dict 的严格加载和前向确认当前环境兼容。
- 六类顺序由导出 classes.json 提供：0 龟裂/crazing，1 夹杂/inclusion，2 斑块/patches，3 麻点/pitted_surface，4 轧入氧化皮/rolled_in_scale，5 划痕/scratches。无正常类、未知类；保留 source_aliases。
- 预处理严格使用 PIL Grayscale(3) → Resize(224 整数、bilinear、antialias=True) → ToTensor(float32 /255) → ImageNet mean/std。**整数 Resize 表示短边 224、保持比例**，不是强制拉伸为 224×224。没有加入裁剪、CLAHE 或训练增强。
- 审定 v1 的类别与预处理 canonical hash 固定；被改动、错序或重新解释为其他协议时拒绝运行，不静默兼容。
- `weights=None, num_classes=6` 建立白名单 TorchVision 网络；`torch.load(..., weights_only=True, map_location='cpu')`；`load_state_dict(strict=True)`。不读取任意构造器、不执行学生源码、不采用 strict=False。加载前复核实际反序列化文件流的 SHA-256。
- 只接受有限浮点 B×6 logits；softmax 分数用于预测排序，不称为校准后的正确概率。当前逐张推理可处理矩形输入，限制 1–50 张、单图≤16MP、长宽比≤4，单次只加载一个模型且不保留全模型缓存。Worker 的任务超时和多模型调度另由业务层控制。
- 目录查询只做文件/JSON/hash与当前运行时版本校验，不导入 torch/torchvision，不执行模型前向。已在新 Python 进程检查六项 available 且无两模块导入。
- `validated.json` 是显式本机 CPU 复验凭据，绑定资产指纹和当前库版本；缺失、环境变化或资产变化时目录显示不可用。历史 cpu_validation.json 的 ok 不作为放行依据。

## 实际 CPU 验证

每模型真实加载一次，分别对合成方形图 B=1、B=2 和非方形图执行前向。全部得到有限 [1,6]、[2,6]、[1,6]。非方形原图 400×200，经预处理得到 [1,3,224,448]。没有真实标签，未计算任何精度。

CPU 线程数固定 2；前向计时为 B=1、3×224×224，预热 3 次、计时 10 次，P50/P95 由 10 个实际样本计算。计时只包围 module(tensor)，不含预处理、文件校验或加载。短时合成基准反映这台机器本次运行，不代表端到端服务吞吐量或任何现场准确率。

| 模型 | 参数量 | 资产校验 ms | 加载 ms | 两张图预处理 ms | 前向 P50 ms | 前向 P95 ms | 进程累计峰值 RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mobilenet_v3_small | 1,524,006 | 21.69 | 1666.20 | 6.05 | 11.96 | 15.60 | 311.72 |
| resnet18 | 11,179,590 | 142.78 | 375.01 | 6.79 | 44.83 | 52.42 | 386.58 |
| efficientnet_b0 | 4,015,234 | 48.03 | 167.03 | 3.95 | 30.20 | 41.50 | 386.58 |
| resnet50 | 23,520,326 | 258.07 | 611.01 | 3.44 | 113.76 | 206.82 | 504.77 |
| densenet121 | 6,960,006 | 80.56 | 301.97 | 3.18 | 87.70 | 104.36 | 504.77 |
| convnext_tiny | 27,824,742 | 296.66 | 875.84 | 6.43 | 80.32 | 101.05 | 565.05 |

加载时间含构建网络、复核文件流、受限反序列化和严格加载；第一个模型还可能包含首次 TorchVision 导入成本。预处理时间包括方形和矩形两张图。

RSS 使用 Windows GetProcessMemoryInfo 的 PeakWorkingSetSize，为该验证进程从启动至该时刻的累计峰值，含 Python、库和分配器保留内存，**不是各模型增量或同时驻留六模型的内存**。每个模型测完释放引用，再进入下一个；没有并发加载六模型。原始逐次时间与精确版本见 `asset-validation.json`。

第一次验证的模型加载和前向已完成，但最后收集 Windows 内存时因 ctypes 句柄参数声明错误，将整项标为失败。修正 GetProcessMemoryInfo 参数类型后完整复跑六模型；后续又为实际加载流增加哈希验证并完整重跑，最终结果以当前 JSON 和 `cpu-validation.log` 为准。不将测量脚本错误归因于权重不兼容。

## 定向回归

`tests/test_classification_infer.py` 最终 **20 tests passed**。这些测试只用合成配置、临时假权重与张量；模型构造/加载契约使用 mock，不加载部署权重或做网络前向。覆盖：canonical hash、CPU凭据、文件变更、类序错配、预处理错配、分类头错配、未知slug、运行时缺依赖/变更、无GT指标、完整GT与固定六类macro-F1、输入数量、输出形状/浮点/有限性、softmax Top-k、矩形灰度预处理、损坏/极端图像、weights_only/strict合同、加载前资产变更、压缩路径穿越与拒绝覆盖。

```powershell
.\.venv\Scripts\python.exe -B tests/test_classification_infer.py
.\.venv\Scripts\python.exe -B scripts/install_classification_assets.py --validate-only
```

第二条命令明确执行可信内置模型 CPU 前向并刷新本地凭据，不是普通无副作用测试。全新机器先以 `--source <zip> --validate` 安装；更换 Python/模型依赖后必须重新验证。网站启动不会自动执行这些操作。
