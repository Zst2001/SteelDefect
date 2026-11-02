# PCB 分割：阶段 4 本地模型准入与网站集成验收报告

日期：2026-10-29  
仓库：`F:\360MoveData\Users\40336\Desktop\Bofang\Steel_lab`  
分支 / 基线：`main` / `a662316384d6b0f289baf530a579d6346c0e5d10`  
任务依据：`docs/prompt/Steel_lab_PCB分割功能实现.md`

## 1. 一页验收结论

**总体状态：PASS，范围为本机隔离开发环境的阶段 4A 准入及阶段 4B 集成验收。生产发布：未执行；现有站点配置：未更改。**

三个正式模型均已在本仓库 `.venv` 的 Windows CPU 环境通过资产校验、安全严格加载、固定参考向量比较、稀疏前景检查、图层/CAM 和独立进程性能测试；随后才启用隔离验收环境，完成真实 MySQL、Redis/RQ、独立 Worker、HTTP API 和浏览器闭环。此结论不是沿用 AutoDL 的 CPU 结果，也不是 PCB 测试集重新评测。

| 交付项 | 本次结论 |
|---|---|
| 资产准入 | 原 ZIP/sidecar 保持原样；52 个普通文件、51 项内部 SHA、50 项 manifest 内容校验通过 |
| 三模型 | `unet`、`unet_resnet18`、`unetpp_resnet18` 全部 `VERIFIED_FOR_STAGING` |
| 数值一致性 | 固定容差内无超差元素；220 和 256 尺度 mask 均完全一致；220 尺度前景分别 5、63、696 像素，均无差异 |
| 网站能力 | 私有单张 220×220 RGB 上传、单模型选择、可选 GT/CAM、异步任务、图层、下载、历史及再跑 |
| 真实基础设施 | 隔离 MySQL + Redis/RQ，三模型真实任务通过；冷导入超时和排队撤权负向检查通过 |
| 真实浏览器 | **100 项检查通过**，三个模型均由 UI 提交并完成真实 CPU 推理；无 API 错误、无浏览器未捕获异常 |
| 后端回归 | **560 passed、3 skipped**；另有资产/推理单元测试 **81 passed、12 subtests passed** |
| 前端回归 | PCB 模拟接口 58 项、既有主页面 156 项、钢铁分类 52 项、阶段 C 静态契约 22 项及 5 个 SFC 语法检查通过 |
| 旧业务真实 CPU | 钢铁 UNet 无 GT 对照 / 有 GT 对照 / 公开演示通过；钢铁 MobileNet 分类无标签 / 有标签通过 |
| 默认模型 | U-Net；ResNet18-U-Net 保留为本机更快候选，U-Net++ 保留为离线 Recall 较高候选 |
| 功能开关 | 源码默认 `PCB_SEGMENTATION_ENABLED=false`；仅验收进程显式设为 true；准入记录失效时关闭提交 |
| 数据库 / Git | 无 schema 迁移；未操作原数据库和 Redis 数据；未 commit、push；未修改 `.env` |

**尚需项目负责人决定的事项：**何时在日常开发站点设置启用开关；生产发布窗口与资源安排；是否另立“运行中强杀恢复/硬内存限制”任务。取消任务当前属于 `NOT_SUPPORTED`，本次没有伪造取消按钮。公开发布 PCB 原图、GT 或权重的许可仍无依据，不应开放。

本轮证据统一位于 `docs/report/pcb-stage4-2026-10-29/`。当前权威 CPU 证据使用其中的 **`cpu-deployment-final/`**；早期 `cross-initial/`、`cpu-admission/`、`cpu-final/` 等目录只保留过程记录，不应用其旧运行配置替代最终数据。`changed-code-files.json` 列出本轮 54 个代码/配置/测试文件及 SHA-256，不包含用户原有未跟踪材料或模型资产。最终 `git diff --check` 通过，验收临时进程与带本轮标签的容器已清理。

## 2. 实施前盘点与复用边界

初始工作树已有未跟踪文档、历史截图、`docs/prompt/`、`ppt/`、`output/` 等内容，本轮保留。没有恢复工作区、切换分支或重新安装依赖。现有 MySQL/Redis 容器可用，但未将测试接入其数据；验收使用缓存镜像创建的独立临时容器。盘点时没有可复用的 API/Worker 进程，因此选用仓库既有 `.venv` 和实际 Windows `RQ SimpleWorker` 入口协议进行验证。

| 现有模块 | 本轮复用方式 |
|---|---|
| Vue 3 + Vite + Element Plus，`apps/web/src/router/index.ts` | PCB 场景进入独立工作台，继续使用现有外壳、登录、HTTP 客户端和结果记录 |
| FastAPI，`apps/api/app/main.py` | 增量注册 PCB router，不新建后端服务 |
| SQLAlchemy / MySQL 的 Task、TaskModel、DatasetVersion、Sample、Artifact、MetricSet、AuditLog | PCB 使用既有表；以独立 task type、dataset kind、预处理协议区分场景 |
| `services/submission.py`、`services/dispatch.py` | 沿用用户锁、请求幂等键、确定性任务 ID、唯一入队及投递状态判定 |
| `services/input_freeze.py` | 增加 PCB 身份快照，复用提交冻结和执行前核验 |
| `apps/worker/__main__.py`、`jobs.py` | 仍是 Windows SimpleWorker，增加 PCB 任务分派及独立执行体 |
| `services/tasks.py`、`records.py`、`task_artifacts.py` | 复用私有任务、导师提交/撤回、历史、再跑、路径防护和下载授权 |
| `services/classification.py::_registered` | 复用已有受控注册行的并发创建机制，不复制整套模型中心 |
| A/B/C 离线回归运行器 | 加入 PCB 测试，继续限制 `.env`、外网、真实执行器和生产存储访问 |

