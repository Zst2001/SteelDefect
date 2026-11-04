# PCB 分割：批量多模型、多尺寸与上传交互扩展验收报告

日期：2026-11-03。总状态：**PASS（本报告所列范围）**。

本次依据 `E:\huancun\edgehuancun\PCB缺陷分割工作台扩展.md`，在真实 Windows 仓库完成增量实现、定向修复、隔离回归和真实 CPU/browser 验收。没有训练、替换权重、下载数据、修改 `.env`、迁移日常数据库、提交或推送 Git，也没有自动部署日常站点。测试使用合成图像，本文不报告真实缺陷检测精度。

- 仓库：`F:\360MoveData\Users\40336\Desktop\Bofang\Steel_lab`。
- 分支：`main`；初末 HEAD 均为 `6d3ecb090ae9f7f3d84b33375ca1dec8b2e8d13a`。
- 唯一证据根目录：`F:\360MoveData\Users\40336\Desktop\Bofang\Steel_lab\docs\report\pcb-batch-extension-20261103`。下面证据链接均指向此次目录。
- 环境：Windows 11，Intel Core i7-9750H（6 核 / 12 线程），Python 3.13.13，PyTorch 2.14.0+cpu，torchvision 0.29.0+cpu，NumPy 2.5.3，Pillow 12.3.0，OpenCV 5.0.0.93，Node 24.14.0。沿用既有 `.venv` 与前端依赖，没有安装或升级依赖。
- 本次修改 14 个已跟踪文件，新增 10 个代码/测试文件；另新增本报告及证据。341 个基线文件中 327 个哈希不变，14 个为本次修改，无丢失文件。初始未跟踪的 `docs/prompt/`、历史报告、`ppt/` 等用户文件保留。没有暂存操作。

## 1. 完成的功能

PCB 分割工作台现在支持一次选择或拖入最多 10 张图像，追加、去重、预览和删除；上传虚线框整区及键盘均能打开原生多选窗口，原重复小按钮已移除。三个准入模型改为复选，默认只选 U-Net，可全选、清空；页面明确显示图片数、模型数、子任务数、窗口总预算。

GT 和 CAM 选项固定可见。GT 使用稳定的内部图片 ID 关联，支持严格同名、`_mask`、`_gt` 自动配对和人工指定；重复名称、竞争候选、尺寸不一致不会猜测通过。未配对的已选 GT 有明确提示。一部分图片有 GT、另一部分没有 GT 可以共同提交。

提交产生持久批次和独立的“图片 × 模型”子任务，CPU Worker 仍串行执行。新增批次页按图片展开模型卡片，展示状态、图层与该图片的指标；失败项单独再跑，旧任务与其他成功结果保留。刷新、历史回访、授权下载和移动端布局已验证。原尺寸图层仅在展开后加载，没有伪造进度百分比和未实现的取消按钮。

### 页面证据

- [最终真实桌面工作台](pcb-batch-extension-20261103/live-final/batch-desktop-form.png)
- [最终真实桌面批次结果](pcb-batch-extension-20261103/live-final/batch-desktop-results.png)
- [最终真实移动端工作台](pcb-batch-extension-20261103/live-final/batch-mobile-form.png)
- [最终真实移动端结果，已滚动验证懒加载](pcb-batch-extension-20261103/live-final/batch-mobile-results.png)
- [48 项交互 mock 验收](pcb-batch-extension-20261103/frontend/run-05/results.json)

截图中的图像是合成测试输入；mock 截图中的模型参数等属于明确标注的测试夹具，不是实际资产数据。

## 2. API、持久化与调用关系

### 2.1 原单图接口保持兼容

| 接口 | 本次行为 |
|---|---|
| `GET /api/scenes/pcb/segmentation/models` | 保留原模型目录，额外提供服务端统一限制 |
| `POST /api/scenes/pcb/segmentation/uploads` | 原单张 `file`、可选 `gt`；原 RGB 220×220 与原文件上限不变 |
| `POST /api/scenes/pcb/segmentation/tasks` | 原单 `model_id` 契约；不能借此绕过新扩展输入的预算或 CAM 确认 |
| `GET /api/tasks/{task_id}` | 原详情，增加父批次和实际尺寸等兼容字段 |
| `GET /api/tasks/{task_id}/file/{rel_path}` | 继续使用原 Artifact 权限与白名单 |
| `POST /api/records/{task_id}/rerun` | 扩展输入仍可建立新的独立 PCB 分割任务；旧结果不覆盖 |

