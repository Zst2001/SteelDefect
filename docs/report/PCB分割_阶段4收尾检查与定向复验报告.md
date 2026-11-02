# PCB 分割：阶段 4 收尾检查与定向复验报告

> 2026-10-30 补验更新：Docker恢复后已完成230项真实浏览器断言和60项独立复算，后端重新回归584 passed / 3 skipped。最新结论为本地隔离验收PASS，取消仍延期。详见[Docker恢复后补充验收报告](PCB分割_阶段4Docker恢复后补充验收报告_2026-10-30.md)。本文以下BLOCKED记录保留为补验前的历史事实。

日期：2026-10-30。依据：`docs/prompt/Steel_lab_PCB收尾检查与定向复验.md`。范围：阶段 4 的 C1–C6 收尾，不是阶段 5，也不代表生产发布。

仓库：`F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab`；分支 `main`；HEAD `a662316384d6b0f289baf530a579d6346c0e5d10`。以下源码位置均相对于该仓库根目录。

本轮证据：[pcb-stage4-closeout-20261030](pcb-stage4-closeout-20261030/)。原阶段 4 证据保留在 `pcb-stage4-2026-10-29/`；原三模型 CPU 验收以其 `cpu-deployment-final/` 为准。

## 1. 一页结论

**总体结论：BLOCKED。代码定向修复及不依赖 Docker 的回归已完成，但 C1 带 GT、C2 JPEG 的真实浏览器 → MySQL → Redis/RQ → Worker → U-Net 闭环本轮未能执行，不能宣告六项完整验收通过。**

具体阻塞是 Docker Desktop Linux engine 不可用。尝试后台启动 Docker Desktop 后，它在初始化 Inference manager 时因既有 `<LOCALAPPDATA>/Docker/run/dockerInference` 节点无法访问而退出。该节点为 0 字节 ReparsePoint，最后修改时间为 2026-10-29 11:37:17，早于本轮。按提示词“仅精确清理本轮创建并可验证归属的临时资源”的限制，本轮没有删除、改名、重置该节点或 Docker 数据。

`tests/check_pcb_live_flow.py --closeout` 实际退出码为 **1**，在创建第一个容器前停止：**新建容器 0，真实任务 0，真实浏览器推理运行 0**。独立启动的静态安全检查服务另行记账，不属于这条受阻链路。证据：[startup-blocked.json](pcb-stage4-closeout-20261030/live-browser/startup-blocked.json)、[closeout-execution.log](pcb-stage4-closeout-20261030/live-browser/closeout-execution.log)。

已完成的实质修改：

- 增加独立 `mask_visual` PNG，背景 0、前景 255；保留原始 `pred_mask` 的 0/1 协议、路径和指标来源。前端区分预览与下载，兼容缺少新制品的历史任务。
- 修复 Vite 私有资产路径的拒绝行为：原直接路径可能返回 SPA HTML，原 `/@fs/` 拒绝页会包含内部绝对路径；新增定向 guard，同时处理编码、点段及 Windows 尾随点/空格别名。**未观察到权重或 ZIP 内容被实际返回，不将它描述为已证实的权重泄露。**
- 上传页、详情页明确显示取消延期说明；没有新增取消 API 或假取消状态。
- 扩展真实验收脚本、JPEG 身份验证、双 Mask、权限白名单、取消拒绝及私有 GET/HEAD 回归。

实际回归：A/B/C 后端 **578 passed、3 skipped**；PCB 资产/推理 **81 passed、12 subtests passed**；PCB 模拟浏览器 **182 项**；旧主页面 **156 项**；钢铁分类前端 **52 项**；PCB 静态检查 **31 项**；阶段 C 前端 **22 项及 5 个 SFC 语法检查**。旧钢铁分割和分类各完成一次真实 CPU 测试（分别覆盖 3 条和 2 条业务分支），详见第 8 节。各集合不可简单相加为“真实端到端测试数”。

**建议：暂不启用日常本地站点的 PCB 功能。** 源码默认开关仍为 `False`，待 Docker 恢复后完成 C1/C2 的真实验收再判断。未训练、未修改正式权重或准入回执、未访问日常数据库/Redis、未改 `.env`，未 commit/push。

## 2. 六项完成矩阵