保持的边界：首页介绍和视觉 token 未改；侧栏仍是钢铁、PCB、太阳能电池板三个场景；PCB 检测仍为空任务，光伏仍未接入；公开演示未加入 PCB；钢铁正式评测仍为原 NEU-20 协议；学生 `.py/.pth` 的 Docker 隔离链路未改；科研助手仍为现有 harness，未增加 PCB 专科、跨专科路由或 RAG 集合。

## 3. 实际运行环境

| 项目 | 实测环境 |
|---|---|
| OS | Windows 11，`10.0.26200`，PowerShell |
| CPU / 内存 | Intel Core i7-9750H，6 核 12 线程，约 15.9 GiB 物理内存 |
| Python | 仓库 `.venv\Scripts\python.exe`，3.13.13，64 位 |
| PyTorch / torchvision | `2.14.0+cpu` / `0.29.0+cpu` |
| NumPy / Pillow | `2.5.3` / `12.3.0` |
| OpenCV | 模块 `cv2=5.0.0`；发行包 `opencv-python-headless=5.0.0.93` |
| PCB CPU 配置 | intra-op 2、interop 6、MKLDNN 开启；完成后恢复 Worker 原 intra-op 设置 |
| 真实队列执行器 | 同一 `.venv` 独立 Python 进程、RQ SimpleWorker，单 Worker 串行执行 |
| 隔离基础设施 | 已缓存 `mysql:8.0` / `redis:7-alpine`，`--pull=never`，127.0.0.1 随机端口、临时存储 |
| 浏览器 | Chromium `151.0.7922.34`，Playwright；桌面及 390px 实机浏览器布局检查 |

没有下载权重、运行训练或安装/升级依赖。真实链路使用同一模型加载器、同一预处理和同一 Worker 任务函数；不同之处仅为显式的测试数据库、Redis、存储、合成用户与开关配置。测试设置由 init-only 配置创建，不读取 `.env`，外部连接被审计钩子拒绝。

## 4. 阶段 4A：资产与模型准入

### 4.1 独立资产校验

| 项目 | 结果 |
|---|---|
| 原始目录 | `assets/PCB_segment/` |
| ZIP | `pcb_seg_meiwei_v2_formal_v1.zip`，144,022,706 字节 |
| ZIP SHA-256 | `7c93a1f299f7e2b998ee1c8473ce9f3b6b700487247d4c069a69ec0240549c1d` |
| 外部 sidecar / 提示词固定值 / 重算值 | 三方一致 |
| 解压统计 | 52 个普通文件，158,245,813 字节 |
| 内部清单 | `SHA256SUMS.txt` 51 项全部一致；manifest 50 个内容文件全部一致 |
| 原可信模型源码 SHA-256 | `f36e2b509030b607ea621cb80be6a424cc88b66f4003ec8b710d67a02c9b0a7b` |
| manifest SHA-256 | `fdb601a391a178ab6a761b4562945771807e511d990c5824727a2ac00fba9cf6` |
| 私有暂存目录 | `assets/pcb/meiwei_v2_formal_v1/`，不在前端 public、构建目录或任务 Artifact 中 |

`scripts/verify_pcb_assets.py` 使用标准库先检查中央目录、条目类型、路径、大小写冲突、Windows 保留名、尾随点/空格、重复条目、加密/软链接/特殊文件、大小与压缩比，再安全解压和逐文件校验。在此之前没有执行包内 Python。审核交接说明、许可和脚本后，运行原包 `tools/verify_archive.py` 得到 `ZIP_STRUCTURE_OK`。

未发现 Meiwei 原图/GT、训练 checkpoint、未授权模型、`.env`、逐图私有评测产物或超出白名单的文件。`.gitignore` 增加两个 PCB 资产目录；没有将 ZIP、权重、参考向量加入 Git。Vite 真实 HEAD 检查中，五个私有 ZIP/sidecar/权重/参考 logits/源码路径全部返回 403。构建中没有这些私有资产。

本轮末尾重新校验原 ZIP 与 sidecar，仍一致；见 `asset-recheck-final.json`。该文件的 `model_admission=NOT_VERIFIED` 表示资产校验器不负责模型准入，**不是**最终模型状态。最终模型状态见 CPU JSON 和私有准入回执。

### 4.2 权重身份与受控部署源码

| 模型 | 参数量 | 权重 SHA-256 | CAM 层 |
|---|---:|---|---|
| U-Net | 7,849,634 | `c9ffbb31c5bc80ef74b71d5b35a1d13517610656362a2030bae639156314235b` | `dec1` |
| ResNet18-U-Net | 14,413,570 | `6ce8f3ebe139c6781670af1889c1c80e519980ab056964a97b2359a1c7366fcd` | `dec0` |
| ResNet18-U-Net++ | 16,111,106 | `ff621b6e9d6097f7f8d89bc12bc37834c94c3e68aa190b99cffa22c7cbf2bd69` | `dec0` |

