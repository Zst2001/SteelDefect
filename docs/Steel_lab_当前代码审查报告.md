# Steel_lab 当前代码审查报告

审查日期：2026-10-19  
依据：当前工作区源码、现有测试代码、Git 状态及《项目介绍与 ChatGPT 规划上下文》。

> 本文件根据用户后续要求，将对话中已完成的审查报告保存为 Markdown。下述 Git 状态和结论对应审查时点；本次保存不构成新一轮审查或开发授权。

**审查阶段仅进行了静态、只读审查，没有修改项目文件，没有运行测试、模型推理、服务、数据库迁移或远程调用。下文“测试有证据”仅表示存在相应测试代码，不代表本次测试通过。保存阶段仅新增本报告文件。**

## A. 项目现状摘要

### A.1 总体结论

当前实现与项目介绍的主体定位一致：

- Vue 3 前端、FastAPI API、RQ SimpleWorker、MySQL、Redis，以及 Docker 学生模型隔离形成完整业务结构。
- 当前推理实现集中于钢铁语义分割，包含公开演示、实验台对照和正式评测三种协议。
- 科研助手已有学术、分割、模型三专科及工具白名单；模型适配助手独立实现。
- 新增场景导航已经落地；PCB、光伏及钢铁检测、分类保持不可提交。
- 学术 RAG 的集合限制、阈值、召回整理及缓存规则有代码支持。

但介绍文档中的部分表述需要收窄：

1. **学生模型权限并非在所有入队参数上得到一致检查。**
2. **任务文件下载接口校验了任务权限和路径边界，但没有限制为允许公开的结果制品。**
3. **固定测试集原始 GT 下载接口受保护，但生成的彩色 GT 图层及包含 GT 的结果包仍可下载。**
4. **正式评测按“预置且固定测试集”属性判断，没有直接锁定 NEU-20 身份及 20 张样本数量。**
5. **任务持久化、缓存失效和 RQ 入队之间存在失败后状态不一致的窗口。**

这些是现有链路的边界问题，与尚未开放新算法任务无关。

### A.2 Git 状态

- 当前分支：`main`
- HEAD：`f12bccba1f83762a43558f66cb59184ea3d57f8d`
- 提交说明：`Update README to match the shipped assistant, RAG, and local bootstrap.`
- 暂存区：未发现已暂存文件。
- 本地状态显示跟踪 `origin/main`；本次未 fetch，不能据此确认远程服务器是否有更新。

**已修改、未暂存：**

| 文件 | 变更归属 |
|---|---|
| [apps/api/app/main.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/main.py) | 注册 scenes 路由 |
| [apps/api/app/routers/__init__.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/routers/__init__.py) | 导出 scenes |
| [AppLayout.vue](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/web/src/layouts/AppLayout.vue) | 场景侧栏及选中状态 |
| [router/index.ts](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/web/src/router/index.ts) | 场景路由、旧路径跳转 |
| [PlaceholderDisabledView.vue](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/web/src/views/PlaceholderDisabledView.vue) | 场景空页说明 |
| [CompareNewView.vue](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/web/src/views/compare/CompareNewView.vue) | 正式评测链接 |
| [课题组网站需求分析书.md](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/docs/课题组网站需求分析书.md) | 当前需求修订 |

**未跟踪：**

- [routers/scenes.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/routers/scenes.py)
- [services/scenes.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/services/scenes.py)
- [views/inspect/](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/web/src/views/inspect/)
- [test_scenes_empty.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_scenes_empty.py)
- [交接3.md](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/docs/交接3.md)
- [项目介绍与ChatGPT规划上下文.md](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/docs/项目介绍与ChatGPT规划上下文.md)
- [ppt/](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/ppt/)

已查看的业务代码 diff 与最近的场景入口工作一致。介绍文档属于后续补充资料。`ppt/` 按用户说明属于无关汇报材料，本次没有阅读其内容。

**后续必须保护：**全部现有未提交内容、首页 hero、UI token、分割协议、学生隔离、RAG 规则以及本地敏感配置。不能用清理工作区、格式化全仓库或批量提交的方式处理这些变更。

## B. 代码架构与调用链

### B.1 前端创建、查询和下载任务

统一 HTTP 客户端在 [http.ts:9](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/web/src/api/http.ts:9)，使用 `/api` 前缀、携带 Cookie，并提供统一错误格式化。