| 项目 | 实际状态 | 修改与执行 | 证据 |
|---|---|---|---|
| C1 带 GT 真实浏览器 | **BLOCKED / NOT_RUN** | 已扩展 `check_pcb_live_flow.py --closeout`、真实浏览器脚本及独立复算器；启动退出 1，未创建真实任务 | `live-browser/startup-blocked.json`、`preflight.json` |
| C2 JPEG 文件身份 | **源码/隔离 HTTP 单测 PASS；真实闭环 BLOCKED** | 无需生产转换修复；新增 PNG/JPEG 实际字节、解码像素、MIME、格式拒绝回归；新真实 JPEG 浏览器运行未发生 | `backend-unit.log`、`backend-review.json`、`live-browser/` |
| C3 双 Mask | **实现、单测、模拟 UI PASS；新真实链路待验** | Worker 输出层新增可视化制品，白名单及 UI 配套；原始协议和受绑定推理代码未变 | `frontend/results.json`、下载 PNG、`backend-unit.log` |
| C4 私有 GET | **真实静态负向检查 PASS；真实 MySQL 制品正例 BLOCKED** | Vite/API/构建最终各 280 GET/HEAD，合计840个最终矩阵请求；授权正例及跨用户拒绝已由隔离 HTTP 单测验证 | `private-get-*.json`、`build-final/`、`backend-unit.log` |
| C5 取消能力 | **DEFERRED / NOT_SUPPORTED** | 可见说明与无假入口检查 PASS；HTTP 404/405 拒绝且任务不变；没有实现取消 | `frontend/static-results.json`、`frontend/results.json`、后端取消测试 |
| C6 审查与关键回归 | **已执行项目 PASS；依赖真实链路项目 BLOCKED** | 后端、推理、旧钢铁真实 CPU、前端与构建已跑；完整 MySQL 并发、强杀恢复、项目级类型检查未运行 | 第 8 节命令表及日志 |

## 3. GT 真实浏览器验收

### 3.1 本轮实际结果

本轮没有真实任务 ID、真实 MySQL MetricSet、真实推理结果截图或真实 U-Net 指标复算结果。不存在可引用的本轮 `live-browser/results.json` 成功证据。**原阶段 4 的 100 项真实浏览器通过结果不能替代本次带 GT 的缺口。**

已经生成并验证格式的合成输入位于 `live-browser/synthetic-inputs/`：

- `synthetic-pcb-220.png`：220×220 RGB PNG。
- `synthetic-pcb-220.jpg`：真实 JPEG 编码，220×220 RGB，默认 EXIF 方向。
- `synthetic-pcb-gt.png`：220×220 单通道 PNG，含正负像素，输入值为 0/255。
- `provenance.json`：生成方法、正负像素数量及文件 SHA-256。来源是确定性随机纹理与程序绘制几何，不是 Meiwei 数据或模型预测。

这些合成资料只用于链路和算术验收，**不得解读为模型真实精度**。格式预检成功不等于提交或推理成功。

### 3.2 已准备、尚未实际执行的检查

`tests/check_pcb_live_flow.py --closeout` 复用隔离容器/存储/进程方式，仅计划两次默认 U-Net：PNG+GT 和 JPEG 无 GT。`tests/check_pcb_closeout_frontend.mjs` 通过登录表单实际登录、上传、提交、等待、切换图层、下载 JSON/图层、历史重入和刷新，并检查未授权下载。

`tests/pcb_closeout_verify.py:verify_results` 使用独立 Pillow/NumPy 运算，从下载原始 mask 和 GT 复算 TP/FP/FN/TN，再对照数据库 MetricSet、API、`pcb.json` 和 UI 百分数字符串，不调用生产指标函数。原图制品没有独立的图层下载按钮，因此脚本通过已认证浏览器 request context 获取原图，记录真实响应头；不会谎称点过不存在的按钮。

零分母政策保持：Dice/IoU/Precision/Recall 的分母为零时返回 `null`，UI 为 `—`；不填入 0、1 或置信度。合成图片允许模型预测全背景，独立复算器记录实际前景数，不强迫模型产生缺陷。非空/全空可视化语义由确定性的单元测试分别覆盖。

### 3.3 已执行的较低层证据

