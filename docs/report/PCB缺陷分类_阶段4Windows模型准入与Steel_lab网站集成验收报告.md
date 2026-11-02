# PCB 缺陷分类：阶段 4 Windows 模型准入与 Steel_lab 网站集成验收报告

日期：2026-11-02。结论：**PASS（本机准入、增量集成及隔离验收通过；日常站点未自动启用）**。

执行仓库：`F:\360MoveData\Users\40336\Desktop\Bofang\Steel_lab`。
分支保持 `main`，HEAD 保持 `a662316384d6b0f289baf530a579d6346c0e5d10`。
依据：`docs/prompt/PCB缺陷分类_阶段4Windows模型准入与Steel_lab网站集成_Codex实施提示词.md`。

本报告是本次唯一正式阶段验收报告。开发过程中的失败、自测和重试保留在证据目录，以下结论以最终通过的运行记录为准。
证据目录：[pcb-classification-stage4-20261102](pcb-classification-stage4-20261102/)。

## 1. 实际完成的能力与边界

在既有 PCB 分割旁新增「缺陷分类」工作区。登录用户上传一张**已经裁剪、主要包含单个缺陷的 ROI**，选择固定内置模型，通过原有 Task → Redis/RQ → Windows CPU Worker 流程得到六类预测。

- 新建入口：`/inspect/pcb/classification`。
- 结果入口：`/inspect/pcb/classification/tasks/:taskId`。
- 原 PCB 分割入口仍为 `/inspect/pcb`，分割行为及历史结果保留。
- 侧栏仍为「PCB板检测」场景入口；分类与分割在页面内切换，没有新增任务名称侧栏项。
- 默认模型仍是 **EfficientNet-B0**；MobileNetV3-Small 为轻量备选。
- 固定类别依次为：`0 open 断路`、`1 short 短路`、`2 mousebite 鼠咬`、`3 spur 毛刺`、`4 copper 余铜`、`5 pin-hole 针孔`。
- 没有 normal 类，不定位整板缺陷、不自动裁框、不生成分割掩码或 Grad-CAM。
- 单次仅一张 ROI、一个模型，不接受真实类别/GT，不生成 Accuracy、Macro-F1 或本图准确率。置信度只表示六分类 softmax 输出。
- 未扩展公开 demo、训练、全量 Test 1,545 评测、学生模型插件、学术 RAG 或检测任务。

**独立门禁 `PCB_CLASSIFICATION_ENABLED` 的代码默认值仍是 `false`。本轮只在隔离验收进程中开启，未改 `.env`、未发布生产、未自动 commit/push。**

## 2. 环境盘点及兼容性选择

实际使用 Windows 11 `10.0.26200`，不是 WSL、AutoDL 或 Linux 模拟路径。复用已有 `.venv` 与前端 `node_modules`，没有安装或升级依赖。

| 项目 | 实际环境 |
|---|---|
| Python | 3.13.13，仓库 `.venv\Scripts\python.exe` |
| PyTorch / torchvision | 2.14.0+cpu / 0.29.0+cpu |
| NumPy / Pillow | 2.5.3 / 12.3.0 |
| Node / npm | 24.14.0 / 11.9.0 |
| Docker Engine | 28.1.1；本轮恢复 Docker Desktop 后可用 |
| RQ | 2.12.0，Windows `SimpleWorker` |
| CPU 标识 | Intel64 Family 6 Model 158 Stepping 10, GenuineIntel |
| 分类计算设置 | CPU FP32，intra-op 2、inter-op 6、MKLDNN 开启 |
| 内存采样 | Windows `GetProcessMemoryInfo`；未安装 psutil |

### 数据库无需迁移

源码中 `Task.type` 是 `String(16)`；提示词建议的 `pcb_classification` 超过长度。按提示词允许的兼容命名，采用 **`pcb_classify`**，协议仍为 **`pcb_cls_deeppcb_roi_v0`**，批次类型为 `pcb_cls_batch`。