| 业务 | 关键入口 | 实际调用 |
|---|---|---|
| 快速对照 | [CompareNewView.vue:163](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/web/src/views/compare/CompareNewView.vue:163) 的 `submit` | 上传图片 → 可选上传掩码 → `POST /tasks/compare` |
| 正式评测 | [EvalNewView.vue:133](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/web/src/views/eval/EvalNewView.vue:133) | `POST /tasks/eval` |
| 公开演示 | [DemoNewView.vue:121](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/web/src/views/demo/DemoNewView.vue:121) | `POST /demo/tasks`，不经过上传接口 |
| 对照／评测结果 | [CompareTaskView.vue:279](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/web/src/views/compare/CompareTaskView.vue:279) 的 `refresh` | 查询任务及 metrics；约 2.5 秒轮询 |
| 演示结果 | [DemoTaskView.vue:196](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/web/src/views/demo/DemoTaskView.vue:196) | 查询独立演示任务接口，不请求 metrics |
| 下载 | 两类结果页的下载函数 | 分别调用实验台和演示的文件／bundle 接口 |

前端对照页确实按模型来源过滤内置模型和学生模型。但**前端筛选不能代替后端参数鉴权**，见 F.1。

### B.2 API 鉴权、校验、持久化与入队

主要入口：

- [main.py:55](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/main.py:55)：注册全部 `/api` 路由。
- [authz.py:31](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/authz.py:31)：`get_current_user` 检查 Session、有效期和账号状态，并续期会话。
- [routers/tasks.py:27](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/routers/tasks.py:27)：`CompareIn`、`EvalIn` 提供 Pydantic 输入校验。
- [services/tasks.py:191](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/services/tasks.py:191)：`create_compare_task`。
- [services/tasks.py:271](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/services/tasks.py:271)：`create_eval_task`。

实际顺序为：

1. 检查数据版本、归属及任务协议。
2. 解析模型版本，检查可运行状态、CPU 条件及协议一致性。
3. 建立 `Task`、`TaskModel`、`TaskSample`。
4. 提交 MySQL 事务。
5. 失效 Redis 缓存。
6. `_enqueue_task` 将任务 ID 交给 RQ。

第 4～6 步不是一个原子操作，失败补偿不完整，见 F.3。

### B.3 Worker 如何区分三种协议

[apps/worker/__main__.py:17](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/worker/__main__.py:17) 创建 `SimpleWorker`，不使用 fork 模式。

[apps/worker/jobs.py:192](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/worker/jobs.py:192) 提供：

- `run_compare`：只接受 `compare`
- `run_eval`：只接受 `eval`
- `run_demo`：只接受 `demo`

共同进入 `_run_task`，随后：

- demo → `_run_demo_body` → `assert_demo_worker_contract`
- compare／eval → `_run_compare_body`
- 最终共用 `_run_inference_visuals`

`_run_options` 决定评测范围和预览抽样：

- demo：无指标范围。
- compare：`batch_reference`。
- eval：`official_split`，按配置限制可视化样本数量，但指标遍历全部关联样本。

这里的 `Task.type` 是运行协议，与需求中的分割／检测／分类算法种类不同。

### B.4 内置模型与学生模型的执行路径

**内置模型：**

`jobs._run_inference_visuals` → `infer.engine.get_builtin_module` → `build_cpu_baseline` → `predict_mask`。

- [engine.py:42](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/packages/infer/engine.py:42) 负责 CPU 加载及进程内缓存。
- [third_party/load_checkpoint.py:64](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/third_party/load_checkpoint.py:64) 使用 `strict=True`。
- 相关骨干构建使用 `pretrained=False`，避免自动下载预训练参数。

**学生模型：**

`jobs._run_inference_visuals` → `student_exec.infer_student_masks` → `run_student_container` → 容器内 `admit.runner.run_infer`。

[student_exec.py:117](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/worker/student_exec.py:117) 将预处理张量及模型文件放入任务工作目录，再调用 Docker，读取容器输出的预测数组。

### B.5 学生模型导入完整流程

[import_model.py:63](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/services/import_model.py:63) 的 `import_student_model`：

1. 校验名称、入口、类别、通道、文件扩展名和大小。
2. 保存源码和权重，计算哈希。
3. 创建 `Model`、`ModelVersion`、`Weight`。
4. `scan_student_source` 静态扫描。
5. 静态失败或声明 CUDA 时标为 `cannot_start`。
6. 其余标为 `checking`，入队 `run_admit`。
7. Worker 再次扫描，再调用学生容器。
8. 容器内依次执行 import、构建、严格加载、dummy 前向和形状检查。
9. 成功更新 `runnable`；失败记录阶段、消息和检查报告。

隔离参数见 [dockerutil.py:73](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/packages/admit/dockerutil.py:73)：禁网、只读根文件系统、非 root、丢弃 capabilities、禁止提权及 CPU／内存限制。