`tests/test_pcb_backend.py:test_pcb_dual_mask_download_geometry_values_and_metrics` 已对真实 PNG 解码、隔离 SQLite MetricSet、API、JSON 和独立像素计数做一致性检查，覆盖非空及全空情况；计算和队列为测试替身。模拟浏览器覆盖带 GT、无 GT、无定义指标和权限错误。两者均不能替代本节真实 MySQL/RQ/权重闭环。

## 4. JPEG 文件身份

**结论：源码与隔离 HTTP 单测未发现 JPEG 内容误标为 PNG 的问题，因此未修改生产图像转换逻辑。**

| 环节 | 当前实现与证据 |
|---|---|
| 上传校验 | `apps/api/app/services/pcb_segmentation.py:112`，`image_bytes` 检查实际 PNG/JPEG 格式与扩展名一致、RGB、220×220、单帧及 EXIF 方向缺省或 1 |
| 原始 Sample | 同文件 `create_batch:144` 保存原始上传字节，JPEG 为 `.jpg`，PNG 为 `.png`；单测对照全部字节相等 |
| Worker 消费 | `apps/worker/pcb_segmentation.py:108–130` 校验实际读取字节哈希，解码为 RGB 数组，将该数组送入 `compute` |
| 展示原图 | 同文件 `run_pcb_body` 以同一 `image_rgb` 生成 `origin/image.png`，暂存时显式 `format="PNG"`，不是修改扩展名 |
| HTTP | `apps/api/app/routers/tasks.py:get_file:91` 的 `FileResponse` 基于 PNG 路径返回 `image/png`；单测验证 PNG magic `89504e470d0a1a0a` |
| 像素一致性 | 下载 PNG 为 RGB 220×220，与 Pillow 解码原 JPEG/PNG 的像素及测试计算入口实际收到的像素完全相同，无旋转、缩放、色彩增强 |
| 文件名 | HTTP URL basename 为 `image.png`；通用服务端当前不设置 `Content-Disposition` 文件名。图层按钮使用前端 `{taskId}_{kind}.png`；真实 JPEG 浏览器文件名检查尚未执行 |

新增/扩展测试定位：

- `test_pcb_origin_format_bytes_mime_and_consumed_pixels`（约第 545 行）：PNG、JPEG 正例、原字节、PNG magic/MIME、下载像素、实际消费数组和跨用户拒绝。
- `test_pcb_bad_inputs_leave_no_batch`：伪扩展名、非 RGB（含 JPEG 灰度/CMYK）、尺寸等失败不留下批次。
- `test_pcb_exif_is_explicit`：PNG/JPEG 非默认 EXIF 拒绝，方向 1 接受。

本轮 JPEG 上传前/完成后真实浏览器预览截图：**NOT_RUN**。`frontend/` 截图来自模拟 API，不用于证明 JPEG 真实链路。

## 5. 原始与可视化 Mask

| 项目 | 原始 Mask | 可视化 Mask |
|---|---|---|
| Artifact kind | `pred_mask` | `mask_visual` |
| 相对路径 | `pred_mask/{model_version_id}/image.png` | `mask_visual/{model_version_id}/image.png` |
| 编码 | PNG，L，uint8，220×220 | PNG，L，uint8，220×220 |
| 像素集合 | 非空 `{0,1}`；全空 `{0}` | 非空 `{0,255}`；全空 `{0}` |
| UI 标签 | 原始二值掩码（0/1） | 可视化掩码（0/255） |
| 下载名 | `{taskId}_pred_mask.png` | `{taskId}_mask_visual.png` |
| 用途 | 程序处理、指标与复现 | 直接查看和展示下载，不参与推理或指标 |

新增计算仅为 Worker 输出层 `pred * np.uint8(255)`，发生在原始预测验证和指标计算之后。它进入已有暂存、受控发布和清理流程。`pcb.json` 的 legend 增加像素含义，未更改原始预测或冻结协议。

`TaskArtifacts.permitted` 仅在 PCB 分支加入这一 kind，仍核验模型、样本键、精确目录和注册制品；`locate` 的封闭路径、link/junction 拒绝继续生效。新增 7 类负向回归覆盖错误模型、样本、kind、目录、扩展名、路径穿越和未注册磁盘文件。

隔离 HTTP 单测确认授权用户可下载两份 PNG，无关学生及未获分享导师均被拒绝。对非空 mask，两个文件的前景坐标逐像素完全相同；可视化前景为 255。全空预测时两者均全零。原始下载 mask 与 GT 独立复算结果和 API/数据库/JSON 一致。