部署源码位于 `packages/infer/pcb/`。`models.py` 保留审核后的模型类和构建行为，移除仅训练/预训练加载使用的不安全 pickle 回退；不修改原包。`preprocess.py`、`postprocess.py` 与包内文件逐字节相同；`visualize.py` 仅调整部署导入和 hook/梯度的 finally 清理，保留计算语义。

`runtime.load_model` 对同一个打开的权重文件流先计算固定 SHA，再 `torch.load(weights_only=True, map_location='cpu')`，之后 `load_state_dict(strict=True)`，核对参数量、CAM 层并切换 eval。没有普通 pickle fallback，没有外网预训练下载，没有从上传目录或 ZIP 动态 import 源码。

API 侧目录读取不加载 Torch/学生代码。`catalog.require_admitted` 将全部资产、三个模型状态、部署源码哈希、协议哈希、运行库版本及线程配置绑定到私有回执；三模型任一失效均禁止提交。回执不是用户可写配置或公开 Artifact，不能手工伪造/改状态替代重测。

- 协议 SHA-256：`59ddc5613157d93291b8b99b4420d73bcd7b20b7a4e1717958e67ca27dae7158`
- 最终部署源码组合 SHA-256：`fe45790c8fdf6d413ea13f6fc13b797a3043e7f33ea586e82335b8c541673f6d`
- 私有回执：`assets/pcb/meiwei_v2_formal_v1.admission.json`
- 变更受绑定的推理源码、库版本或 CPU 配置后，必须重新运行三模型准入，不应复制旧回执绕过门禁。

### 4.3 模型准入矩阵

三模型全部通过：`strict=True`、无 missing/unexpected keys、eval/CPU；B=1 与 B=2 的 256×256 输出，B=1 的 256×272 结构自检；输出均为有限 `B×2×H×W` logits。非方形测试仅为结构检查，网站仍只接受 220×220。

真实输入协议为 RGB uint8 220×220 → 四边各补 18 个零像素 → float32 /255 → 256×256；模型输出 logits 后先裁取 `[18:238,18:238]` 回到原图坐标，再执行二通道 softmax / argmax，通道 1 为缺陷概率，argmax 为二值 mask。没有 resize、CLAHE、ImageNet mean/std 或擅自修改阈值。

| 模型 | 预处理逐值一致 | cross max_abs | cross max_rel | mask 一致率（256 / 220） | 原图前景：参考 / 本地 | 差异像素 / 前景 IoU | 状态 |
|---|---|---:|---:|---|---:|---|---|
| U-Net | 是，纹理/黑/灰三组 | 0.0000073910 | 0.0144992 | 1.0 / 1.0 | 5 / 5 | 0 / 1.0 | VERIFIED_FOR_STAGING |
| ResNet18-U-Net | 是，三组 | 0.0000180006 | 0.0074496 | 1.0 / 1.0 | 63 / 63 | 0 / 1.0 | VERIFIED_FOR_STAGING |
| ResNet18-U-Net++ | 是，三组 | 0.0000162721 | 0.0051138 | 1.0 / 1.0 | 696 / 696 | 0 / 1.0 | VERIFIED_FOR_STAGING |

固定容差仍为 `abs(a-b) <= 1e-3 + 1e-4*abs(b)`，三模型超差元素均为 0。max_rel 在接近零的参考值处可能相对较大，应结合固定 abs+rel 判据读取，不能将它误认为 mask 差异比例。全部差异坐标列表为空。

256 画布的前景分别为 16,902、17,179、17,680 像素（含 padding 区域）；原图裁切后才是 5、63、696。本轮稀疏前景检查以 220 坐标为重点，避免被全图背景一致率掩盖。

mask、overlay、boundary、probability heatmap、CAM 均回到 220×220；浮点概率无 NaN/Inf。纹理向量 CAM 为 `ok`，纯黑/纯灰图因为无前景返回 `unavailable`，不视为分割失败。概率与 CAM 分别计算；前者是 softmax 分数，后者是固定层对预测缺陷区域 logit 的梯度解释。原始 float32 概率数组在推理层可用，本期公开给授权任务用户的下载白名单只包含热力 PNG，不开放 `.npy`。

合成向量只证明实现一致性与运行能力，不能证明真实 PCB 泛化精度。本次未使用 140 张固定测试集重新评测。

## 5. 目标 CPU 性能与默认模型

每模型一个独立进程；加载时间包含权重哈希、反序列化和模型构造，不包含 Python/Torch 首次导入；未清空 OS 文件缓存。前向与完整预处理→前向→后处理各 warm-up 2 次、测量 7 次；CAM warm-up 1 次、测量 3 次。以下为最终部署配置（2 / 6 线程、MKLDNN 开启）的实际值，单位 ms。