生产调用链没有发现 Web/API 直接 import 学生源码。测试中存在直接运行受控 fixture 的宿主子进程，不代表生产隔离路径。

### B.6 状态、文件、指标和审计保存位置

| 内容 | 实际保存位置 |
|---|---|
| 用户、模型版本、任务及子模型状态 | MySQL ORM 对象 |
| 指标 | MySQL `MetricSet`，允许计算时另写任务目录 `metrics.json` |
| 原图、权重、预测、拼图、下载包 | 本地 storage 目录 |
| 文件索引 | MySQL `Artifact` |
| 导入报告与日志 | 模型目录中的报告及日志文件 |
| 队列、缓存、演示限额 | Redis |
| 记录操作、助手回合、适配操作审计 | MySQL `AuditLog` 等对象 |

[db/models.py:175](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/db/models.py:175) 定义任务及关联对象。

[jobs.py:522](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/worker/jobs.py:522) 写出 `task.json`，包含权重哈希、预处理和环境等信息。但当前任务清单没有完整冻结掩码内容及其哈希，见 F.4。

### B.7 科研助手与模型适配助手

科研助手：

- [assistant.py:50](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/services/assistant.py:50)：三专科和工具白名单。
- `get_session` 校验会话归属。
- `_require_tool` 拒绝跨专科工具。
- `iter_add_message` 按当前会话专科选择处理逻辑。
- `preview_infer_run`、`add_infer_turn` 处理分割预览与确认。
- `add_perf_turn` 处理测参预览／入队。
- `add_code_turn` 及流式版本只读取源码、生成建议文本。
- `get_analyzable_task` 拒绝 demo，并限制可分析任务范围。

模型适配助手：

- [adapt.py:40](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/services/adapt.py:40)：只允许本人学生模型。
- `build_proposal`：AST 分析和适配提案。
- [adapt.py:219](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/services/adapt.py:219)：`apply_adapt` 检查同意、状态及白名单。
- 修改前检查原 class 和适配块外源码不变，重新静态扫描。
- 更新当前版本源码哈希，标为 `checking`，重新入队检查。
- 不直接设置为 `runnable`。

### B.8 场景与权限

- [router/index.ts:17](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/web/src/router/index.ts:17)：新路由和旧路径跳转。
- `router.beforeEach`：未登录跳登录，管理页检查导师角色。
- [SteelInspectView.vue](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/web/src/views/inspect/SteelInspectView.vue)：分割嵌入，对检测／分类显示禁用按钮。
- [routers/scenes.py:12](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/routers/scenes.py:12)：全部 scenes 入口依赖登录。
- [services/scenes.py:45](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/services/scenes.py:45)：只接受 pcb／solar 查询，提交固定返回 `409 SCENE_EMPTY`。

这部分与项目介绍一致。

## C. 项目介绍文档核验表

“源码确认”表示静态调用链支持结论；“测试代码”不表示本次执行通过。

| 文档功能或约束 | 实际代码证据 | 现有测试证据 | 核验状态及差异 |
|---|---|---|---|
| 当前只有钢铁分割可运行 | Worker 使用分割张量、掩码与混淆矩阵；场景服务拒绝其他任务 | runner、场景测试 | **一致，源码确认** |
| demo 不计算、持久化精度 | Worker 强制 `score_gt=False`；指标写入条件排除 demo；metrics 接口拒绝 demo | H3、H5、metrics policy | **一致，源码确认＋测试代码**；未运行端到端验证 |
| 无 GT 对照指标不可用 | `serialize_metrics` 在 `has_gt=False` 时返回不可用 | metrics policy、E | **一致** |
| 正式评测只用 NEU-20 | seed 登记 NEU-20；API 检查 `kind=preset`、`is_fixed_test`、完整 GT | F、data | **存在差异**：没有直接校验 NEU-20 身份或恰好 20 张 |
| 学生不能下载固定集 GT | datasets 专用下载接口检查禁止标志 | `smoke_e` 有 403 断言 | **存在差异**：结果图层、bundle 未执行同一 GT 策略 |
| 学生模型权限隔离 | `student_version_id` 检查可见性 | G、assistant 有部分越权断言 | **存在差异**：baseline 参数分支缺来源／归属检查 |
| 学生源码在 Docker 执行 | Worker 的 admit／infer／perf 均调用容器 | D 为源码字符串检查；runner 测试为本地子进程 | **生产调用链一致**；容器实际行为待核验 |
| 严格加载权重 | 内置和学生 `load_state_dict(strict=True)` | baseline、runner 测试 | **一致**；安全反序列化另有兼容分支风险 |
| 完整检查 `B×C×H×W` logits | runner 检查张量、维数及 C | runner 形状／加载失败测试 | **部分差异**：未见 batch 一致性、浮点类型、有限值的完整检查 |
| Docker 超时受控 | 有 subprocess timeout | 未发现容器超时清理测试 | **待核验**：超时未显式停止 Docker 容器 |
| 三专科不跨专科路由 | `TOOLS_BY_SPECIALTY`、`_require_tool`、会话专科分支 | assistant | **一致** |
| 模型适配独立、同意后复检 | `apply_adapt`、AST 不变性检查、重新入队 | adapt | **一致** |
| RAG 只访问 ippilab | `collection_name` 在建立客户端前拒绝其他集合 | kb_milvus | **一致** |
| RAG 阈值／召回／缓存规则 | 0.48／0.45、24→5、TTL 600 有代码 | kb_milvus、assistant | **一致**；远程实际条数、索引和可用性待核验 |
| 新场景禁用与路由正确 | scenes 服务、前端路由和禁用按钮 | scenes；部分前端为静态断言 | **一致**；本次未进行浏览器验收 |
| 结果可追溯 | 模型哈希、版本、预处理及结果记录存在 | G、E、F 部分覆盖 | **存在差异**：已引用上传批次仍可覆盖掩码 |
| 首页及金相样式应保护 | hero 原文及 token 存在 | home catalog 有部分静态检查 | **源码确认** |
| 历史 5 passed、服务健康、437 条语料 | 当前源码不能证明历史执行结果或远程现态 | 交接记载 | **仅文档记载，本次未复验** |