### 2.2 新批量接口

`POST /api/scenes/pcb/segmentation/uploads/batch` 使用 multipart；文本字段 `manifest` 是如下 JSON，各文件字段名称由 manifest 显式关联，不依赖上传顺序：

```json
{"files":[
  {"client_file_id":"image_a","file_field":"original_a","gt_field":"gt_a"},
  {"client_file_id":"image_b","file_field":"original_b"}
]}
```

`original_a`、`original_b` 为原图文件字段；`gt_a` 为唯一配对 GT。缺失、重复、额外字段或重复 ID 均拒绝。先验证整批，再持久化；磁盘部分写入失败也会回滚数据库并移除本次新建独占目录中的残片。

`POST /api/scenes/pcb/segmentation/tasks/batch` 要求 `Idempotency-Key`，请求示例：

```json
{"batch_id":"服务端返回的父批次ID",
 "model_ids":["unet","unet_resnet18","unetpp_resnet18"],
 "include_cam":true,"accept_unsupported_cam":true}
```

`GET /api/scenes/pcb/segmentation/batches/{batch_id}?page=1&page_size=50` 返回：

```text
batch_id, status, counts{total,success,failed,queued,running},
samples[{sample_id,client_file_id,filename,width,height,has_gt,
         input_plan,windows,tasks[既有单任务详情]}],
image_count, selected_model_ids, include_cam, total_windows,
pagination{page,page_size,total,has_more}, open_path
```

分页上限 100；`counts` 和 `pagination.total` 是全部获授权任务的统计，`samples`、`image_count`、`selected_model_ids`、`total_windows` 是**当前页可见项汇总**，不能当成全批全局值。前端使用全局 counts 展示进度。

### 2.3 选择的持久化方案

原 PCB 快照、Artifact 和文件命名假设一个版本只有一个 `sample_key=image`。为复用这一已验收边界，本次使用一个私有 Dataset、一个父 `DatasetVersion(kind=pcb_batch)`，其元信息持久保存子版本与 Sample ID；每张图片使用独立子版本和一个 Sample。各模型为该图片建立独立 Task / TaskModel / TaskSample。没有新增表或数据库迁移。

核心调用链：

```text
PcbNewView → uploads/batch → pcb_batch.create_group
           → tasks/batch → pcb_batch.submit_group
           → create_pcb_task（内部允许扩展，延迟逐任务投递）
           → 已有 dispatch/RQ → apps.worker.jobs.run_pcb_segmentation
           → run_pcb_body → 原 compute 或 compute_adapted/tiling
           → 原子发布 Artifact + 有GT时 MetricSet + 完成审计
PcbBatchView → batches/{id} → get_group → 授权范围内的单任务详情
```

### 2.4 幂等、失败与权限

- 幂等绑定用户、父批次、子图片、模型与 CAM 选项。AuditLog marker 使用加锁当前读，避免 MySQL REPEATABLE READ 的旧快照；同键不同参数返回冲突，前端对不同参数保留独立键。
- 批次先持久化全部子任务，再逐一投递。未尝试项保留明确 `QUEUE_NOT_SENT` 失败状态；确定拒绝为 `QUEUE_REJECTED`；成功项不被其他失败抹掉。未知投递遵守原 `QUEUE_UNKNOWN` 纪律，不自动再发。
- Worker 领取前、读入时、发布前复核权限、功能开关、原文件/GT 字节、模型准入及适配器身份。任务冻结原尺寸、源模式、文件大小/SHA、GT、窗口位置和融合规则、模型及选项。
- 所有者可见本人批次；其他学生不可见。导师只看到已提交子任务及其匹配图片、统计；单项授权不泄露同批其他图片/模型。撤回后批次和文件立即不可见。访客被拒绝。
- 上传文件名只用于显示，实际存储使用服务端 ID 与固定文件名；下载仍经过 TaskArtifacts，内部快照、模型文件、非白名单路径不能下载。
- 功能关闭后禁止创建/执行，已成功历史仍按原权限可读。新增适配器代码改变时，旧扩展输入会 fail closed，须重新上传，不静默换协议；旧原生单图历史不受新适配器身份影响。