没有扩展列、增加表或修改真实数据库。`db/models.py` 仅补充注释，字段定义未变。新业务复用 `Dataset`、`DatasetVersion`、`Sample`、`PreprocessSpecRow`、`Model`、`ModelVersion`、`Weight`、`Task`、`TaskModel`、`TaskSample`、`Artifact`、`AuditLog`。

### 既有修改的保护

任务开始时仓库已有较多未提交的 PCB 分割、前端、权限相关变更，以及未跟踪报告、`ppt/`、`output/`。没有还原、删除、暂存或提交这些文件。

本轮开始记录了 253 个源码/配置文件哈希；结束时没有缺失文件。本次增量涉及 **23 个已有文件、20 个新源码/测试/来源说明文件**。`git diff --stat` 含此前修改，不能视作本轮独有变更。

首页、`AppLayout.vue`、科研助手服务、PCB 分割 service/worker、原分割推理包等保护对象保持任务开始时的内容；首页「实验室现未来将」未改。

证据：[初始 Git 状态](pcb-classification-stage4-20261102/git-status-before.txt)、[文件基线](pcb-classification-stage4-20261102/baseline-files.json)、[本轮变更清单](pcb-classification-stage4-20261102/change-inventory.json)、[结束保护核验](pcb-classification-stage4-20261102/preservation.json)、[结束 Git 状态](pcb-classification-stage4-20261102/git-status-after.txt)。

## 3. 原始资产、安全解包与准入

原始 ZIP 和 sidecar 均保留在 `assets/PCB_fenlei/`，未修改。

| 文件/项目 | 最终核验 |
|---|---|
| ZIP | `pcb_cls_deeppcb_roi_v0_formal_v1.zip`，20,825,269 bytes |
| ZIP SHA-256 | `bfb1c0ce379a47b5ac9acaa11c990042b1d75eddc99dfd55479a0f619316d8ba` |
| sidecar 声明 | 与固定 ZIP SHA、实际计算值一致 |
| sidecar 本身 SHA-256 | `14c5dc30f65a68c19fb0c923dfafbfc440094f4f365b92797969dee96b888fe1` |
| MANIFEST SHA-256 | `7b2527efce91290c0da179481232b0ab24838bc75b992912ce2e1d386db9703b` |
| EfficientNet-B0 权重 SHA-256 | `bb8a58511246651111cb6cb43c0c101fe20ba7d4de1633254c0432f03e039c39` |
| MobileNetV3-Small 权重 SHA-256 | `ea56cb4b3b2fd3be9d672b85780a07b1040556ea8acf07be4e9e7f20cb48b2f3` |

`scripts/verify_pcb_classification_assets.py` 复用原 PCB 准入器的路径/成员检查，固定校验 ZIP 字节数、SHA、sidecar、14 文件白名单、CRC、13 项清单长度及 SHA。拒绝路径穿越、绝对路径、盘符、链接/特殊成员、重复/大小写碰撞、Windows 保留名、尾随点/空格、异常压缩比及解压大小。

解包位置：`assets/pcb_classification/deeppcb_roi_v0_formal_v1/`。首次解包只允许新目录，不覆盖已有目录。所有部署文件保持原包字节，网站执行的是经过审阅后新增的固定仓库模块，不动态 import 解包目录或上传目录中的 Python。

新增私有准入回执：`assets/pcb_classification/deeppcb_roi_v0_formal_v1/.windows-admission.json`。回执绑定协议、固定 ZIP/清单、两模型身份、部署源码哈希、Python/torch/torchvision/NumPy/Pillow、CPU 与线程策略及准入结果。文件或配置不符时拒绝提交/执行。

原始 ZIP、解包资产和回执均被 `.gitignore` 排除。Vite 开发/预览服务器增加分类资产、原包和受控分类源码目录拒绝规则；没有公开下载权重的路由。