安全反序列化补充：  
[ckpt.py:24](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/packages/admit/ckpt.py:24) 优先使用 `weights_only=True`，但 `TypeError` 后回退到没有显式指定该参数的加载方式。适配服务在 API 进程调用此函数读取 checkpoint 元数据。**回退分支存在是源码事实；当前安装版本是否触发及其具体行为待核验，不能概括为所有环境下都无条件安全。**

## D. 核心业务链路与风险

### D.1 公开演示

已确认的保护包括：

- 单独的样例、模型、提交和结果 API。
- 内置模型来源及白名单检查。
- 样例含 mask 时拒绝。
- Worker 再次检查协议，禁止学生模型和 GT。
- 不写 `MetricSet`，前端不请求精度。
- Redis Lua 对 IP 和会话同时检查限额。

主要风险是**提交成功语义与入队不一致**：限额预约、数据库提交成功后，入队异常未落在释放限额的异常块中。因此可能出现没有进入队列却消耗演示次数的情况，见 F.3。

### D.2 实验台对照

图片与掩码分别上传；掩码检查包含配对、尺寸及类别值验证。只有全部样本有掩码才设置 `has_gt=True`。

主要问题：

- baseline 参数缺少模型来源／可见性检查，见 F.1。
- `create_compare_task` 排除 demo 数据，却没有限定必须是上传批次；固定测试集也可能经 compare 使用。
- 已创建任务关联的掩码仍可覆盖，见 F.4。
- [CompareTaskView.vue:292](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/web/src/views/compare/CompareTaskView.vue:292) 的首次刷新和轮询没有局部异常处理。网络失败后的实际提示及恢复体验需浏览器核验；本次不将其列为首要任务。

### D.3 正式评测

API 拒绝上传批次、非固定集和缺 GT 数据；Worker 对全体样本计算指标，拼图按排序抽样。

但需要区分：

- **现有 seed 配置是 NEU-20**。
- **API 的约束是任意符合属性的 preset fixed test**。

若未来登记新的固定集，现有断言可能自动接受它，而页面仍写 NEU-20。新增数据登记时必须保留当前评测边界。

GT 专用下载接口的 403 是有效保护，但结果生成和下载路径另有缺口，见 F.2。

### D.4 学生模型导入与执行

生产调用链使用 Docker，严格加载权重，检查阶段可以记录为 static／import／build／load／forward／shape 等。

需要保留的准确表述：

- 静态扫描是前置过滤，不等于完整安全证明。
- runner 当前形状验证只覆盖部分输出契约。
- 学生推理失败先被拼成 `RuntimeError`，再由 Worker 按异常文本重新分类，原始 `fail_stage` 不一定完整保留。例如资源阶段不总能从文本准确恢复。
- 容器 timeout 后的资源清理没有明确实现，见 F.5。
- checkpoint 安全兼容分支需要核验；这与 `strict=True` 是两类不同问题。

### D.5 科研助手

专科白名单、会话归属、demo 拒绝、确认后执行等约束都有代码支持。

另有权限口径差异：