## 3. 多尺寸推理、GT 和 CAM 纪律

### 3.1 原生与适配路径

新增 `packages/infer/pcb/tiling.py`，放在冻结模型调用外侧。原 `models.py`、`preprocess.py`、`postprocess.py`、`visualize.py`、`runtime.py`、`catalog.py` 未变。

| 输入 | 行为 | CAM |
|---|---|---|
| 原生 RGB 220×220 | 直接调用原 compute / pad18→256→forward→crop220→softmax | 默认关闭；打开时仍为原 CAM |
| 小图 | 右侧/下侧常量黑填充，输出裁回原尺寸 | 明确不支持 |
| 较大或非正方形 | 原始像素滑窗，不整体 resize；短边必要时先填充 | 明确不支持 |
| 8-bit 灰度 | 显式复制为三通道，记录 gray_to_rgb；220 灰度也属于适配输入 | 明确不支持 |
| RGBA、16-bit、CMYK、多帧、异常 EXIF、损坏文件 | 明确拒绝 | 不执行 |

固定窗口 220，步长 176，名义重叠 44，最后一窗贴齐末端，因此末窗重叠可大于 44。逐窗沿用原 pad/crop；融合两类 softmax 概率，使用每轴最小值 0.05 的正余弦权重，二维最小权重约 0.0025。覆盖归一化后才 argmax，不拼接已离散 mask。输出掩码 0/1，所有图层严格回到原 W×H。

GT 只接受同尺寸二值灰度 PNG（0/1 或 0/255），无损规范化成 0/1；不参与前向、不插值。不带 GT 的任务没有 MetricSet，也没有假的 Dice/IoU。带 GT 的任务逐图逐模型计算，真实验收额外从下载的预测与 GT 像素重算 TP/FP/FN/TN，与接口一致。

混合尺寸请求 CAM 时必须明确确认；不支持的任务记录 `not_supported_for_size`，普通概率热力图仍可用。概率热力图从未冒充 CAM。原生 CAM 无前景或执行异常仍沿用原明确状态与失败策略。

### 3.2 统一限制

| 限制 | 值 |
|---|---:|
| 每批原图 | 1–10 张 |
| 单文件（原图或 GT） | ≤10 MiB |
| 每批原图和 GT 合计 | ≤50 MiB |
| 最长边 | ≤2048 |
| 像素数 | ≤2048²，且宽高非零 |
| 总工作量 | Σ每图窗口数 × 选定模型数 ≤500 |
| multipart 传输上限 | 文件预算 +1 MiB 协议开销，实际流计数，不能靠伪造 Content-Length 绕过 |

限制定义来自 `tiling.limits()` 并由目录 API 传给前端；服务端仍独立校验。2048² 单图 144 窗，三个模型 432 次在预算内；两张同尺寸选三模型 864 次会在提交前拒绝。没有扩大既有 120 秒 PCB 子任务超时。

### 3.3 原生数值回归和资产身份

三个模型的新旧原生 220 路径对 logits、mask、probability、overlay、boundary、probability_heatmap **逐位相等**。对冻结 `reference_vectors/input_220_rgb.npy` 及各模型 `*_logits.npy`，沿用原 FP32 容差 `1e-3 + 1e-4 × abs(reference)`，三个模型 mask 不同像素均为 0；最大绝对 logit 差约为 U-Net 7.39e-6、ResNet18-U-Net 1.80e-5、ResNet18-U-Net++ 1.63e-5。没有放宽容差。

冻结六个部署源文件及准入回执前后哈希相同；严格加载仍 `strict=True`、`weights_only=True`。新增外侧适配器不属于旧回执绑定源码，使用独立 SHA 绑定新任务；因此未重写回执，也不需要为未改变的原模型伪造再准入。适配器身份：`d9a20c4f34b12d226f86cca258b21488f3cdda2f760141c22e232dad5c3535e7`。