证据：[14 文件审计](pcb-classification-stage4-20261102/asset-audit.json)、[36 项解包/篡改/失效检查](pcb-classification-stage4-20261102/admission-negative.json)。篡改测试只针对临时副本；原始包、部署资产及私有回执未被篡改测试覆盖。

## 4. Windows CPU 正确性、性能及缓存

### 原包与部署实现分别验证

原包 `runtime/smoke_test.py` 在仓库解释器中原样运行，退出码 0，两个模型均 PASS；其 `1e-5` 阈值未改，未使用 `--write-reference`。Windows 运行设置 UTF-8，避免原包默认编码读取中文配置出现乱码。

部署准入事先采用 `abs(actual-ref) <= 1e-3 + 1e-4 * abs(ref)`，没有根据结果放宽。实际误差也满足更严格的原包阈值。

| 模型 | 参数量 | strict missing / unexpected | 合成参考预测 | 最大绝对误差 | 最大相对误差 |
|---|---:|---:|---|---:|---:|
| EfficientNet-B0 | 4,015,234 | 0 / 0 | 3，spur / 毛刺 | 2.9802322e-6 | 9.8517353e-6 |
| MobileNetV3-Small | 1,524,006 | 0 / 0 | 1，short / 短路 | 2.1457672e-6 | 1.0576659e-6 |

两者均使用 torchvision 原生结构、`weights=None`、固定六分类头、`torch.load(map_location='cpu', weights_only=True)`、`load_state_dict(strict=True)`、`eval()` 和 `inference_mode()`。没有宽松加载或网络权重兜底。

验证了 `[1,3,224,224]` FP32 输入、三通道完全相同、原生 L/224 PNG 像素不变、`[1,6]` 有限 logits、六概率非负且和约等于 1、置信度与预测索引一致；另测纯灰及棋盘纹理的稳定输出。完整六维参考/实际向量及逐元素阈值结果见 CPU JSON 证据。包内历史验证资料未当作本机真实 ROI 测试结果。

### 性能

每模型预热 3 次、有效计时 20 次，原始分布已保存。完整推理计时为灰度解码/预处理 → CPU forward → softmax → JSON 序列化，不包含排队、数据库、HTTP 或制品写盘。

| 模型 | 构造及严格加载 ms | forward P50 / P95 ms | 完整推理 P50 / P95 ms |
|---|---:|---:|---:|
| EfficientNet-B0 | 312.77 | 32.43 / 47.40 | **34.18 / 51.56** |
| MobileNetV3-Small | 143.68 | 9.61 / 14.87 | **10.70 / 14.57** |

上表模型加载发生在资产全量校验之后。单独的新进程测得完整冻结清单及 13 项载荷校验耗时 **478.17 ms**，命中校验缓存后的文件身份检查 **3.43 ms**，避免把两种成本混在模型加载列中。进程启动/导入耗时未作为上述推理延迟；真实任务总耗时另见 Worker 日志。

Windows 进程 Working Set：EfficientNet 加载前约 280.8 MiB、加载后 317.1 MiB、推理后峰值约 326.6 MiB；MobileNet 加载前约 320.5 MiB、加载后 316.9 MiB、进程历史峰值约 327.1 MiB。第二模型与第一模型在同一基准进程顺序测量，受内存复用影响，**不能将此峰值当作 MobileNet 独立进程的模型占用**。

默认继续使用 EfficientNet-B0；当前 CPU 延迟没有支持更换冻结默认模型的理由。

### 常驻缓存与失效

`infer.pcb_classification.runtime.predict()` 采用每进程单模型缓存。首次调用加载，重复同一模型不再创建网络、不重复 `torch.load`，也不重复计算大权重 SHA。切换模型释放旧缓存引用。

缓存键绑定私有目录、模型、文件身份、准入回执与源码身份。文件 stat 改变会重新完整哈希；配置、清单、权重、回执、源码或运行库/CPU 设置不符时失效关闭。Worker 关闭开关时清除分类缓存。