| 模型 | 冷加载 | 前向 P50 / P95 | 完整推理 P50 / P95 | CAM P50 / P95 |
|---|---:|---:|---:|---:|
| U-Net | 1655.24 | 283.71 / 306.14 | 294.30 / 366.97 | 839.97 / 840.20 |
| ResNet18-U-Net | 1890.28 | 189.66 / 208.06 | 196.66 / 242.06 | 583.52 / 584.98 |
| ResNet18-U-Net++ | 2129.69 | 359.02 / 380.91 | 380.56 / 432.92 | 1274.72 / 1318.81 |

完整推理耗时不含队列等待、全套准入扫描、加载模型、图片落盘、HTTP 和 CAM，因此不能直接作为网页任务的端到端 SLA。CAM 重复次数较少，P95 仅是这批样本的统计值。真实基础设施测试中，包含新 Worker 启动和重复投递检查的每模型测试段约 15–17 秒，不能与上表混为一谈。

使用 Windows `GetProcessMemoryInfo`，阶段内每 10ms 采样 RSS，并同时记录 OS 进程生命周期峰值。每行来自独立进程，单位 MiB：

| 模型 | Torch 导入前 | 模型加载前 | 加载后 | 推理采样峰值 | CAM 采样峰值 | 最终 OS 峰值 |
|---|---:|---:|---:|---:|---:|---:|
| U-Net | 27.7 | 204.2 | 345.3 | 515.9 | 604.6 | 604.7 |
| ResNet18-U-Net | 27.7 | 204.7 | 395.8 | 498.3 | 556.6 | 557.7 |
| ResNet18-U-Net++ | 27.5 | 204.6 | 408.0 | 547.9 | 677.7 | 678.9 |

以下只引用冻结交付包中的 **Meiwei v2 140 张 test 离线成绩**，未在本机重新计算：

| 模型 | 离线 Defect Dice | 离线 Defect IoU | 离线 Recall | 本期定位 |
|---|---:|---:|---:|---|
| U-Net | 0.8028 | 0.6706 | 0.7864 | 默认，三者 Dice 最高且参数最少；本机延迟可接受 |
| ResNet18-U-Net | 0.7955 | 0.6604 | 0.7851 | 本次本机完整推理/CAM 更快、峰值 RSS 更低的候选 |
| ResNet18-U-Net++ | 0.7789 | 0.6379 | 0.8233 | 离线 Recall 较高、CPU/CAM 成本较高的候选 |

本次只采用单图、单模型、Worker 串行加载，不新增跨任务模型缓存。固定输入与模型、2 个 intra-op 线程、120 秒任务超时控制可预测的资源使用；没有宣称 Windows SimpleWorker 具备强制 OS 内存隔离。

## 6. 阶段 4B：架构与业务实现

### 6.1 主要文件与调用链

| 新增 / 修改位置 | 核心职责 |
|---|---|
| `scripts/verify_pcb_assets.py` | 外部固定 SHA、路径/条目白名单、安全解压和内部哈希 |
| `scripts/check_pcb_cpu.py` | 三个独立进程准入、cross/稀疏前景/性能/RSS、生成受绑定回执 |
| `packages/infer/pcb/{models,preprocess,postprocess,visualize,runtime,catalog}.py` | 受控二类模型、严格加载、固定协议、图层/CAM、准入门禁 |
| `apps/api/app/routers/pcb_segmentation.py` | 已登录模型目录、单图上传、任务创建 |
| `services/pcb_segmentation.py` | `create_batch`、`create_pcb_task`、`pcb_snapshot`、模型/协议注册和结果序列化 |
| `services/pcb_delivery.py` | `reconcile_unclaimed_failure`，轻量处理领取前 RQ 失败/超时 |
| `apps/worker/pcb_segmentation.py` | `assert_pcb_execution`、`compute`、`run_pcb_body`、GT 指标、暂存与原子发布 |
| `jobs.py`、`input_freeze.py`、`dispatch.py` | 新任务分派、冻结字段、PCB 可选失败回调；旧任务回调默认不变 |
| `tasks.py`、`records.py`、`task_artifacts.py` | 原权限/历史/再跑体系增加 PCB；私有结果白名单 |
| `datasets.py`、`models.py`、`routers/models.py`、`perf.py`、`assistant.py` | 阻止 PCB 从旧数据集/钢铁模型/性能测量/分割助手入口混入或绕过权限 |
| `scenes.py`、`main.py`、`config.py` | 场景能力、注册 router、默认关闭及 120 秒超时设置 |
| `apps/web/src/views/pcb/` | `PcbNewView.vue`、`PcbTaskView.vue`、共用局部样式与接口类型 |
| 前端 router / AppLayout / RecordsView / api labels、http | PCB 导航激活、详情路由、历史筛选、类型标签和幂等 HTTP 请求 |
| `apps/api/app/db/models.py` | 仅补充 Task.type 注释，无表结构变化 |

核心流程：

```text
登录用户 → PCB 目录门禁 → 上传原图 / 可选 GT
  → 私有 DatasetVersion(pcb_batch) + Sample
  → 固定 model_id + include_cam + Idempotency-Key
  → Task(pcb_segmentation) / TaskModel / TaskSample + inputs.json
  → 既有 Redis/RQ 唯一作业 task-<task_id>
  → jobs.run_pcb_segmentation → _run_task → run_pcb_body
  → 权限/快照/实际读取字节复核 → CPU 分割 / 可选 CAM
  → 暂存输出 → 发布前再次加锁复核 → Artifact / 可选 MetricSet / AuditLog
  → 既有任务轮询、记录与鉴权 file 下载 → PCB 结果页面
```