原交付 ZIP 的 SHA256 为 `7c93a1f299f7e2b998ee1c8473ce9f3b6b700487247d4c069a69ec0240549c1d`，与原 `.zip.sha256` 一致。

证据：[原生/21 次 CPU 回归](pcb-batch-extension-20261103/tiling/cpu-run-01/cpu.json)、[边界与 Git 核验](pcb-batch-extension-20261103/boundary-audit.json)。

## 4. Windows CPU 实测

三模型分别覆盖 110×110、220×220、221×300、512×384、1024×1024、2048×220、2048×2048，共 **21 次**。对应窗口数为 1、1、4、6、36、12、144。输出尺寸、有限概率、概率归一化、正覆盖、末窗边界均通过。使用 torch 2 个 intra-op 线程、6 个 inter-op 线程，MKLDNN 开启。

以下是**每个组合单次测量的驻留模型适配器耗时**；不含 HTTP、排队、解码、保存，不是 P50/P95，也不是整站性能承诺。RSS 是进程采样峰值，不是硬件峰值测量。

| 模型 | 输入 W×H | 窗口数 | 单次耗时（秒） | 进程采样峰值 RSS（MiB） |
|---|---|---:|---:|---:|
| unet | 512×384 | 6 | 1.994 | 465.7 |
| unet | 1024×1024 | 36 | 10.699 | 502.5 |
| unet | 2048×2048 | 144 | 44.221 | 731.6 |
| unet_resnet18 | 512×384 | 6 | 1.031 | 483.9 |
| unet_resnet18 | 1024×1024 | 36 | 6.487 | 552.9 |
| unet_resnet18 | 2048×2048 | 144 | 26.599 | 801.7 |
| unetpp_resnet18 | 512×384 | 6 | 2.572 | 540.7 |
| unetpp_resnet18 | 1024×1024 | 36 | 15.809 | 620.3 |
| unetpp_resnet18 | 2048×2048 | 144 | 56.648 | 906.4 |

独立模型加载记录：U-Net 9.576 秒（包含首次初始化/冷盘影响），ResNet18-U-Net 0.511 秒，ResNet18-U-Net++ 0.457 秒。最慢边界尺寸的加载加推理约 57.105 秒，实测给 120 秒子任务上限留有余量；不保证在任意主机负载下都不超时。真实链路成功验证为 220 与 512×384；2048² 的 HTTP/RQ 全流程本次未单独跑，最大尺寸证据是实际 CPU 适配器。无需为整批提高单任务超时。

另补充三模型 × 512×384 的纯背景/稀疏细线，共 **6 次**真实权重检查。纯背景均无前景；稀疏细线仍有模型相关断裂、漏检、扩张，不承诺细缺陷识别质量。逐层原尺寸图及原始概率保存在 [visual-cases-01](pcb-batch-extension-20261103/tiling/visual-cases-01/visual.json)。可视检查未见贯穿整幅的拼接空白条，末行末列保留，覆盖权重最小约 0.00250000018。这组与其他功能验收可能并行，耗时不作性能基准。

## 5. 真实批量闭环与安全验收

最终证据：[live-final/live-results.json](pcb-batch-extension-20261103/live-final/live-results.json)、[browser-results.json](pcb-batch-extension-20261103/live-final/browser-results.json)。**178 项独立 HTTP/DB/RQ/文件断言通过，80 项真实浏览器断言通过，清理 PASS。**

环境为临时 MySQL 8 / Redis 7 容器、随机回环端口、tmpfs 存储、真实 Windows CPU Worker、真实 Vite/browser。配置只从测试初始化参数读取；审计钩子禁止 `.env` 与外部服务访问。测试会话不保存、不输出。使用缓存镜像 `--pull=never`，临时资源按准确 PID / 容器 ID 和独占 label 清理。

父批次与六个任务如下，均为最终验收新建的合成测试任务，临时数据库清理后不能在日常站点查询：

父批次：`0af675f6-9939-4b6e-8e25-8fa56803e2f4`。