单元测试验证了身份改变、模型切换、关闭开关及失效后的缓存行为；真实同一 Worker 的第三个任务确认 `cache_hit=true`。缓存防护针对意外更换/过期准入，不宣称抵御恶意操作系统管理员刻意伪造文件身份。

证据：[原包 Smoke](pcb-classification-stage4-20261102/original-smoke.txt)、[部署准入、原始时延、RSS、缓存计数](pcb-classification-stage4-20261102/cpu-admission.json)、[全量哈希与缓存复核耗时](pcb-classification-stage4-20261102/asset-verification-timing.json)。

## 5. 实现路径及安全契约

### API 与任务链

| 功能 | 实际入口 |
|---|---|
| 模型目录 | `GET /api/scenes/pcb/classification/models` |
| 单图上传 | `POST /api/scenes/pcb/classification/uploads`，multipart 只允许一个 `file` |
| 创建任务 | `POST /api/scenes/pcb/classification/tasks`，仅 `batch_id`、`model_id`，支持 `Idempotency-Key` |
| 查询详情 | 复用 `GET /api/tasks/{task_id}` |
| 历史、再跑、提交/撤回 | 复用 `/api/records` 现有接口与权限 |
| 任务类型 / 队列函数 | `pcb_classify` / `apps.worker.jobs.run_pcb_classification` |
| 文件下载 | 复用 `/api/tasks/{task_id}/file/{rel_path}` |

主调用链：

```text
PcbClassifyNewView
 → 登录态 HTTP 客户端
 → pcb_classification router
 → service.create_batch / create_task
 → 原有 lock_user、request_id、existing_task、freeze_inputs
 → Task/TaskModel/TaskSample + AuditLog 落库
 → dispatch.enqueue（确定性 task-{id}，RQ unique）
 → jobs._run_task → pcb_classification.assert_execution / run_body
 → 固定 infer.pcb_classification.predict
 → 私有临时 JSON/PNG → 再次核验授权、开关、资产和冻结输入
 → Artifact + AuditLog + success 原事务提交
 → 授权详情、文件下载、结果记录
```

关键定位：

- `apps/api/app/services/pcb_classification.py:110` `create_batch()`：上传验证、私有存储、原始字节 SHA 和解码事实。
- 同文件 `:150` `snapshot()`：固定数据/模型/协议、样本事实，拒绝钢铁或分割批次混入。
- 同文件 `:180` `create_task()`：门禁、用户/批次锁、模型登记、幂等和投递。
- `apps/api/app/services/input_freeze.py`：扩展独立分类快照；重新验证实际文件字节。
- `apps/worker/pcb_classification.py:22` `assert_execution()`、`:49` `run_body()`：运行前及发布前双重复核，不持有授权锁做 CPU 计算。
- `apps/api/app/services/pcb_delivery.py`：复用轻量失败回调，按精确函数/任务类型分别处理分割及分类；领取前失败不留下永久 queued。
- `apps/api/app/services/task_artifacts.py`：分类专用两项白名单及现有路径封闭检查。
- `apps/api/app/services/models.py`、`datasets.py`、`tasks.py`：防止分类模型/批次进入钢铁分割或通用资源选择路径。

### 输入与产物

上传上限 2 MiB、像素数上限 4096²；检查 PNG/JPEG magic、MIME、扩展名、实际解码、单帧、支持的像素模式及 EXIF 方向。拒绝空文件、损坏文件、过大输入、16 位图、多帧、路径名称和额外 multipart 字段。非原生合法 ROI 按冻结协议适配为 224×224 灰度，保存并展示 `input_adapted`。

原始上传保存于私有 `storage/pcb_classification/{batch_id}/image.{png|jpg}`，保留 SHA、长度、尺寸、格式、模式等事实。任务成功仅登记：

1. `pcb_classification.json`：真实预测、六概率、模型/协议/输入身份与适配事实。
2. `origin/image.png`：**归一尺寸后的灰度输入预览**，不是原始上传字节或检测结果。页面明确标为模型输入预览。