场景为 `pcb`，task kind 为 `segmentation`，数据库 Task.type 为 `pcb_segmentation`，DatasetVersion.kind 为 `pcb_batch`，协议 dataset 为 `pcb_meiwei_v2`。不借用 NEU-20、`neu_200` 或钢铁四类协议。

### 6.2 API、输入和数据冻结

| 入口 | 行为 |
|---|---|
| `GET /api/scenes/pcb/segmentation/models` | 登录后检查开关、三模型和当前运行环境准入；返回固定目录 |
| `POST /api/scenes/pcb/segmentation/uploads` | multipart `file` + 可选 `gt`，拒绝多个图片/GT 与额外字段 |
| `POST /api/scenes/pcb/segmentation/tasks` | `batch_id`、固定 `model_id`、严格布尔 `include_cam`；支持 `Idempotency-Key` |
| `GET /api/tasks/{id}`、`/metrics` | 复用授权，PCB 专用序列化，无 GT 则仅 `available=false` |
| `GET /api/tasks/{id}/file/{rel_path}` | 复用授权和路径防护，只能读取成功 PCB 任务的白名单制品 |
| `GET /api/records?type=pcb_segmentation` | 既有个人/导师视图、详情、提交/撤回、再跑 |

原图限单帧 220×220 RGB PNG/JPEG，非空且不超过 2 MiB，扩展名与实际格式匹配。拒绝灰度、RGBA、错误尺寸和非缺省/非 1 的 EXIF 方向；不静默转色、缩放或旋转。只按服务器生成的路径存放，不使用上传文件名拼接目标路径。

GT 只接受 220×220 的 `L` 单通道 PNG，值集合属于 0/1 或 0/255；无损规范化为 0/1 后保存，原图上传字节保持原样。GT 不作为模型前向输入。

模型权重 SHA、部署代码指纹、处理协议、CAM 开关、场景、类别、样本/GT 事实进入冻结快照。执行器核验自己实际消费的图片/GT 字节，防止先校验后读取期间的替换。再跑创建新 Task，并保留 CAM 选择，不覆盖旧结果。

### 6.3 权限、发布与异常

PCB 继续沿用所有者私有/提交导师后可见/撤回即失去导师访问的规则；其他学生不能读取任务、原图、GT、结果或下载。旧数据集详情/GT 路径拒绝 `pcb_batch`，避免绕过任务级授权。PCB 内置模型与钢铁模型选择器、旧性能 API、助手推理工具及旧 Worker 路径互斥。

执行期间不持有授权数据库锁做 CPU 计算。发布前按既有 actor → DatasetVersion → Task 顺序重新加锁，复核用户、冻结输入和协议；执行期间撤权不会发布结果。

制品先写入专用暂存目录，核验后逐文件 `os.replace` 到确定路径，再同事务登记 Artifact/MetricSet/终态。普通发布失败回滚记录并清理本次文件；已提交制品不会因缓存刷新失败而删除。没有声称文件系统与数据库是跨系统原子事务，强杀窗口见限制章节。

本轮验收发现并修复两个实际问题：

1. **领取前超时状态不一致。** 当 RQ 在第一次导入 Torch 时超时，原应用 Task 仍 queued。新增不导入 Torch 的 PCB 失败回调，严格验证 RQ 函数名、参数、确定性 job ID、Task.type 和 queued 状态，更新 Task/TaskModel/Audit；不覆盖 running/成功/其他尝试。原 1 秒冷导入超时条件复验后，RQ 和应用均 failed，`PCB_JOB_TIMEOUT`，Artifact/Metric 为 0。
2. **CAM 分支吞全任务超时。** 普通 CAM 异常仍可独立失败，但 `JobTimeoutException` 必须上抛并映射 `PCB_JOB_TIMEOUT / resource`。新增完整任务生命周期测试，证明普通 CAM 错误可成功保留分割和 GT 指标，而超时最终 failed、无 Artifact/Metric，仅保留冻结输入。

所有投递失败信息采用固定安全文本，不将底层异常内容或密钥返回前端。未知投递仍沿用 `QUEUE_UNKNOWN` 的保守语义，不擅自重复入队。失败后的“再跑”属于新任务，不是静默覆盖/重试原制品。

### 6.4 结果与前端

工作台路由为 `/inspect/pcb`，详情为 `/inspect/pcb/tasks/:taskId`。页面沿用现有浅色工作台、深色侧栏和蓝色强调；原图与模型选择分区、单图预览、GT/CAM 高级选项、明确的禁用/错误/排队状态，没有虚构进度或精度。

结果提供原图、0/1 mask、红色 overlay、黄色 boundary、Viridis 缺陷概率、可选 Grad-CAM、GT 与 TP/FP/FN 误差图；支持图层切换、放大、当前图层 PNG 和受控 JSON 下载。Mask 预览仅通过 CSS 提高亮度，下载保持原始 0/1。

只有合法 GT 才创建 `MetricSet(scope=pcb_uploaded_pair,n=1)`，计算 Defect Dice、IoU、Precision、Recall 和 TP/FP/FN/TN。分母为零返回 null，界面显示“—”。无 GT 完整可用，但不显示精度数值。页面不展示离线 test 分数，避免与当前图片评价混淆。