- 普通任务 API 的 `_can_view_task` 允许导师查看任务。
- 科研助手的 `can_analyze_task` 对导师要求任务已提交。

这不直接证明错误，但文档不能把“任务可见”和“助手可分析”描述成完全相同的权限条件。

已知历史窗口截断问题仍存在。没有证据表明应因此重做 RAG 或引入多智能体框架。

### D.6 模型适配助手

修改范围、本人权限、同意流程、AST 不变性和复检均有实现及测试代码。

主要边界：

- 它会在 API 进程读取 checkpoint 元数据，但不会 import 学生 `.py`。
- 源码写入、数据库状态更新和入队不是一个原子操作。
- 入队失败可能留下已经修改源码但持续 `checking` 的版本，属于 F.3 的同类问题。

### D.7 场景入口

当前代码符合本轮目标：

- 侧栏按三个场景组织。
- 钢铁页三方向切换。
- PCB／光伏空页。
- API 独立鉴权和固定拒绝。
- 旧路由跳转保留结果页。

**未接入 PCB、光伏、检测和分类不是近期缺陷。** 本次不建议改变其禁用状态。

## E. 测试与回归策略

### E.1 现有测试分类

| 测试文件 | 主要覆盖 | 运行依赖与注意事项 |
|---|---|---|
| [test_static_scan.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_static_scan.py) | AST 导入与危险调用过滤 | 逻辑单测，读取受控 fixture |
| [test_metrics_policy.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_metrics_policy.py) | 无 GT、缺指标 payload 不补零 | 逻辑单测 |
| [test_preprocess.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_preprocess.py)、[test_overlay_alpha.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_overlay_alpha.py) | 预处理确定性、尺寸、叠加规则 | 本地数值计算 |
| [test_slice_c.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_slice_c.py)、[test_slice_e.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_slice_e.py)、[test_slice_f.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_slice_f.py) | 模型分组、下载包名称、掩码、指标、固定集属性规则 | 主要为函数／对象级测试；不等同于真实 Worker 链路 |
| [test_slice_d.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_slice_d.py) | API 不出现 runner import 等字符串 | 静态文本检查，不证明 Docker 运行行为 |
| [test_admit_runner.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_admit_runner.py) | tiny 模型加载和失败阶段 | 写临时文件、生成测试权重、启动宿主 Python 子进程并前向；不是 Docker 验收 |
| [test_builtin_baselines.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_builtin_baselines.py) | 内置集合、排序、权重加载与前向 | 混合 SQLite 内存测试和真实 CPU 模型测试 |
| [test_slice_gradcam.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_slice_gradcam.py) | CAM、目标层、归一化 | PyTorch 前向及梯度计算；不是训练，但本次也未执行 |
| [test_slice_perf.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_slice_perf.py) | 测参协议、入队、档案 | 混合 SQLite、mock 和 CPU 前向；直接执行受控 runner |
| [test_slice_scatter.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_slice_scatter.py) | 散点图尺寸、配色、输出格式 | 本地绘图 |
| [test_slice_g.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_slice_g.py) | 记录、归档、提交、再跑、同学隔离 | SQLite 内存库；队列／部分 Redis 调用 mock |
| [test_slice_h1.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_slice_h1.py)、[H2](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_slice_h2.py)、[H3](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_slice_h3.py)、[H4](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_slice_h4.py) | 账号、演示目录、协议、授权、限额 | SQLite／内存限额／mock；H3 部分只检查源码字符串 |
| [test_slice_h5.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_slice_h5.py)、[H6](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_slice_h6.py) | 前端演示接口纪律、文档与冒烟内容 | 静态检查居多，不是浏览器测试 |
| [test_slice_data.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_slice_data.py)、[test_slice_home_catalog.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_slice_home_catalog.py) | 数据目录、分页、归属、首页目录 | SQLite 内存库，部分临时文件 |
| [test_slice_adapt.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_slice_adapt.py) | 拒绝不改、只改适配层、变体选择、权限、复检状态 | SQLite、临时源码、队列 mock；部分提案禁用或模拟 LLM |
| [test_slice_assistant.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_slice_assistant.py) | 专科隔离、确认、上下文、引用复用、流式响应 | SQLite；多数写作／队列被 mock，但学术检索并非统一隔离 |
| [test_kb_milvus.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_kb_milvus.py) | 集合限制、召回整理、阈值、embedding 缓存 | 关键客户端被 fake／mock；不同于真实远程验收 |
| [test_scenes_empty.py](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/tests/test_scenes_empty.py) | 登录、场景状态、409、404、无指标字段 | 独立 FastAPI TestClient，依赖覆盖，无真实入队 |

### E.2 执行前必须知道的副作用

