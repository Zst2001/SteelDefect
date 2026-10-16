# 课题组工业缺陷分割科研网站

[智能感知与精密工业检测实验室](https://github.com/Zst2001/SteelDefect)（江西师范大学人工智能学院 · IPPI Lab）的双面常驻 CPU 网站：对外是展示门户（免登录首页 + 公开演示），对内是学生实验台（AutoDL 训完导入权重，与内置 baseline 对照、评测）。**网站不做训练。**

当前真任务只有 **钢铁表面缺陷语义分割**。目标检测 / 缺陷分类侧栏可点，但是占位页，不能提交真实任务。快照标签：`zst261016`。

## 当前范围

### 展示面（H0–H6）

- 免登录首页：实验室身份 **智能感知与精密工业检测实验室 / IPPI Lab**；展台图来自公开演示预备样例，须标明不是模型输出
- 侧栏「公开演示」进 `/demo`；预备样例 NEU-20 全 20 张可点选（每次 1–5 张）
- 内置模型：UNet / DeepLabV3+ / UNet++ / BiSeNet / DANet / PSPNet / SegFormer（演示与快速对比每次 1–3 个）
- 访客 24 小时内同一 IP ∧ 浏览器会话成功入队 3 次；超限「明日再试或登录」，登录后不计这 3 次
- 只出原图 / 掩码 / 叠加 / 拼图；**不算、不展示 Acc / mIoU / mDice**
- 关闭公开注册；学生账号由导师开通
- 登录用户进 `/demo` 仍走公开演示协议（F-DEMO），不是快速对比
- 首页 hero 长文保持仓库中的原文（含「实验室现未来将…」），不要擅自改写

### 实验台（Slice A–G）

- 可启动：MySQL 8 + Redis、FastAPI、Vue、种子账号
- 无 GT 图：内置 CPU baseline 出原图 / 彩色掩码 / 叠加 / 拼图；无 GT 不返回、不渲染精度
- 工作台、模型中心、鉴权下载图层包（拼图 + 单层 PNG + task.json）
- 学生导入：单个 `.py` + `.pth`，静态扫描 + Docker 隔离检查；失败为不能启动并带 `fail_stage`
- 全部图片配对掩码后，给出本批 mIoU / mDice / 逐类 IoU（参考指标，不代表完整测试集）
- 正式评测：仅预置 **NEU-20**（学生不可下载 GT）。全量 20 张算指标；Acc 只出现在详情。拼图抽 8 张。NEU-20 不是论文完整 test split
- 结果记录：本人对比 / 评测 / 演示档案；对比 / 评测可提交导师（演示不可提交）；同学互不可见
- 内置模型 Grad-CAM（学生模型第一版不算）；模型测评（本机 CPU 参数量 / 前向 ms / 换算 FPS）；性能散点图
- 模型适配助手：仅在导入失败时出现；同意后改适配层，不改原 class、不放宽权重加载

### 科研助手（须登录）

侧栏「科研助手」→ `/assistant`。一块对话画布 + 输入框旁专科选择器（学术 / 分割 / 模型）。同一会话可追问并带上下文；换专科开新线程。禁止多智能体框架，禁止一个输入框自动路由。

- **分割：** 分析本人可见的对比 / 评测（拒绝 demo）；确认后可封装快速对比
- **模型：** 调用实验室测参；源码建议只出文本，不写盘（写盘仍走模型适配助手）
- **学术：** 按审定语料检索增强生成。远程 Milvus 只允许集合 **`ippilab`**（结构切块，COSINE ≥ 0.48），不读 `paper_literature`。本仓库不部署向量库。未命中拒答，不编 DOI。向量库不可用时回退本站审定短条目
- 无 `LLM_API_KEY` 时：证据 / 命中 / 测参档案仍开，写作关，不编造指标

产品说明：`docs/科研助手产品说明.md`、`docs/学术RAG需求说明书.md`、`docs/模型适配助手产品说明.md`。需求书：`docs/课题组网站需求分析书.md`（v3.1.1）。

## 仓库结构

```text
apps/web/          Vue 3 + Vite + TypeScript + Element Plus
apps/api/          FastAPI（含科研助手 / 学术检索）
apps/worker/       RQ SimpleWorker（内置模型进程内；学生模型 Docker）
packages/infer/    复用 third_party 的加载 / 预处理 / 着色 / 拼图 / Grad-CAM
packages/admit/    学生源码静态扫描与隔离 runner（仅容器/子进程调用 runner）
deploy/            MySQL8 + Redis；student.Dockerfile 隔离镜像
assets/            已有 NEU 权重与 20 对样例（不要塞进 Redis）
docs/              需求书、产品说明、学术 RAG、交接、审定语料 docs/kb/
scripts/           种子、冒烟、知识库重建 index_kb.py
third_party/       已有网络结构与工具（不要整份复制改写）
```

## 环境

- Python 3.11
- Node 20（仅前端）
- Docker Desktop（MySQL 8 + Redis；学生 `.py` 检查/推理走 `steel-lab-student:cpu`）
- 本机 PyTorch CPU 轮
- 学术检索另需：`.env` 里的 `MILVUS_URI` / `MILVUS_TOKEN`（远程实例，集合名必须是 `ippilab`）以及火山方舟 `LLM_API_KEY`

compose 将 MySQL 映射到 **宿主机 3307**（避免与本机已有 3306 冲突），Redis 仍为 6379。若要改端口，同步改 `.env` 里的 `MYSQL_DSN`。

密钥只写在仓库根目录 `.env`（已 gitignore）。`.env.example` 只留空变量名，不要把真实 Key / Token 提交进 Git。

构建学生隔离镜像（首次导入前）：

```powershell
docker build -f deploy/student.Dockerfile -t steel-lab-student:cpu .
```

## 启动

在仓库根目录 PowerShell：

```powershell
copy .env.example .env

docker compose -f deploy/docker-compose.yml --env-file .env up -d

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install timm

alembic -c apps/api/alembic.ini upgrade head
python scripts/seed.py

# 终端 1
uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000 --reload

# 终端 2
python -m apps.worker

# 终端 3
cd apps/web
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

浏览器：http://127.0.0.1:5173（Vite **必须** `--host 127.0.0.1`，否则容易只绑 IPv6）  
健康检查：http://127.0.0.1:8000/api/health ，期望 `mysql` / `redis` / `docker` / `student_image` 为 true。  
本地种子账号（密码只写在 `.env.example` / `.env`）：`advisor` 与 `student`。  
访客打开 http://127.0.0.1:5173/demo 即可点选预备样例；实验台与科研助手须登录。

Worker 使用 RQ **SimpleWorker**：不 fork，L1 能缓存已加载的内置 `nn.Module`，并兼容 Windows。FastAPI / Worker **不得** `import` 学生 `.py`。

学生插件契约：单文件提供 `build_model(num_classes, in_channels=3, **kwargs)` 或表单指定的 `nn.Module` 类；`forward` 主输出为 `B×C×H×W` logits。导入失败时，模型卡上的**模型适配助手**可对入口 / 构造参数 / 多路输出第 1 项 / checkpoint `model_name` 对应的已有消融变体做适配（同意后改当前版本的适配层并复检；不改原 class、不放宽权重加载）。

大模型：在 `.env` 填 `LLM_API_KEY`，默认火山方舟 `LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3`，写作 `LLM_MODEL=deepseek-v4-1-flash-260910`，向量化 `LLM_EMBED_MODEL=doubao-embedding-vision-251215`（1024 维）。`DASHSCOPE_API_KEY` 仍可作备用。集合名 `MILVUS_COLLECTION_NAME=ippilab`，不要改成其它集合。

审定语料变更后重建索引（只写 `ippilab`，约数分钟）：

```powershell
.\.venv\Scripts\python.exe scripts\index_kb.py
```

## 验收冒烟（API + Worker 已启动）

公开演示 AC-10～AC-13（脚本会清本地 `lab:demo:*` 限额 key，以便复测 3 次窗口）：

```powershell
python scripts/smoke_h.py
```

期望：免登录目录 20 张、入队可视化、`/metrics` 对 demo 为 404 `DEMO_NO_METRICS`、图层包无 `metrics.json`；第 4 次 429 `DEMO_QUOTA`；清 Cookie 同 IP 仍拒；登录后可再入队；访客上传/对比 401；`POST /auth/register` 403；导师可开通学生。

实验台 AC-01（无 GT 对比）：

```powershell
python scripts/smoke_ac01.py
```

期望：

1. `GET /api/health` 中 mysql / redis 为 true
2. 上传 `assets/samples/neu/images` 中 2 张图（不传掩码）
3. 选择 1–3 个 runnable 内置模型创建 `POST /api/tasks/compare`
4. 任务进入 `success` 或 `partial_success`
5. `GET /api/tasks/{id}/metrics` 为 `{"available": false}`，不含 miou/dice/acc
6. `GET /api/tasks/{id}/bundle` 返回 zip（拼图 + 单层 PNG + task.json，无 PDF）

工作台与模型卡：

```powershell
python scripts/smoke_c.py
```

学生导入：

```powershell
python scripts/smoke_d.py
```

静态扫描失败应立即 `cannot_start` / `fail_stage=static`。镜像与 Worker 就绪时，合规 Tiny 模型应进入 `runnable`。

有 GT 参考指标（AC-04）：

```powershell
python scripts/smoke_e.py
```

配对掩码后 `GET /api/tasks/{id}/metrics` 应为 `available: true` 且含真实 mIoU；同一流程不传掩码仍为 `{"available": false}`。固定测试集 GT 下载：学生调用 `GET /api/datasets/{id}/gt/{sample_key}` 应 403（`GT_FORBIDDEN`）。

正式评测（NEU-20 全量指标 + 8 张抽样拼图）：

```powershell
python scripts/smoke_f.py
```

`POST /api/tasks/eval` 仅接受 `eval_ready` 的预置固定测试集。上传批次应返回 `EVAL_DATASET_FORBIDDEN`。评测成功后 `scope=official_split`、`n=20`，图层包仍不含 `metrics.json` / PDF。

数据集中心（须登录）：列表只返回摘要；详情按页预览原图。把完整 NEU 的 `images/` 与 `masks/` 放到 `assets/datasets/neu`（或 `.env` 的 `NEU_FULL_ROOT`）后重启 API，卡片会显示张数，但 **不能** 进入正式评测。不要用网页一次选几千张文件。

单测（含展示面 H1–H6、助手与学术检索，不需 Worker；学术检索单测若本机已配 `.env` 会打到远程 `ippilab`）：

```powershell
python -m pytest tests/test_slice_h1.py tests/test_slice_h2.py tests/test_slice_h3.py tests/test_slice_h4.py tests/test_slice_h5.py tests/test_slice_h6.py tests/test_slice_g.py tests/test_slice_adapt.py tests/test_slice_data.py tests/test_slice_assistant.py tests/test_kb_milvus.py
```

## 硬性约束（已落实）

- 无 `/train`，不调用 `train.py` / `train_multi.py`
- Web 进程不 `import` 学生 `.py`；学生检查/推理在 Docker（`--network=none`，只读代码/权重）
- PNG / `.pth` / 原图不进 Redis；任务终态在 MySQL
- DeepLab / BiSeNet / DANet / PSPNet 构建 `pretrained=False`；checkpoint 优先 `model_state`；学生权重 `weights_only`
- 对比写入 `PreprocessSpec`（默认 200×200 CLAHE/椒盐），禁止静默改尺寸
- 检测 / 分类页按钮 disabled；科研助手无密钥时证据包 / 检索命中 / 测参档案仍开、写作关，不编造指标
- 公开演示不复用「上传 + 有 GT 出指标」的 compare 协议
- 学术检索只写集合 `ippilab`，禁止读/写同机其它文献集合；不要在本仓库 docker-compose 向量库
- 金相 UI token（近黑轨 / 钢蓝画布 / 氰标尺），不要另起浅色或玻璃拟态皮肤