仅允许：`origin/image.png`、合法 `gt/image.png`、模型对应的 mask/overlay/boundary/probability/CAM/error PNG、`pcb.json`。不开放 PCB bundle、服务器 log、`inputs.json`、模型源码、权重、内部 metadata 或参考 logits。

## 7. 验证结果与证据分级

| 检查 | 结果 | 真实依赖 / 限定 | 证据 |
|---|---|---|---|
| 外部/内部资产与安全路径 | PASS；末尾重验一致 | 原 ZIP，只读；安全解压已在最初完成 | `asset-admission.json`、`asset-recheck-final.json` |
| 包内第二重验证器 | `ZIP_STRUCTURE_OK`，exit 0 | 审核后运行，无推理/训练 | 本次命令输出 |
| 三模型 CPU 准入 | 3/3 VERIFIED_FOR_STAGING | 真权重、真实本机环境、独立进程 | `cpu-deployment-final/*.json`、各模型日志 |
| 资产 / 推理单元测试 | 81 passed、12 subtests passed | 固定加载纪律、前景判据、CAM 等；不等同真实队列 | `pcb-admission-tests-final.log` |
| A/B/C + PCB + 旧业务隔离回归 | 560 passed、3 skipped，60.06s | SQLite、临时存储、fake queue，禁外网/`.env`/真实执行器 | `backend-regression-final.log` |
| PCB 定向生命周期 | 60 passed，已包含在上述 560 中 | 含撤权、字节替换、CAM 超时、发布失败、回调身份及终态保护 | `tests/test_pcb_backend.py`，完整回归日志 |
| PCB HTTP→直接 Worker 真权重 | 1 个测试、三个模型成功 | 真 CPU；SQLite / fake queue，不是 Redis 证明 | `cpu-http-flow.json` |
| 真实 MySQL / Redis / RQ | PASS | 隔离真实 MySQL InnoDB、RQ 独立 Worker；三模型、一个有 GT、幂等/重复投递/下载/权限 | `infrastructure/result.json`、`worker-*.log` |
| 真实 RQ 超时 / 排队撤权 | PASS | 1 秒冷导入 deadline；创建者排队后禁用；均无结果残留 | `infrastructure/result.json` 的 negative_cases |
| 真实浏览器闭环 | 100 项 PASS | 三次 UI 真实上传/提交、真实队列/CPU、图层/PNG/JSON/历史；全部无 GT | `live-browser/results.json`、`browser.log`、截图 |
| PCB 前端异常与布局 | 58 项 PASS | 模拟业务 API，1440/768/390；GT/无 GT/CAM/失败/禁用等 | `frontend/results.json` |
| 既有主页面回归 | 156 项 PASS | 模拟 API，含首页、公开演示、对照、助手及多尺寸布局 | `steel-ui-regression/results.json` |
| 钢铁分类前端 | 52 项 PASS | 模拟 API | `classification-regression/results.json` |
| 阶段 C 前端契约 | 22 项 + 5 SFC 语法 PASS | 静态/语法检查，不是真后端 | `tests/check_phase_c_frontend.mjs` 执行输出 |
| 旧钢铁分割 CPU | 1 测试、3 链路 PASS | 真实内置 UNet；原 builder/预测执行；SQLite、fake queue、鉴权依赖夹具 | `legacy-steel-cpu.json` |
| 旧钢铁分类 CPU | 1 测试、2 次运行 PASS | 真实 MobileNet，每次 2 张合成图；SQLite / fake queue | `legacy-classification-cpu.json` |
| Vite 生产构建 | PASS | 临时输出目录、无 `.env`；PCB chunk 存在，私有资产不进入构建 | `tests/check_pcb_build.mjs` 执行输出 |
| 私有资产 HTTP 隔离 | 根 200、5 个私有路径均 403 | 当前 Vite 配置，真实 HEAD；未下载资产内容 | `tests/check_pcb_asset_privacy.mjs` 执行输出 |

不能相加重复宣称：PCB 定向 60 项已经包含在完整 560 项中；模拟浏览器结果与真实浏览器结果分别报告。真实基础设施三模型测试和最终真实浏览器分别运行，不是把同一结果复制三次。

旧钢铁 CPU 回归的加载阶段使用**测试专用的固定哈希、weights_only=True 读取包装**，然后交给现有严格 builder；未修改生产钢铁加载器，不能据此宣称其旧加载实现已完成安全升级。无 GT 对照 / 有 GT 对照 / 公开演示对应 MetricSet 数为 0 / 1 / 0，公开演示无精度响应或指标文件；授权图层及 bundle 下载通过。

真实浏览器脚本调试中，曾遇到本地启动探针未识别就绪 API，改为不依赖环境代理/SSL 配置的直接 loopback HTTP 探针后正常；另一个初版断言把原有 `index.html` 的 Google Fonts 请求也视为失败。最终仍阻断这些外部字体请求，只允许其已知路径作为“被阻断的既有可选资源”，其他外部请求继续判失败。没有允许联网下载字体或改动首页。初版三模型业务已成功的记录保存在 `live-browser/before-font-guard-adjustment.json`；最终依据 `results.json` 的 PASS。

### 未运行、跳过与限制