历史任务没有 `mask_visual` 时，详情仍可加载；可视化按钮禁用并解释原因，原始掩码保留 CSS 提亮预览，下载字节仍为 0/1。没有补写历史数据或强制要求旧任务新增制品。

模拟浏览器证据：`frontend/03-directly-visible-mask.png`、`frontend/04-legacy-mask.png`、`frontend/390-inspect-pcb-tasks-legacy.png`、5 份下载 PNG 及 `results.json`。桌面直接可见 mask 和 390px 历史页已人工查看；页面上的合成/模拟验收标识保留。

## 6. 私有 GET/HEAD 安全检查

### 6.1 范围及方法

实际检查 14 个资产路径：原 ZIP、sidecar、3 个权重、3 个参考 logits、3 份资产源码（trusted_models/preprocess/postprocess）、ASSET_MANIFEST、MODEL_REGISTRY、私有 admission 回执。

每个路径最终 10 个 URL 变体，分别 GET、HEAD：直接相对路径、`/@fs/` 绝对映射、编码斜线、双重编码、`?raw`、点段、`assets` 目录尾随点/空格、私有子目录尾随点/空格。最终每个服务 **14×10×2=280** 请求。

请求仅访问本轮隔离 `127.0.0.1` 随机端口；明确拒绝 8000/5173 日常服务。GET 带 `Range: bytes=0-511`，最多捕获 4096 字节并及时关闭连接。报告只保存状态、Content-Type、Location、安全固定拒绝正文及有限元信息；任意非固定正文均隐藏。没有完整 HTTP 下载权重/ZIP。

最终 GET 的 PASS 条件同时要求 403/404、无内部绝对路径、正文为已知固定拒绝文案；HEAD 要求拒绝状态且无内部路径。首个传输错误会写明失败并停止该轮矩阵，不将没有执行的请求算作通过。

### 6.2 复现、修复与复验

| 轮次 | 结果 | 解释与证据 |
|---|---|---|
| 原实现，6 变体 | FAIL，154/168 未达拒绝标准 | 140 个请求返回 200 SPA HTML；14 个 `/@fs/` GET 返回含内部路径的 403 HTML；另 14 个 HEAD 拒绝正常。见 `private-get-before-corrected-detector.json` |
| 定向 guard 首版，6 变体 | Vite/API/构建分别 168/168 PASS | 文件 `private-get-vite.json`、`private-get-api.json`、`build/private-get-build.json` 保留 |
| Windows 别名扩展，修复前 | FAIL，112/280 未达标准 | 新增 4 变体的 GET/HEAD 返回 200 SPA HTML；没有取得私有资产内容。见 `private-get-windows-alias-before.json` |
| Vite 最终，10 变体 | **280/280 PASS，exit 0** | `private-get-vite-final.json`、`.log` |
| 构建预览最终，10 变体 | **280/280 PASS，exit 0** | `build-final/private-get-build.json`、`build-final/build.json`、`build-final.log` |
| FastAPI 最终，10 变体 | **280/280 PASS，exit 0** | 全部404；`private-get-api-final-v2.json`、`-execution.log`、`-server.log` |

实际修复为新增 `apps/web/pcb-private-assets.ts:pcbPrivateAssets`，由 `vite.config.ts` 在开发及预览服务器静态处理之前注册。解码、规范化斜线/点段/Windows 目录别名后，对 `assets/pcb` 和 `assets/PCB_segment` 返回固定 403 `Forbidden`、`no-store`、`nosniff`。不删除资产，不扩大 `fs.allow`，也不把所有 GET 一律拒绝。

构建使用实际 Vite 配置、临时输出目录且不读取 `.env`，递归检查产物不含 ZIP/pth/npy/py/admission/manifest/registry。正常首页 GET 200、PCB 代码块 HEAD 200，证明普通静态资源仍可访问。

独立 FastAPI 使用真实应用路由和 Uvicorn，但设置为 init-only Settings、关闭 seed/PCB、无数据库建表和出站 socket；临时 SQLite 文件未创建。这是真实公开负向 HTTP 检查，不是真实 MySQL/RQ/模型链路。其私有静态路径返回 404，固定 JSON 拒绝正文。