1. 配置类默认读取本地环境文件。即使测试使用 SQLite，也不意味着导入阶段完全隔离配置。
2. 助手测试的自动 fixture 关闭写作模型，但未统一替换 `retrieve_kb`；配置了远程检索时，部分用例可能连接 Milvus、embedding 和 Redis。
3. [main.py:17](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/main.py:17) 的 lifespan 可创建存储目录并执行 seed。启动 API 或启用其生命周期不是纯读取。
4. [smoke_h.py:44](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/scripts/smoke_h.py:44) 会删除演示限额 key，并创建账号／任务。
5. 其他业务 smoke 脚本会上传、创建任务、推理或测参；`smoke_llm` 会请求外部模型。
6. pytest 自身也可能创建缓存、临时文件和字节码。

因此，本轮不运行任何测试是合理且必要的。

### E.3 明显缺少的回归证据

在已检查测试中，未找到以下完整行为覆盖：

- 将私有学生版本放入 `baseline_version_ids` 时拒绝。
- 任务下载拒绝内部学生源码、权重和执行目录。
- 固定集 GT 限制同时覆盖单文件、bundle、compare 和 eval。
- 缓存异常、入队失败后的数据库状态及演示限额补偿。
- 已被任务引用的批次禁止覆盖掩码。
- Docker 超时后确实无残留容器。
- 输出 batch／dtype／NaN／Inf 契约验证。
- 新场景页面的自动浏览器回归。
- 实际 MySQL／Redis／Docker 整体链路的故障恢复自动化。

当前前端 package scripts 只有 dev、build、preview，未发现已配置的 Vitest／Playwright 测试入口。静态 Vue 文本断言不能替代页面行为测试。

### E.4 后续验证建议

| 修改类型 | 优先验证 | 条件 |
|---|---|---|
| 参数鉴权／制品下载 | 新增 SQLite＋独立 TestClient 回归；再跑 G、assistant、场景相关用例 | 临时存储、无真实队列、禁止外部网络调用 |
| GT 策略 | E、F、data，加上固定集文件和 bundle 测试 | 先明确产品允许展示哪些派生 GT |
| 入队失败处理 | 用 fake 队列／缓存注入故障，检查状态和限额 | 不需要真实推理；再在专用环境验证 Redis 故障 |
| 掩码冻结 | 上传 API 与 TaskSample 引用测试 | 使用临时目录及内存库，增加并发条件验证 |
| Docker 生命周期 | 命令构造单测＋受控超时容器测试 | 明确授权使用 Docker 和资源预算 |
| 场景导航 | scenes 用例＋登录、跳转、禁用状态浏览器检查 | 独立测试环境，不能自动启动当前业务服务 |

## F. 建议优先处理的问题

以下最多五项，均为讨论候选，不代表开发授权。

### F.1 高优先级：模型入队权限与任务文件访问边界不完整

**问题描述**

实验台 baseline 参数只检查版本存在、可运行及 CPU 条件，没有确认其来源为内置模型，也没有检查该分支的模型归属。任务文件接口则允许读取任务目录中任意符合路径校验的文件。

**代码证据**

- [tasks.py:86](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/services/tasks.py:86)：baseline 循环缺少来源与可见性判断。
- 同函数学生参数分支在 115～119 行有对应检查，说明两条路径不一致。
- [jobs.py:337](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/worker/jobs.py:337)：按真实 `Model.source` 选择学生执行路径，不按 baseline 角色拒绝。
- [student_exec.py:135](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/worker/student_exec.py:135)：源码和权重复制／链接进入任务内部目录。
- [routers/tasks.py:89](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/routers/tasks.py:89)：文件读取未检查 Artifact 白名单。

**实际影响**

在调用者已知另一学生可运行版本 ID、且协议兼容的前提下，存在绕过模型使用权限的代码路径；结合任务内部文件下载，还可能扩大到源码和权重暴露。没有进行实际越权请求。

**原因及确定性**

权限检查只放在 `student_version_id` 分支，文件授权只检查任务级权限。缺口由源码直接确认，实际数据暴露情况未知。

**最小修改范围**

统一模型角色校验；baseline 必须是内置模型。下载只允许明确登记且获准公开的制品，排除学生执行目录。

**验收方式**

验证他人私有版本、本人学生版本作为 baseline 均被拒绝；合法内置 baseline 和获授权学生模型仍可运行；内部文件不可下载，正常图层和 bundle 不受影响。

**风险与回退**

收紧文件白名单可能影响当前 UI 引用的制品，需要覆盖全部合法种类。回退应回退实现版本并保留受限访问措施，不能以重新开放任意内部文件作为长期回退。