| 项目 | 状态 | 原因 / 含义 |
|---|---|---|
| 3 个真实文件系统 symlink 测试 | SKIPPED | Windows 当前权限不允许创建测试符号链接；已有路径规则/负向测试通过，不能替代这 3 项 |
| 完整 MySQL REPEATABLE READ 并发专项矩阵 | NOT_RUN | 本次真实 MySQL 跑了 PCB 闭环及负向生命周期，但未把旧并发专项的全部场景重跑为 MySQL；SQLite 回归不能证明 MySQL 所有竞争时序 |
| Worker 执行中进程强杀、机器断电恢复 | NOT_RUN | 不等同 RQ 的受控超时；领取前回调不接管 running，保留此边界 |
| 任务取消 | NOT_SUPPORTED | 原系统无取消 API，本期没有伪造支持 |
| PCB 固定 test 重新评测 / 训练 | NOT_RUN（按任务范围禁止） | 无原始数据公开许可；本期只做实现准入与合成输入集成验证 |
| 正式 NEU-20 全量评测 | NOT_RUN | 本期回归协议与代表性钢铁 CPU 链路，未运行正式评测任务 |
| 学生插件 Docker 实际执行 | NOT_RUN | 未修改学生执行器；相关权限/安全回归使用隔离夹具 |
| `vue-tsc` 全项目类型检查 | NOT_RUN | 当前没有该可用工具，本次未安装依赖；Vite 构建和 SFC 检查不能冒充完整类型检查 |
| 生产迁移/生产发布/原数据库验收 | NOT_RUN | 无 schema 迁移需求，也未获得生产发布授权 |

最终后端日志含两条既有 Starlette/anyio 弃用警告；推理单元测试含一条 PyTorch backward hook 提示，不影响本次 CAM 验证。构建存在大于 500 kB chunk 的体积提示，本期没有为此重构原前端。

## 8. 可复现命令

以下在仓库根目录 PowerShell 运行。一行一条命令，不使用 bash `&&`；不输出 `.env`。复验 CPU/真实链路会产生本地证据及临时测试任务，不能将测试脚本指向生产配置。

### 8.1 资产和三模型准入

```powershell
Set-Location 'F:\360MoveData\Users\40336\Desktop\Bofang\Steel_lab'
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -B scripts/verify_pcb_assets.py
```

本机已完成安全解压。仅首次、目标目录不存在时使用 `--extract`；校验器拒绝覆盖现有解压目录，不应手工覆盖原 ZIP 或通过重算“预期 SHA”消除错误。

```powershell
.\.venv\Scripts\python.exe -B assets/pcb/meiwei_v2_formal_v1/tools/verify_archive.py --root assets/pcb/meiwei_v2_formal_v1
$pcbEvidence = 'docs/report/pcb-stage4-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
.\.venv\Scripts\python.exe -B scripts/check_pcb_cpu.py --output $pcbEvidence --threads 2 --warmup 2 --repeats 7
```

最后一条运行全部三模型，并在全部通过后生成/更新私有准入回执；不要用 `--cross-only` 代替完整准入，不要改容差。当前 CPU evidence 正式运行目录为 `cpu-deployment-final`。

### 8.2 单元和既有回归

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests/test_pcb_asset_admission.py tests/test_pcb_infer.py
.\.venv\Scripts\python.exe -B -c "import platform, runpy; platform.uname(); runpy.run_path('tests/run_phase_a_tests.py', run_name='__main__')"
.\.venv\Scripts\python.exe -B tests/check_pcb_cpu_flow.py
.\.venv\Scripts\python.exe -B tests/check_classification_cpu_flow.py --report docs/report/pcb-stage4-2026-10-29/legacy-classification-cpu.json
.\.venv\Scripts\python.exe -B tests/check_steel_cpu_regression.py
node tests/check_phase_c_frontend.mjs
node tests/check_pcb_build.mjs
node tests/check_pcb_asset_privacy.mjs
```

原 CPU 回归脚本会覆写它自身的本轮报告输出；需要保存多次运行时使用可选 `--report`（支持的脚本）或先另存证据，不要覆盖其他阶段文档。`platform.uname()` 在离线审计钩子安装前初始化本机平台信息。

模拟浏览器复验使用本机已有 Playwright 包，不执行 `npm install`：

```powershell
$pcbPlaywright = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'
node tests/check_pcb_frontend.mjs $pcbPlaywright docs/report/pcb-stage4-2026-10-29/frontend
node tests/check_classification_frontend.mjs $pcbPlaywright docs/report/pcb-stage4-2026-10-29/classification-regression
node tests/check_frontend_light.mjs $pcbPlaywright docs/report/pcb-stage4-2026-10-29/steel-ui-regression
```

### 8.3 真实隔离基础设施与浏览器

前置条件：Docker Desktop 可用，已有 `mysql:8.0`、`redis:7-alpine` 缓存镜像，仓库 `.venv`/node_modules/Playwright 均已就绪，三个模型回执有效。

```powershell
.\.venv\Scripts\python.exe -B tests/check_pcb_infrastructure.py
.\.venv\Scripts\python.exe -B tests/check_pcb_live_flow.py
```

脚本自行创建带唯一所有权标签的临时容器、随机 loopback 端口、合成账号及存储；不读取 `.env`，不连接原 MySQL/Redis，不拉取镜像。浏览器 session 经 stdin 传递，不进入 argv 或报告。结束时关闭本次 API/Worker/Vite/浏览器，检查容器所有权后按精确 ID 清理；Windows Python 子进程使用本次 Popen 对应的进程树清理，不按名称结束其他 Python。

### 8.4 日常本地站点启用与启动

**本轮没有自动开启原数据库对应的站点。**下面供本地运维使用：只有确认目标确为开发环境、资产回执有效、数据库/Redis 已就绪时才启动。不修改 `.env`，用各进程的临时环境变量；不要同时重复启动已有同名 Worker。

API PowerShell 窗口：

```powershell
Set-Location 'F:\360MoveData\Users\40336\Desktop\Bofang\Steel_lab'
$env:PCB_SEGMENTATION_ENABLED='true'
$env:SEED_ON_START='false'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000 --reload
```

Worker PowerShell 窗口：

```powershell
Set-Location 'F:\360MoveData\Users\40336\Desktop\Bofang\Steel_lab'
$env:PCB_SEGMENTATION_ENABLED='true'
.\.venv\Scripts\python.exe -m apps.worker
```

Vite PowerShell 窗口：

```powershell
Set-Location 'F:\360MoveData\Users\40336\Desktop\Bofang\Steel_lab\apps\web'
npm run dev -- --host 127.0.0.1 --port 5173
```

确认 API 启动完成及 `http://127.0.0.1:8000/api/health` 后，用现有账号登录 `http://127.0.0.1:5173/inspect/pcb`。三个模型全部可用才允许选择图片和提交；不要用 Meiwei 私有原图充当公共演示样例。原数据库正常写入的用户上传/任务记录只应在负责人选择启用该开发站点后产生。