正常授权任务文件的正例与未授权 404 由 `test_pcb_origin_format_bytes_mime_and_consumed_pixels`、`test_pcb_dual_mask_download_geometry_values_and_metrics` 等隔离 HTTP 单测覆盖。**本轮真实 MySQL 任务制品授权下载正例仍 BLOCKED，因此 C4 的完整联合门禁不宣称全部通过。**

过程证据说明：初版路径检测正则会误把 `https:` 中字符当成本地盘符，`private-get-before.json` 仅留作调试过程，不用于结论；修正后的 `private-get-before-corrected-detector.json` 才是基线。Windows 变体首次探测出现一次有限请求超时，退出 1；第二次观察模式完成全部 280 请求，观察模式自身退出 0 不代表矩阵 PASS。API 扩展首次启动等待超时退出 1，记录为执行失败，不计入通过数。

API 最终复验将测试启动等待由约30秒改为180秒并增加阶段/诊断栈，隔离限制未放宽。45秒诊断栈停在 `app.main → services.scatter → matplotlib.font_manager → plistlib` 的模块文件读取，随后正常启动；实际ready为55.97秒，启动加矩阵约56.64秒。这里确认的是导入耗时超过原测试窗口，不认定是 `platform.uname` 故障，也未为测试改生产初始化代码。最终文件记录进程树、临时目录清理PASS及SQLite未创建。

## 7. 取消延期说明

**能力状态：DEFERRED / NOT_SUPPORTED。**

用户可见文案为：**“任务取消本期延期，当前不支持主动中止已提交任务”**。上传和详情页说明原系统尚无统一取消协议、离开页面不会终止任务；“新建分割/再跑”仍是创建新任务。

检查覆盖上传页、详情、历史及 1440/768/390 布局。没有新增取消按钮、空回调或 `canceled/canceling` 伪状态。历史菜单中的“取消归档”是既有归档操作，并非停止 Worker，保留原行为。

`test_pcb_cancel_api_is_absent_and_requests_cannot_mutate_task` 验证 OpenAPI 不含取消接口，`POST /api/tasks/{id}/cancel` 与 PCB 场景取消路径为 404，`DELETE /api/tasks/{id}` 为 405；任务仍 queued，入队次数仍为一次。

页面已有 queued/running/success/failed 映射，超时通过失败原因提示；禁用、授权变化及错误响应保留明确反馈。“延期说明和拒绝检查通过”不等于“取消功能已实现”。

## 8. 定向审查、修改范围与关键回归

### 8.1 工作树保护和本轮代码范围

开始时核对上轮 54 个代码/配置/测试文件，哈希全部与上轮清单一致。开始时已有 25 个 tracked 修改，以及 PCB 新文件、历史报告、`ppt/`、`output/` 等未跟踪内容。本轮不将这些整体认领为本轮改动，不 stage、不重置。

[changed-closeout-files.json](pcb-stage4-closeout-20261030/changed-closeout-files.json) 单列本轮 **18 个代码/配置/测试文件**及哈希：修改原基线 10 个文件，另修改原来干净的 Vite 配置，新增 7 个文件。报告和证据文件不计入这个代码文件数。

| 类别 | 文件 |
|---|---|
| 后端输出与白名单 | `apps/worker/pcb_segmentation.py`、`apps/api/app/services/task_artifacts.py` |
| PCB 前端 | `apps/web/src/views/pcb/PcbNewView.vue`、`PcbTaskView.vue`、`types.ts` |
| 静态资产拒绝 | `apps/web/vite.config.ts`、新增 `apps/web/pcb-private-assets.ts` |
| 修改既有测试 | `tests/test_pcb_backend.py`、`check_pcb_frontend.mjs`、`check_pcb_live_flow.py`、`check_pcb_live_frontend.mjs`、`check_pcb_build.mjs` |
| 新增测试/核验器 | `tests/check_pcb_closeout_ui.mjs`、`check_pcb_closeout_frontend.mjs`、`pcb_closeout_verify.py`、`pcb_private_get_probe.mjs`、`check_pcb_private_get.mjs`、`check_pcb_private_api.py` |

未修改首页、全局导航风格、钢铁协议、学生模型执行体系、学术 RAG、资产本体或受准入绑定的推理源码。

### 8.2 问题与审查记录