首期不新增原始上传下载接口，不生成 `MetricSet`，不提供图层 bundle、脚本、权重、ZIP、参考向量、`inputs.json` 或服务器日志下载。

学生 A 的任务与 ROI 不向学生 B 开放；导师只能访问明确提交的任务，撤回后拒绝访问。撤回仍遵守既有“导师未读前可撤回”的规则，没有更改共享机制。历史详情/结果不依赖当前启用开关，关闭后仍可按权限读取；新上传、新任务、再跑和执行需重新过门禁。

### 前端

新增 `PcbTabs.vue`、`PcbClassifyNewView.vue`、`PcbClassifyTaskView.vue` 和类型契约，沿用原 PCB 浅色布局。包含真实图片预览、后端目录驱动的模型选择、六类说明、提交/运行/失败状态、服务端轮询、概率条和授权 JSON 下载。

提交失败后保持已上传批次和幂等键；更换图片或模型形成新请求。路由变更/卸载后忽略旧响应并停止轮询。导师提交、撤回、再跑从既有「历史记录」操作入口复用，按服务器 `can_*` 权限显示；没有新增假的取消按钮。

桌面和移动截图：[桌面输入](pcb-classification-stage4-20261102/live-attempt3/desktop-upload.png)、[桌面真实结果](pcb-classification-stage4-20261102/live-attempt3/desktop-result-0.png)、[移动输入](pcb-classification-stage4-20261102/live-attempt3/mobile-upload.png)、[移动结果](pcb-classification-stage4-20261102/live-attempt3/mobile-result.png)。截图使用合成 ROI，不能据此判断真实缺陷准确率。

## 6. 真实基础设施验收

最终运行使用新建、带专用所有权标签、无持久卷的 MySQL 8/Redis 7 容器，随机 loopback 端口和临时存储；真实 FastAPI HTTP、现有 Worker 主入口、RQ/SimpleWorker、Vite 和 Chromium。预置临时用户/session，走真实鉴权，未替换 API 鉴权依赖或使用假队列。

最终运行目录：[live-attempt3](pcb-classification-stage4-20261102/live-attempt3/)。

| 任务 ID | 模型 / 输入 | 结果 |
|---|---|---|
| `b0718b1a-b6ec-518a-8764-0826a062c20e` | EfficientNet-B0 / 原生灰度 PNG | success，未适配，首次加载 |
| `96b17235-0fc1-56ab-ba28-3ab14ea89a42` | MobileNetV3-Small / RGB JPEG，180×150 | success，适配提示成立 |
| `adce1137-d165-514f-9d76-b025e70e79e7` | MobileNetV3-Small / 灰度 PNG | success，同 Worker 缓存命中 |

每个成功任务均核验 MySQL 终态、2 个 Artifact、0 个 MetricSet、1 条完成审计和 RQ finished；浏览器显示值逐项与真实 API 六概率核对，授权 PNG/JSON 可读，历史链接正确。

**71 项真实浏览器断言 + 90 项基础设施/权限断言通过。** 另有 6 个受控失败任务，分别证明开关关闭、创建者禁用、输入字节替换、模型角色变更、推理阶段超时、领取前依赖失败会得到正确失败终态且没有成功 Artifact。

超时与领取前依赖失败是**隔离 RQ 子进程中的明确故障注入**，不是宣称实际计算超过 120 秒，也没有改生产推理代码制造延迟。其余权限、HTTP、数据库、文件替换、入队及 Worker 执行均为真实链路。

覆盖了同键复用任务、同键改模型冲突、跨用户 ROI 复用拒绝、访客/同学/未提交导师下载拒绝、提交后导师可读、撤回立即不可读。另启动独立关闭开关的 API，确认模型目录状态真实、新任务 409、已有授权 JSON 仍可读取。原系统没有统一取消协议，本次没有假造取消能力。

私有文件 HTTP 证据：