| 子任务 ID | 模型 | 原图尺寸 | GT/MetricSet | CAM | 状态 |
|---|---|---|---|---|---|
| `0d98b325-4210-5b17-9f0b-4182d6922dd4` | unetpp_resnet18 | 220×220 | 有/1条 | ok | success |
| `99cb1679-e833-5de1-9e68-af6a423ea284` | unet_resnet18 | 220×220 | 有/1条 | ok | success |
| `f506eb97-06f2-5d8a-ba6d-d8a1871a0357` | unet | 220×220 | 有/1条 | ok | success |
| `81667fd0-db9c-5e5b-8411-05c081a6efa3` | unetpp_resnet18 | 512×384 | 无/0条 | not_supported_for_size | success |
| `b1e335fb-c703-5c77-9f75-b88bdf8112ec` | unet | 512×384 | 无/0条 | not_supported_for_size | success |
| `e52b25cf-7f59-5d95-b972-a06011908296` | unet_resnet18 | 512×384 | 无/0条 | not_supported_for_size | success |

每项检查了一个 TaskModel、唯一完成审计、RQ finished、原尺寸图层，以及有 GT 时恰好一条 MetricSet、无 GT 时零条。原图下载与实际上传像素一致。原生三模型 CAM 均为 ok；大图三模型均明确不支持 CAM。独立详情、历史、刷新、下载、桌面/移动端滚动懒加载实际经过浏览器。

已验证的授权输出为 origin、pred_mask（0/1）、mask_visual（显示用0/255）、overlay、boundary、probability，条件存在的 gt/error/cam，以及既有结果 JSON `pcb.json`。内部 inputs/task 快照、模型权重和任意路径不在下载白名单。

同批权限检查：访客 401，其他学生/未提交导师 404；只提交一个子任务后导师仅见该项及对应图片；撤回后批次和原图立即 404。分页 page_size=1/2/50 正确限制可见数量。

额外使用真实重叠 HTTP 请求对同一幂等键同时提交三个模型，两个响应返回完全相同的三个 ID，Redis 队列恰好各入队一次，随后三项 CPU 执行成功：

父批次：`78e2aba6-87bc-4926-ab3c-34ed1d6194e8`。

- `1d24bb2e-ea32-5333-bf4d-bb3efd49ec41`
- `ac999fb0-54a3-59ed-acfe-5f46ecf652f8`
- `d4133147-300c-5db4-af2a-b0ccdf0aefe4`

此额外验证先停止独占空闲 Worker，以观察准确队列数量，再使用既有、唯一名称的 SimpleWorker burst 模式消费此隔离队列。未清空任何 Redis key 或队列。

10 图 ×3 模型的 30 个任务、选项冲突、部分投递拒绝/未知、个别失败保留兄弟结果、单项再跑、发布前/排队时撤权及换字节，由隔离数据库单元/链路测试覆盖，**没有冒称真实跑过 30 个大模型任务**。

## 6. 测试清单及结果

测试数量按各自脚本口径列出，存在重合覆盖，不把断言数与 pytest 用例数相加宣传。