| 编号 | 文件/函数与证据 | 影响、处理及测试 |
|---|---|---|
| C2-JPEG-IDENTITY | `services/pcb_segmentation.py:image_bytes/create_batch`；`worker/pcb_segmentation.py:run_pcb_body`；`routers/tasks.py:get_file` | **已检查未发现错配。** 原始 JPEG 保留，展示显式 PNG；补格式/MIME/消费像素回归，不改生产转换 |
| C3-MASK-DISPLAY | `worker/pcb_segmentation.py:136–141`；`task_artifacts.py:permitted`；`PcbTaskView.vue` | 原下载仅 0/1，普通查看器中难以辨认；新增独立 0/255 制品与明确 UI，双 mask、权限、历史兼容测试通过 |
| C4-STATIC-DENIAL | `vite.config.ts`；新增 `pcb-private-assets.ts`；真实 HTTP 修复前矩阵 | SPA 200 和 Vite 拒绝页内部路径披露已复现；增加固定拒绝，Windows 别名同样归一化。最终 Vite/构建矩阵通过；未证实资产内容泄露 |
| C4-PROBE-BODY | `tests/pcb_private_get_probe.mjs:probePrivateAssets` | 独立复审发现初版仅用状态与路径判断，非固定 403 正文也可能被判 PASS；现要求 GET 固定安全正文，重新做最终矩阵，不把隐藏内容当作安全证据 |
| C5-CANCEL-DEFERRED | `views/pcb/types.ts`、上传/详情；`test_pcb_backend.py:699` | 原无假取消实现，但缺明确帮助；补延期说明，404/405、状态不变检查；仍不支持取消 |
| C6-LOADER | `catalog.py:require_admitted:96`；`runtime.py:load_model:22` | **已检查未发现新增问题。** 同一打开流先哈希，随后 `weights_only=True`、`strict=True`；校验参数和 CAM 层身份；相应资产/推理单测通过 |
| C6-PROTOCOL-CAM | `preprocess.py:prepare_canvas:12`、`postprocess.py:mask_and_probability:18`、`visualize.py:SegmentationGradCAM:53` | **已检查未发现新增问题。** 220 四边 pad18→256，除255，裁回 `[18:238]`，类别1前景；CAM finally 清 hook/梯度并恢复状态。受绑定源码未改 |
| C6-LIFECYCLE | API `create_pcb_task:238`、`pcb_snapshot:206`，`input_freeze.py:verify_inputs:89`，`jobs.py:_run_task:236`，Worker `run_pcb_body:98`，`pcb_delivery.py:reconcile_unclaimed_failure:20` | **已检查未发现新增问题。** 幂等/CAM冲突、冻结、实际字节、计算前后权限、锁释放、暂存发布清理、领取前失败回收有回归；普通CAM失败与RQ超时区分，未宣称完成强杀恢复 |
| C6-SCENE | `models.py:is_other_scene_version:18`，`tasks.py:_resolve_runnable_models:89`，`datasets.py:get_visible_dataset:29`，`records.py:rerun_record:252` | **已检查未发现新增问题。** PCB task/batch/模型标识与旧场景隔离，旧数据集路径不绕过权限；再跑新建任务，默认关闭 |

详细后端审查：[backend-review.json](pcb-stage4-closeout-20261030/backend-review.json)。前端审查：[frontend/review.json](pcb-stage4-closeout-20261030/frontend/review.json)。

### 8.3 实际测试命令和结果

以下命令从仓库根目录执行；`$ev` 表示 `docs/report/pcb-stage4-closeout-20261030`，`$pw` 表示 `C:/Users/40336/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright`。这是路径简写，不是环境文件。Python 采用已有 `.venv/Scripts/python.exe`，无安装/升级依赖。