**用户决策**

恢复已有权限约束无需重定产品；若“共享模型”是否允许下载源码／权重尚无明确政策，需要负责人确认。

### F.2 高优先级：固定测试集 GT 限制未覆盖派生结果

**问题描述**

专用 GT 接口拒绝学生下载，但 Worker 为有 GT 任务生成独立彩色 GT 图层，并纳入下载包。固定集也可通过 compare 进入全量可视化路径。

**代码证据**

- [datasets.py:87](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/routers/datasets.py:87)：专用 GT 下载限制。
- [jobs.py:314](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/worker/jobs.py:314)：生成、登记彩色 GT。
- [jobs.py:58](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/worker/jobs.py:58)：bundle 包含 `gt` 目录。
- [tasks.py:209](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/services/tasks.py:209)：compare 排除 demo，但未排除固定测试集。

**实际影响**

“不能下载原始 GT 接口”不等于“不能获得固定集标签内容”。彩色类别图保存了标签信息，与严格固定集保密目标存在冲突。

**原因及确定性**

指标／图层生成共用 `has_gt` 条件，没有结合数据版本 GT 权限。行为源码已确认；它是否超出负责人原本允许的可视化范围需要明确。

**最小修改范围**

先统一固定集展示政策，再约束 compare 数据入口、制品生成／下载及 bundle。保留用户自有 GT 对照能力。

**验收方式**

学生与导师分别检查固定集单文件、拼图、bundle 和 compare 入口；确保指标仍真实计算，用户自有掩码对照仍正常。

**风险与回退**

直接移除所有 GT 展示可能违背已有评测展示要求，应先定义允许范围。存量制品如何处理需单独决定，不建议自动删除。

**用户决策**

**需要。** 必须明确“禁止 GT 下载”是否包含独立彩色 GT、包含 GT 的拼图以及错误图等派生结果。

### F.3 高优先级：任务已落库但未入队时缺少一致的失败处理

**问题描述**

compare／eval／demo 和导入／适配流程先提交数据库，再进行缓存和入队操作。后续异常可能留下持续 queued／checking 的记录。

**代码证据**

- [tasks.py:248](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/services/tasks.py:248)、316：提交后失效缓存并入队。
- [demo.py:220](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/services/demo.py:220)：限额释放仅覆盖数据库构建异常，入队在异常块外。
- [import_model.py:211](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/services/import_model.py:211)：checking 提交后入队。
- [adapt.py:305](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/services/adapt.py:305)：同类顺序。
- 对照实现：[perf.py:135](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/services/perf.py:135) 已对入队失败回写 failed，可复用其思路。

**实际影响**

用户看到提交失败，但记录仍显示排队；演示可能扣次数却未运行。Redis 重启时，当前 Compose 又关闭了 Redis 持久化，队列与数据库的差异更需要明确恢复机制。

**原因及确定性**

跨 MySQL／Redis 操作无统一补偿，源码确认。是否已有线上残留任务未核验。

**最小修改范围**

先统一明确入队失败的处理：缓存故障不阻断关键业务、失败回写、演示额度补偿、稳定关联任务与队列标识。不必立即引入新架构。

**验收方式**

注入缓存异常、确定的入队失败和入队响应不确定场景，检查数据库状态、限额、返回值和重复提交行为。

**风险与回退**

“入队已成功但响应丢失”不能当作确定失败盲目重试，需要幂等策略。先处理明确失败，再讨论自动恢复；避免无条件重跑已有任务。

**用户决策**

基本一致性修复符合既有目标；自动重试次数、超时恢复和是否补偿额度需要确定规则。

### F.4 中高优先级：已引用批次仍可覆盖掩码，影响实验追溯

**问题描述**

掩码上传允许反复覆盖同一批次文件，没有检查该数据版本是否已被 queued／running／completed 任务引用。

**代码证据**

- [uploads.py:136](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/routers/uploads.py:136)：验证归属和批次种类。
- [uploads.py:204](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/api/app/routers/uploads.py:204)：写回相同掩码文件路径。
- [jobs.py:273](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/worker/jobs.py:273)、305：执行时读取当前 Sample 和当前掩码文件。
- [jobs.py:522](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/worker/jobs.py:522)：任务清单未保存掩码内容哈希。

**实际影响**

排队期间更换掩码可能改变即将计算的指标；完成后更换掩码会让“同配置再跑”采用不同标注，削弱可复现性。

**原因及确定性**

TaskSample 关联可变 Sample，上传端没有引用冻结检查。源码确认；未制造实际数据变更。

**最小修改范围**