| 验证 | 结果 | 隔离与证据 |
|---|---|---|
| 全部已审计离线套件 | **683 passed，3 skipped，23 subtests passed，2 warnings** | [offline-regression-final.txt](pcb-batch-extension-20261103/offline-regression-final.txt)，225.43 秒；SQLite、临时文件、fake queue，禁止服务/网络 |
| 新 batch 后端 | 51 passed（已计入683） | [backend-unit-cleanup-final.log](pcb-batch-extension-20261103/backend-unit-cleanup-final.log) |
| 滑窗单元 | 9 passed（已计入683） | [tiling/unit.log](pcb-batch-extension-20261103/tiling/unit.log) |
| 新批次前端 mock | 48 项通过 | [frontend/run-05/results.json](pcb-batch-extension-20261103/frontend/run-05/results.json) |
| 旧 PCB 单任务详情/历史 mock | 141 项通过 | [frontend/legacy-run-01/results.json](pcb-batch-extension-20261103/frontend/legacy-run-01/results.json) |
| 原 PCB closeout 实链 | 232 项浏览器 +60 项独立核验通过 | [frontend/closeout-live-01/results.json](pcb-batch-extension-20261103/frontend/closeout-live-01/results.json)，PNG+GT/JPEG-noGT 两条 U-Net CPU |
| 原 PCB 三模型实链脚本 | 103 项通过 | [frontend/legacy-live-01/results.json](pcb-batch-extension-20261103/frontend/legacy-live-01/results.json)，三模型真实 CPU/CAM |
| 新批量最终实链 | 178 项+80 项通过 | live-final，6 主任务+3 并发任务 |
| PCB ROI 六分类实链 | 153 项后端 +86 项浏览器通过 | [pcb-classification-live/live-results.json](pcb-batch-extension-20261103/pcb-classification-live/live-results.json)，3 CPU任务及真实再跑/重复投递、6负例；680次私有访问拒绝 |
| PCB 分类 UI mock | 38+33 项通过 | pcb-classification-ui 与 pcb-classification-ui-review 的 results.json |
| 钢铁分类 UI mock | 52 项通过 | steel-classification-ui/results.json |
| 阶段 C 前端定向检查 | 22 项逻辑断言 +5 个 SFC/TS 语法检查通过 | phase-c-ui.log |
| 钢铁分割 CPU 旧链路 | 1 passed，compare有/无GT与demo三流程通过 | legacy/steel-cpu.json；临时SQLite/fake queue，真实可信CPU |
| 钢铁分类 CPU 旧链路 | 1 passed，有/无标签流程通过 | legacy/steel-classification-cpu.json；临时SQLite/fake queue |
| PCB 原单图 CPU 旧链路 | 1 passed，三模型旧上传/任务/图层/CAM | legacy/pcb-legacy-cpu.json；临时SQLite/fake queue |
| 生产前端构建 | PASS，私有资产未打包 | [build/build.json](pcb-batch-extension-20261103/build/build.json) |
| Vite preview 私有访问 | PCB 320 +分类320 次 GET/HEAD 拒绝通过 | build/private-get-build.json、private-classification-build.json |
| Vite dev / API 私有访问 | 每个 surface 320 次通过 | frontend/closeout-live-01/private-get-vite.json、private-get-api.json |
| Git/脚本语法 | diff --check 通过，新增/迁移JS语法通过 | 仅既有换行转换提示 |

完整离线套件包括阶段 A 权限、Artifact、阶段 C 可靠性/修复/验收、钢铁分类、PCB 两功能、原分割任务/指标政策、场景空入口、科研助手/适配助手的已审计子集。没有据此声称执行所有远程 RAG 测试。

### 跳过、限制与失败尝试

- **SKIPPED：3 项 Windows 符号链接测试**，主机不允许创建测试 symlink；未提升权限。其余普通路径/遍历/Artifact 拒绝用例已运行，不能把这三项记为通过。
- **NOT_RUN：完整 vue-tsc 类型检查**。仓库依赖无 vue-tsc，本次未安装；Vite 编译、已列SFC/TS语法、浏览器运行通过不等同于完整类型检查。
- NOT_RUN：正式 MeiweiPCB/NEU-20 精度评测、训练、生产数据/用户图像测试、远程 Milvus、外部模型 API、GPU、整批30项大模型CPU、2048²真实HTTP/RQ全链、长时间压测。这些不属于本轮已声称证据。
- 最终离线有两个既有 Starlette/httpx、AnyIO 弃用警告；Vite 有大 chunk 警告，未为本任务重写全站打包架构。
- 早期 mock 失败为英文弹窗关闭按钮/隐藏 Element checkbox 的测试选择器，已修正；纵向缩略图约束不足已局部修复，最终截图与回归通过。
- live-attempt1：六项成功，但末尾把原站 Google Fonts 请求误当外部业务调用。最终仍阻断所有外网，只将既有字体尝试单独记录；没有放行模型API/数据请求。
- live-attempt2：六项、权限和并发只入队一次均完成，但脚本强停后重启同名 `lab-worker`，RQ 残留注册导致消费阶段失败。使用独占唯一名称 burst runner 后 attempt3 完整通过；没有修改生产 Worker、清库或删除队列。异常证据保留。
- live-final 在 attempt3 通过后补强移动端逐图滚动/decode检查，避免全页截图保留尚未进入视口的懒加载占位。最终80项浏览器与178项后端全部通过。此前证据不覆盖、不伪装成成功。