| 检查 | 实际命令（路径用上述简写） | 结果 / 退出码 | 证据与依赖边界 |
|---|---|---|---|
| A/B/C 全量后端 | `.\.venv\Scripts\python.exe -B -c "import platform, runpy; platform.uname(); runpy.run_path('tests/run_phase_a_tests.py', run_name='__main__')"` | **578 passed、3 skipped、2 warnings；0** | `backend-regression.log`；隔离配置/SQLite/替身队列。原560变578来自新增18项，不复制原结果 |
| PCB 后端定向 | `.\.venv\Scripts\python.exe -B -c "import platform,runpy,sys;platform.uname();sys.argv=['tests/run_phase_a_tests.py','tests/test_pcb_backend.py'];runpy.run_path('tests/run_phase_a_tests.py',run_name='__main__')"` | **78 passed、0 skipped、2 warnings；0** | `backend-unit.log`；这78项已包含在578项中，不重复计数 |
| PCB 资产/推理单测 | `$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'` 后执行 `.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests/test_pcb_asset_admission.py tests/test_pcb_infer.py` | **81 passed、12 subtests、1 warning；0** | `admission-unit.log`；单测不是新三模型完整准入 |
| 原钢铁分割真实 CPU | `.\.venv\Scripts\python.exe -B tests/check_steel_cpu_regression.py --report "$ev/legacy-steel-cpu.json"` | **1 passed；0** | `.json/.log`；本地真实 UNet，合成 compare无GT/有GT/demo三条流程；临时SQLite/替身队列 |
| 原钢铁分类真实 CPU | `.\.venv\Scripts\python.exe -B tests/check_classification_cpu_flow.py --report "$ev/legacy-classification-cpu.json"` | **1 passed；0** | `.json/.log`；真实 MobileNetV3 Small，两条有/无GT流程，每条2图；隔离存储 |
| PCB 模拟浏览器 | `node tests/check_pcb_frontend.mjs $pw "$ev/frontend"` | **182断言；0** | `frontend/results.json`、`mock-browser.log`；25张截图、5个mask下载文件，业务API为mock |
| PCB 静态/SFC | `node tests/check_pcb_closeout_ui.mjs` | **31检查；0** | `frontend/static-results.json` |
| 原主页面 | `node tests/check_frontend_light.mjs $pw "$ev/steel-ui-regression"` | **156断言；0** | 309 mock API 请求、0未捕获异常；`steel-ui.log`、目录内results |
| 钢铁分类前端 | `node tests/check_classification_frontend.mjs $pw "$ev/classification-ui-regression"` | **52断言；0** | 78 mock API 请求、0未捕获异常；`classification-ui.log` |
| 阶段 C 前端 | `node tests/check_phase_c_frontend.mjs` | **22断言+5 SFC语法；0** | `phase-c-ui.log`；不等于项目级vue-tsc |
| Vite GET 最终 | `node tests/check_pcb_private_get.mjs "$ev/private-get-vite-final.json"` | **280/280；0** | `private-get-vite-final.json/.log`；实际Vite |
| 构建+预览 GET 最终 | `node tests/check_pcb_build.mjs "$ev/build-final"` | **构建PASS、280/280、正常静态正例；0** | `build-final.log`及目录；有既有>500kB chunk提示，无构建失败 |
| API 独立负向首轮 | `.\.venv\Scripts\python.exe -B tests/check_pcb_private_api.py` | **168/168；0** | `private-get-api.json`；真实FastAPI/Uvicorn，无DB/推理 |
| API 独立负向最终 | `.\.venv\Scripts\python.exe -B tests/check_pcb_private_api.py --output "$ev/private-get-api-final-v2.json"` | **280/280；0** | 最终JSON、execution/server日志；180秒启动等待，不使用日常服务 |
| 资产完整性 | `.\.venv\Scripts\python.exe -B scripts/verify_pcb_assets.py --report "$ev/asset-integrity.json"` | **ASSET_INTEGRITY_PASS；0** | 52文件、51内部SHA校验、50manifest校验；不解压执行资产源码 |
| 回执只读校验 | 调用 `infer.pcb.catalog.require_admitted()`，并记录 `source_hashes()`、`receipt_path()`、`canonical_hash()` | **VERIFIED_FOR_STAGING；0** | `admission-receipt-check.json`；未重写回执、未重新benchmark |
| 真实 PCB 浏览器链路 | `.\.venv\Scripts\python.exe -B tests/check_pcb_live_flow.py --closeout` | **BLOCKED；1** | `live-browser/`；Docker创建容器前失败，不能计通过 |
| 新验收脚本预检 | `check_pcb_live_flow.py --help`；两个浏览器脚本 `node --check`；三个Python文件AST解析 | **6项通过；CLI/Node退出0** | `live-browser/preflight.json`；另有3个合成输入格式检查，不代表业务执行 |
| 验收脚本最终预检 | 3个Python文件AST解析+两个浏览器脚本及GET探测器 `node --check` + `check_pcb_live_flow.py --help` | **7项通过；0** | `live-browser/preflight-final.json`；包含允许合法全背景输出的最终验证器 |