优先考虑数据版本一旦被任务引用就禁止原地补写／覆盖；修正标注使用新批次。补充掩码哈希及任务快照时应保持范围克制。

**验收方式**

未引用批次仍可正常配对；引用后上传被拒绝；并发提交与补掩码不能绕过冻结；历史结果及再跑规则明确。

**风险与回退**

可能改变当前“事后补掩码”的操作习惯。需要提示用户创建新批次，不能自动迁移或覆盖历史数据。

**用户决策**

需要确认冻结时点及修正标注流程；底层目标与需求中的版本不可原地修改一致。

### F.5 中优先级：Docker 超时后未显式清理容器

**问题描述**

超时处理只抛出 `DockerUnavailable`，未记录容器 ID，也未显式 stop／kill／rm。

**代码证据**

[dockerutil.py:108](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/packages/admit/dockerutil.py:108) 的超时分支没有容器清理；`--rm` 仅用于容器退出后的删除。

**实际影响**

Docker 客户端调用结束不应被直接视为容器内任务已终止。若容器继续运行，可能持续占用 CPU／内存并写入输出目录。

**原因及确定性**

缺少显式生命周期管理是源码事实；当前 Docker Desktop 环境是否出现残留、残留持续多久，**待运行核验**。

**最小修改范围**

为本次容器生成可追踪身份，在超时及异常路径只清理该容器，并记录清理结果。

**验收方式**

在专用环境用受控超时 fixture 验证：请求返回失败后容器已停止、输出不再变化，其他任务容器不受影响。

**风险与回退**

清理必须限定到当前任务容器；禁止使用全局 prune。清理失败时保留可诊断信息，不伪报已释放资源。

**用户决策**

实现方向不改变产品范围；实际 Docker 故障验证需另行授权并确定资源预算。

## G. 尚需补充的信息

1. **固定集 GT 政策**：允许哪些可视化，禁止哪些下载，如何处理已有结果包。
2. **导师与共享模型权限**：导师直接查看未提交任务是否符合预期；共享是否包括源码／权重下载。
3. **实际数据状态**：是否存在多个 preset fixed test、异常 queued／checking 记录、重复或已覆盖掩码。需另行授权检查数据库。
4. **运行环境**：实际 Python、PyTorch、RQ、Docker 版本及资源配置；本次未读取运行环境或敏感配置。
5. **checkpoint 回退行为**：当前版本下 `TypeError` 回退的实际含义及是否应直接拒绝。
6. **部署恢复能力**：Redis 丢队列、Worker 重启、容器超时、磁盘满及数据库不可用后的实际行为。
7. **生产防护**：反向代理、上传限制、TLS、备份恢复、监控与发布流程，本次源码阅读不能确认实际部署状态。
8. **测试隔离程度**：后续执行助手和适配测试前，应明确阻断环境配置读取、远程检索和模型 API。
9. **前端实际表现**：轮询失败、旧路由参数保留、页面切换及下载错误反馈需要独立浏览器验证。
10. **历史验证结果**：交接中的成功记录可作背景，但需要按具体修改重新验收，不能用来证明当前完整工作区通过测试。

需要优先保护的现有实现包括：

- [HomeView.vue:8](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/web/src/views/HomeView.vue:8) 的 hero 原文。
- [tokens.css:1](F:/360MoveData/Users/40336/Desktop/Bofang/Steel_lab/apps/web/src/styles/tokens.css:1) 的金相 token。
- 当前场景导航和全部未提交改动。
- 分割、演示和评测协议及已收口 RAG。

## H. 推荐的下一步

**最值得优先讨论的切片：实验台模型入队鉴权与任务制品下载边界收口。**

选择它的原因：

- 有明确、连续的代码证据。
- 涉及已有学生模型私有性和文件访问边界。
- 不依赖新权重、新数据集、GPU 或外部服务。
- 可复用现有模型来源判断、可见性函数和 Artifact 数据。
- 能先用 SQLite、临时目录和 fake 队列验证，不需要真实推理。
- 不改变首页、场景导航、RAG 或算法任务范围。

建议讨论范围限定为：

1. baseline 参数严格限定内置模型。
2. 学生模型统一验证可见性和可运行状态。
3. 任务文件接口仅开放允许的结果制品，阻断内部执行文件。
4. 补充跨用户、模型角色及文件类别的回归用例。
5. 保持合法对照、正式评测和公开演示行为不变。

固定集 GT 派生结果政策可同时形成待决问题，但在负责人明确前，不应擅自删改既有可视化。

**以上仅为审查结论和后续建议。审查阶段没有修改代码、执行测试或提交 Git；本文件是在用户随后明确要求下保存的报告，不代表自动开始任何开发任务。**