- [API 340 次 GET/HEAD 拒绝](pcb-classification-stage4-20261102/live-attempt3/private-api.json)。
- [Vite 340 次 GET/HEAD 拒绝](pcb-classification-stage4-20261102/live-attempt3/private-vite.json)。
- [最终构建预览 320 次分类资产拒绝](pcb-classification-stage4-20261102/build-validated/private-classification-build.json)。
- [最终构建预览 280 次原 PCB 资产拒绝](pcb-classification-stage4-20261102/build-validated/private-get-build.json)。

覆盖原包、sidecar、两权重、配置、清单、包内源码、参考向量、准入回执、部署源码、大小写、编码斜杠/双重编码、`@fs`、路径别名及 query。每次读取有界，不下载完整私有模型，不保存私有响应正文；同时保留公开应用根页面/正常 JS chunk 及授权任务文件的正向对照。

全部本轮自建进程和带精确所有权标签的容器已清理；没有停止日常服务、清空日常 MySQL/Redis 或留下分类验收队列。证据：[真实链路总结](pcb-classification-stage4-20261102/live-attempt3/live-results.json)、[浏览器断言](pcb-classification-stage4-20261102/live-attempt3/browser-results.json)、[Worker 日志](pcb-classification-stage4-20261102/live-attempt3/worker.log)。

## 7. 回归结果、已修复问题及限制

| 检查 | 本次结果 | 证据 |
|---|---|---|
| A/B/C、既有业务及新增分类后端 | **620 passed，3 skipped**，其中新增分类 35 项已计入 620 | [完整回归](pcb-classification-stage4-20261102/regression-complete.txt) |
| 资产路径、篡改、准入、缓存校验 | 36 PASS | [独立准入负例](pcb-classification-stage4-20261102/admission-negative.json) |
| 新分类前端错误/重试/移动布局 | 38 PASS，mock API | [结果](pcb-classification-stage4-20261102/frontend-mock/results.json) |
| 钢铁分类实际 CPU | 1 pytest PASS；有标签/无标签各一次，两图输入 | [CPU 结果](pcb-classification-stage4-20261102/legacy-steel-classification.json) |
| 钢铁分割实际 CPU | 1 pytest PASS；无 GT 对照、有 GT 对照、demo 各一次 | [CPU 结果](pcb-classification-stage4-20261102/legacy-steel-segmentation.json) |
| 原 PCB 分割实际 CPU | 1 pytest PASS；3 模型、CAM、无 GT/有 GT、授权下载 | [CPU 结果](pcb-classification-stage4-20261102/legacy-pcb-segmentation.json) |
| 原 PCB 分割 UI | 182 PASS，mock API | [日志](pcb-classification-stage4-20261102/legacy-pcb-frontend.txt) |
| 原钢铁分类 UI | 52 PASS，mock API | [日志](pcb-classification-stage4-20261102/legacy-classification-frontend.txt) |
| 首页/工作台等浅色页面回归 | 156 PASS，mock API | [日志](pcb-classification-stage4-20261102/legacy-light-frontend.txt) |
| 原阶段 C 前端 | 22 行为断言 + 5 SFC/TS 语法检查 PASS | [日志](pcb-classification-stage4-20261102/legacy-phase-c-frontend.txt) |
| 最终前端生产构建 | PASS；新增分类页面 chunk 存在，递归扫描无私有模型/源码 | [构建证据](pcb-classification-stage4-20261102/build-validated/build.json) |
| `git diff --check` | PASS；仅 Windows LF/CRLF 提示 | 命令退出码 0 |

旧模型 CPU 回归使用临时 SQLite、假队列和受控鉴权夹具，实际执行模型；它们**不是**再次进行真实 MySQL/RQ 验收。钢铁分割测试采用既有固定哈希、`weights_only=True` 的测试读取封装，未借本次任务更改原生产权重加载方式。

本轮实际发现并修复：