## 7. 变更清单与保护范围

### 产品代码

| 文件 | 修改目的 |
|---|---|
| `apps/api/app/routers/pcb_segmentation.py` | 新增三个批量端点，严格请求及流上限 |
| `apps/api/app/services/pcb_batch.py`（新增） | 整批校验/保存、父子关系、幂等、逐项投递、授权分页聚合 |
| `apps/api/app/services/pcb_segmentation.py` | 扩展输入快照、目录限制、兼容序列化，旧端点防绕过 |
| `apps/api/app/services/records.py` | 仅 PCB 分割再跑分支内部允许扩展输入 |
| `apps/worker/pcb_segmentation.py` | 原生与滑窗分派、输入计划复核、原尺寸GT/图层/发布 |
| `packages/infer/pcb/tiling.py`（新增） | 有限尺寸/窗口计划、正概率融合、尺寸还原及源码身份 |
| `apps/web/src/views/pcb/PcbNewView.vue` | 多图、多模型、明显GT/CAM、预算与提交身份 |
| `apps/web/src/views/pcb/PcbBatchView.vue`（新增） | 批次聚合、按图比较、懒加载、单项再跑 |
| `apps/web/src/views/pcb/PcbTaskView.vue` | 实际尺寸与父批次入口，保留旧详情 |
| `apps/web/src/views/pcb/types.ts` | 新增batch/plan与可选兼容字段 |
| `apps/web/src/router/index.ts` | 新增批次结果路由 |
| `apps/web/pcb-private-assets.ts` | 将 PCB 分割部署源码也纳入 Vite 私有路径拒绝 |

### 测试代码

新增 `test_pcb_batch.py`、`test_pcb_tiling.py`、`check_pcb_tiling_cpu.py`、`check_pcb_tiling_visual.py`、`check_pcb_batch_frontend.mjs`、`check_pcb_batch_browser.mjs`、`check_pcb_batch_live.py`。

修改 `run_phase_a_tests.py` 纳入新用例；`pcb_private_get_probe.mjs` 增加 runtime/tiling 源码探针；`check_pcb_frontend.mjs` 保留旧详情/历史部分，旧上传测试由新48项替代；`check_pcb_live_frontend.mjs`、`check_pcb_closeout_frontend.mjs` 迁移新上传交互并实际重跑成功。原单图 API 本身仍由后端与旧 CPU 链路独立验证。

明确未改：数据库模型/迁移、应用配置、Worker入口、首页/hero、侧栏、原金相token、钢铁两功能、PCB六分类产品代码/资产、光伏、学生Docker插件、科研助手与学术RAG。原模型ID、默认U-Net、权重、ZIP、参考向量、准入回执未改变。保护证据见 boundary-audit.json；.env 没有读取内容或修改，没有凭测试隔离结果声称日常数据库做过验收。

## 8. 仍需知道的使用边界

1. 大图支持是受限部署适配，不意味着整板图细小缺陷识别质量已达到实验水平；正式质量判断需要负责人另行组织真实标注数据实验，本轮没有替代该工作。
2. `QUEUE_UNKNOWN` 或进程在投递临界点中断留下 `QUEUE_PENDING` 时，继续遵守既有人工核验纪律，不自动补发以避免重复推理。未知项明确显示消息；未投递的兄弟任务可独立再跑。没有新增通用事务outbox/定时恢复器，也不宣称任意断电下自动恢复。
3. 批次只聚合当前有效授权项，分页的图片/模型汇总是页内值。一次提交最多30项；长期多次重跑可通过分页继续查看。
4. 新适配器源码身份改变会让此前未执行扩展输入拒绝继续使用；需重新上传，不应编辑快照/回执绕过。已经成功的结果按原权限读取。
5. 日常 Worker 仍用既有固定名称；非正常强停后立即重启可能等待旧 RQ 注册失效。这是原启动行为，测试已规避但本轮未扩大到通用运维改造，不得因此清空用户队列。