钢铁分割真实 CPU 验证采用测试内固定哈希、`weights_only=True` 读取和原严格构建器，生产加载器未改。compare无GT和demo的 MetricSet 为0，有GT为1；此测试不是正式NEU-20评测。钢铁分类有GT/无GT均成功，下载与历史可读；未宣称实验精度。

两条真实 CPU 冒烟不依赖本轮故障的 Docker/MySQL/RQ，因此可以完成，但不能替代 PCB 要求的真实基础设施测试。

### 8.4 明确跳过或未执行

- **SKIPPED 3**：`tests/test_task_artifact_access.py:192`，Windows 当前不允许创建测试 symlink；既有路径校验未放宽。
- **BLOCKED / NOT_RUN**：本轮 C1/C2 两个 PCB 真实浏览器任务、真实 MySQL 指标交叉复算、与这两个新任务绑定的授权下载。
- **NOT_RUN**：完整 MySQL 并发/隔离级别竞争验收、Worker 进程强杀/断电恢复、项目级 `vue-tsc`。
- **不需重跑**：三模型全套 CPU 准入/性能 benchmark；绑定代码、权重、协议和运行库未变，回执只读校验通过。没有把旧准入结果记作本轮新运行。
- **未执行且不在本轮范围**：训练、下载模型、云端实验、正式 test 精度评测、部署生产。

## 9. 准入回执与功能开关

ZIP 哈希保持 `7c93a1f299f7e2b998ee1c8473ce9f3b6b700487247d4c069a69ec0240549c1d`，sidecar、52个交付文件及manifest按冻结规则通过只读检查。检查器明确输出 `archive_code_executed=false`、`extracted_to=null`。

本轮没有修改 `packages/infer/pcb/` 的8个基线文件（含PROVENANCE及初始化文件）。运行时仍为已有 Windows `.venv` CPU 环境，线程2、interop6。`require_admitted` 验证现有三个模型 `unet/unet_resnet18/unetpp_resnet18` 均为 `VERIFIED_FOR_STAGING`。

- deployment source hash：`fe45790c8fdf6d413ea13f6fc13b797a3043e7f33ea586e82335b8c541673f6d`。
- 原私有回执文件 SHA-256：`cc53d3ce87eeba73bfa14692c8c20b801831df8e26b3dae33bb6010d09ca246c`。
- 本轮仅保存校验结果与摘要，没有复制旧回执制造新准入，也没有改hash绕过门禁。

`apps/api/app/config.py:39` 仍为 `pcb_segmentation_enabled: bool = False`。生产文件只扩展结果展示及静态拒绝，未开启日常入口。没有读取/打印 `.env` 内容或写入 `.env`；不访问 AutoDL、Milvus、外部模型API，不改变NEU-20/学术RAG/学生Docker边界。

## 10. 剩余事项与建议

1. **先恢复 Docker Desktop 的既有运行环境。** 当前仅确认其启动诊断涉及既有 `dockerInference` 节点，未把删除节点或重置数据当作已授权措施。该环境问题不归因于 PCB 业务代码。
2. Docker 健康后，在隔离环境重新运行两个真实 U-Net 任务及独立复算器。建议新证据目录，保留本次阻塞记录：

   ```powershell
   .\.venv\Scripts\python.exe -B tests/check_pcb_live_flow.py --closeout --output docs/report/pcb-stage4-closeout-rerun-YYYYMMDD/live-browser
   ```

   通过标准必须同时包括真实浏览器结果、独立 `independent-verification.json`、新任务的允许/拒绝下载及截图；不能只检查进程退出或页面有数字。
3. 在真实门禁通过前，维持日常站点 PCB 关闭。C5 继续延期，强杀恢复/完整并发/项目级类型检查作为明确独立事项，不将这轮扩成架构改造。

最终静态/API检查的临时服务和可验证归属的临时目录已按脚本清理；Docker失败链路未创建容器。不对来源不明的既有临时目录执行删除。本轮未删除历史文件、未重置工作区、未改日常/生产数据、未提交或推送Git。

最终验收含义：**可供独立评审的定向实现和测试证据已交付；受真实环境阻塞，PCB阶段4收尾尚未取得完整PASS，不建议据此启用日常功能。**