1. Pillow PNG 的 `verify()` 必须在 `open()` 后直接调用；初版在 EXIF 读取后验证会失败。现改为先验证，再重新打开进行元信息检查/解码，原生像素与适配测试均通过。
2. 结果页初版复用了将 JSON 视为错误响应的通用二进制下载工具，真实浏览器暴露出下载失败。已沿用原分割页的受控 JSON 下载方式，重新通过真实下载与权限撤销提示检查。
3. 验收脚本修正了 Windows 超长 pytest 参数名、旧场景断言缺少新增分类项，以及 Vite 临时端口和源码路径变体构造问题。没有通过放宽权限或模型精度阈值取得 PASS。

限制与明确未运行项：

- 3 个符号链接测试因当前 Windows 账户不能创建测试符号链接而 **SKIPPED**；路径封闭的其他回归通过，不能宣称这 3 项已实测。
- 完整 `vue-tsc` 为 **NOT_RUN**，现有环境未安装该工具；未因此联网安装依赖。已运行 Vite 生产构建、浏览器及相关 SFC/TS 语法检查。
- 构建存在已有大 chunk 提示；后端有 Starlette/httpx、anyio 弃用提示。本轮未为了升级依赖重写架构。
- 未进行真实 PCB ROI 数据集评测、全量 Test、训练或生产容量/长时间压力测试。合成输入、人工 GT 和页面概率不能说明新模型在现场整板图上的准确率。
- 不支持取消任务；模型/源码/运行库变化后需重新准入并重启 API/Worker。不要手工修改准入回执的 PASS 字段。

## 8. 文件变更范围

**新增业务模块**：

- `packages/infer/pcb_classification/{__init__.py,catalog.py,images.py,runtime.py,PROVENANCE.md}`：固定来源、协议校验、图像约束、安全 CPU 推理及缓存。
- `apps/api/app/routers/pcb_classification.py`、`services/pcb_classification.py`：受控单 ROI API 与既有任务系统适配。
- `apps/worker/pcb_classification.py`：执行与发布前复核、暂存制品、终态和审计。
- `apps/web/src/views/pcb/PcbClassifyNewView.vue`、`PcbClassifyTaskView.vue`、`PcbTabs.vue`、`classification-types.ts`：分类工作台、结果及页面内切换。
- `scripts/verify_pcb_classification_assets.py`、`admit_pcb_classification_cpu.py`：资产与 Windows CPU 准入。
- 新增分类后端、准入负例、mock 前端、真实浏览器/基础设施测试及私有路径清单，详见变更 JSON。

**修改既有接入点**：配置和路由注册；Task 序列化、权限/记录及再跑分流；输入冻结；场景目录；通用模型/数据集隔离；Artifact 白名单；Worker 分发和轻量失败回调；前端路由、任务路径、记录筛选及原 PCB 页内切换；Git/Vite 私有资产排除；测试运行器和场景期望。

原 `check_pcb_cpu_flow.py` 新增 `--report`，避免覆盖此前 PCB 证据；原构建/私有文件探针增加分类选项，默认旧分割验证仍保留。没有重写原分割执行器。

## 9. 统一终验表

| ID | 结论 | 对应证据 |
|---|---|---|
| S4-01 仓库/环境盘点与保护 | PASS | `preservation.json`、`baseline-files.json`、Git 前后状态 |
| S4-02 原 ZIP/sidecar/14 文件安全准入 | PASS | `asset-audit.json`、最终固定 SHA |
| S4-03 双模型 Windows 严格加载及参考一致 | PASS | `original-smoke.txt`、`cpu-admission.json` |
| S4-04 CPU 性能/内存/缓存/默认选择 | PASS | `cpu-admission.json`、`asset-verification-timing.json`、真实第三任务缓存命中 |
| S4-05 独立任务/API/Worker/Artifact | PASS | 新业务模块、`regression-complete.txt`、`live-attempt3/live-results.json` |
| S4-06 前端输入/结果/状态/历史 | PASS | mock 38 项、真实 71 项及桌面/移动截图 |
| S4-07 真实隔离基础设施双模型闭环 | PASS | `live-attempt3/live-results.json`、Worker 日志 |
| S4-08 权限/私有资产/门禁 | PASS | 90 项真实检查、API/Vite 各 340 次拒绝、准入负例 |
| S4-09 旧业务、A/B/C、构建回归 | PASS，保留上述 SKIPPED/NOT_RUN 限制 | 620 passed；3 条旧模型 CPU 回归；原 UI/构建证据 |
| S4-10 报告/证据/边界/未自动上线提交 | PASS | 本报告、保护清单、默认关闭配置、清理记录 |