## 9. 安全、许可和回退

许可证说明仅支持同项目内的本地 CPU 验收，没有证据授权公开重分发三份权重、Meiwei 原图或 GT。依赖/模型仓库可能有开源许可，并不能替代数据和实验权重许可。原包内部 `visualization_spec.json` 含样本标识，不作为用户 Artifact。

PCB 可信内置代码在 Worker 中运行；用户不能提交模型代码/权重路径，Web/API 不导入用户 Python。原学生模型仍走原 Docker 隔离，不借 PCB 入口绕过。所有截图是明确标记的合成输入或模拟接口，不是真实 PCB test 图，更不是性能宣传证据。

关闭 PCB：在 API 与 Worker 各自的启动环境设置 `PCB_SEGMENTATION_ENABLED=false` 后重启对应进程。先关闭 API 以停止新增 PCB 提交，再让当前任务正常结束并重启 Worker；不要清空共享 Redis 队列、强杀所有 Python 或删除 Task/Artifact。关闭后的 Worker 会拒绝继续执行未获启用的 PCB 任务；已成功且授权的历史结果仍可读取。

本期没有 schema 迁移，故无需数据库结构回滚。代码回退应只撤回本轮文件/差异，并保留原业务代码与用户修改，不能执行整体 `git reset --hard`。如已产生 PCB 历史任务，优先保留 PCB 只读序列化/Artifact 代码并关闭提交；完全移除代码前需明确历史可读性方案，不删除记录。

剩余工程边界：

- Windows SimpleWorker 使用同进程 CPU 执行及 RQ 超时，不提供 OS 级强制内存限额；native kernel 无响应/强杀不等同已测的 Python deadline。
- 尚未验收运行中强杀后自动修复 running 状态，以及“文件发布与 DB commit 之间断电”的恢复。已覆盖的是正常异常回滚和 RQ 受控超时。
- 提交 `QUEUE_UNKNOWN` 时沿用原项目保守流程，需要运维核对；不能自动无限重发。
- 模型库版本、CPU 线程/interop、权重或受绑定源码变更必须重做准入。其他机器不能直接沿用此 Windows 回执。
- 日常开发站点启用、生产发布、取消能力、专用队列/硬资源隔离、公开数据/权重许可均是独立决策；本报告不代表这些事项已获授权或已完成。

## 10. 最终验收清单

- [x] 原始 ZIP/sidecar 未改写，独立安全解压和全部 SHA 验证通过。
- [x] 三模型均在实际本机 Worker Python 环境安全严格加载，未使用随机权重或不安全回退。
- [x] 预处理逐值一致，固定 reference 门槛通过，稀疏前景无未解释差异。
- [x] 三模型真实 CPU 图层、CAM 及无前景行为验证通过。
- [x] 本机 P50/P95 与独立 RSS 有原始记录，默认模型选择有明确依据。
- [x] PCB 任务、模型、数据与钢铁分割/分类区分，未扩展 PCB 检测/光伏/公开样例。
- [x] 单图异步任务、合法 GT 指标、历史和授权下载有真实基础设施证据；三个模型有真实浏览器闭环。
- [x] A/B/C、共享撤销、幂等、Artifact 白名单和旧业务回归通过；具体 skip / NOT_RUN 已单独列出。
- [x] 私有资产未进入静态服务/构建/用户下载白名单，未提交权重或 `.env`。
- [x] 代码、测试、证据与本报告已保存；本次未 commit、push 或自动开展下一阶段。