## 9. 日常开发站点手动启用/关闭

**本轮未自动上线。** 为避免 `uvicorn --reload` 在实现途中加载未完成代码，确认原开发 Worker 空闲后，仅停止了先前本对话启动的 API/Worker/Vite 进程树；MySQL/Redis与用户其他容器保留。验收临时服务现已全部清理，日常 8000/5173 未自动重新监听。

该扩展沿用 `PCB_SEGMENTATION_ENABLED`，没有新增第二个开关；PCB分类开关互不干预。以下仅是负责人后续手动操作说明，本轮未执行：

1. 确认已有 PCB 分割准入资产有效；检查/按需手动设置 `PCB_SEGMENTATION_ENABLED=true`，不要改权重或回执。
2. 在仓库根用现有 `.venv` 启动 API 和 Worker，在 `apps/web` 启动 Vite；若已有对应服务正常则复用。Windows 分别执行，保持进程常驻：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000 --reload
.\.venv\Scripts\python.exe -m apps.worker
```

在另一个位于 `apps/web` 的终端：

```powershell
npm run dev -- --host 127.0.0.1 --port 5173
```

3. API 启动完成后检查健康接口，登录后进入 `/inspect/pcb`。三个模型仍从服务端准入目录获得；未准入不能因前端可见而强制提交。
4. 需要关闭时由负责人手动将 `PCB_SEGMENTATION_ENABLED=false` 并让 API/Worker 重新读取配置；不删除数据库、队列、输入、已提交任务或历史结果。已成功任务仍按权限查看；重新领取或发布中的任务遵循关闭/撤权复核。

## 10. 可复现入口与最终验收表

在同一 Windows 仓库、已有依赖与缓存 Docker 镜像可用时，使用新的证据路径运行，不覆盖此次结果。真实脚本自己创建/清理独占临时服务，不使用日常端口和 `.env`。

```powershell
.\.venv\Scripts\python.exe -B -c "import platform,runpy;platform.uname();runpy.run_path('tests/run_phase_a_tests.py',run_name='__main__')"
.\.venv\Scripts\python.exe -B tests/check_pcb_batch_live.py --output <新的空证据目录>
.\.venv\Scripts\python.exe -B tests/check_pcb_classification_live.py --output <新的空证据目录>
node tests/check_pcb_build.mjs <新的构建证据目录> --classification
```

浏览器 mock 用现有 Playwright 目录作为首参数、全新输出目录作为第二参数；本机为 `C:/Users/40336/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright`。真实 batch 驱动会自动使用此现有运行时。

| ID | 结论 | 本次依据 |
|---|---|---|
| E-01 | PASS | Windows真实仓库、HEAD/基线与冻结资产核验；分类隔离回归 |
| E-02 | PASS | 整区/键盘多选、三图拖拽、追加删除、无重复按钮的48项mock及真实browser |
| E-03 | PASS | 持久父子结构、30项隔离数据库测试、六项实链与刷新历史 |
| E-04 | PASS | 三模型原生逐位一致、固定参考容差通过、mask零差异、旧API回归 |
| E-05 | PASS | 21次多尺寸CPU、6次补充图像、概率/覆盖/原尺寸及预算拒绝 |
| E-06 | PASS | GT/CAM固定可见、严格配对、部分GT、CAM状态与无GT零MetricSet |
| E-07 | PASS | 最终真实6项主任务+3项并发任务、178后端/80browser断言 |
| E-08 | PASS | 个别失败、幂等、冻结、撤权、导师筛选、Artifact私有访问；未知投递边界已说明 |
| E-09 | PASS | 683项离线、原三条CPU回归、PCB分类153+86实链、前端回归；3项symlink明确SKIP |
| E-10 | PASS | 本报告、独立证据与Windows性能齐全，无训练/生产迁移/.env修改/Git提交/自动上线 |

本报告是本轮唯一正式验收报告。所有 PASS 均限于列明的运行环境与检查范围，未运行项目和运维边界已单列。