所有强制阻断项 S4-02、03、05、07、08 通过。整体 PASS 表示本机代码及准入/隔离集成验收完成，**不表示已经启用日常站点或获得真实数据泛化性能结论**。

## 10. 后续手动启用、复验与回退

### 手动启用开发站点

已有私有资产和回执在本机就绪。先在仓库根验证当前源码/运行环境仍与回执一致（不读取 `.env`）：

```powershell
Set-Location 'F:\360MoveData\Users\40336\Desktop\Bofang\Steel_lab'
.\.venv\Scripts\python.exe -B -c "import sys; sys.path.insert(0,'packages'); from pathlib import Path; from infer.pcb_classification.catalog import admitted; admitted(Path('assets/pcb_classification/deeppcb_roi_v0_formal_v1')); print('PCB classification admission: PASS')"
```

若上述失败，先检查源码、依赖或资产是否变化，不要手动改回执。准入脚本默认拒绝覆盖已有回执；只有管理员确认重新准入时，先保存旧回执，再运行脚本生成新证据。

确认日常 MySQL/Redis 已按原方式健康运行。在 **API 与 Worker 各自启动的 PowerShell 窗口**设置同一个进程环境开关，然后启动/重启对应服务；不需要写入 `.env`：

```powershell
$env:PCB_CLASSIFICATION_ENABLED = 'true'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000 --reload
```

```powershell
$env:PCB_CLASSIFICATION_ENABLED = 'true'
.\.venv\Scripts\python.exe -m apps.worker
```

前端若尚未运行，在 `apps\web` 启动：

```powershell
npm run dev -- --host 127.0.0.1 --port 5173
```

不要重复占用已有端口；已运行的 API/Worker 必须使用本次代码和相同开关后重新启动。登录后进入 `/inspect/pcb/classification`，检查目录的 `enabled=true`、`available=true`、默认 `efficientnet_b0`，再提交一张已裁剪 ROI。两模型未同时准入时不会开放提交。

### 复验入口

在新的证据目录运行，避免覆盖本报告引用的数据：

```powershell
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -B -c "import platform,runpy; platform.uname(); runpy.run_path('tests/run_phase_a_tests.py',run_name='__main__')"
.\.venv\Scripts\python.exe -B tests/check_pcb_classification_admission.py --report <新的证据目录>/admission-negative.json
.\.venv\Scripts\python.exe -B tests/check_pcb_classification_live.py --output <新的真实链路证据目录>
node tests/check_pcb_classification_frontend.mjs 'C:/Users/40336/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright' <新的前端证据目录>
node tests/check_pcb_build.mjs <新的构建证据目录> --classification
```

尖括号为待替换参数，不是可直接粘贴的 PowerShell 路径。真实链路脚本需要 Docker 正常、缓存中的 `mysql:8.0`/`redis:7-alpine` 及现有 Playwright；不会下载镜像或模型。旧 CPU 回归均可指定 `--report` 保存到新位置。

回退只需在 API/Worker 进程设置 `PCB_CLASSIFICATION_ENABLED=false` 并重启，保留历史及私有数据。不要删除共享数据库表、已有任务、旧分割资产或用户未提交代码。

本轮至此停止。没有修改 `.env`、迁移真实数据库、运行训练、访问远程 Milvus/模型 API、提交 Git 或推送远程。
