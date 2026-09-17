# 课题组工业缺陷分割科研网站（第一版：Slice A–F）

常驻 CPU 网站：学生在 AutoDL 训完后把权重拿到本站，与内置 baseline 在同一批图上对照分割效果。网站不做训练。

## 第一版当前范围（A–F）

- 可启动：MySQL 8 + Redis、FastAPI、Vue 路由壳、种子账号
- AC-01：内置 UNet / DeepLabV3+ / UNet++ 对无 GT 图推理，出原图 / 彩色掩码 / 叠加 / 拼图；无 GT 不返回、不渲染精度
- 工作台、模型中心、鉴权下载图层包（拼图 + 单层 PNG + task.json）
- 学生导入：单个 `.py` + `.pth`，静态扫描 + Docker 隔离检查；失败为不能启动并带 `fail_stage`
- AC-04：全部图片配对掩码后，在原图显示尺寸上给出本批 mIoU / mDice / 逐类 IoU（参考指标，不代表完整测试集）；图层包可含 `gt/`、`error/`，仍不含 `metrics.json` / PDF
- 正式评测：仅预置 **NEU-20**（固定测试集，学生不可下载 GT）。全量 20 张计算 mIoU / mDice / 逐类 IoU；Acc 只出现在详情，不作为主指标。拼图按文件名排序抽取 8 张。NEU-20 不是论文完整 test split
- 结果记录：后续切片

## 仓库结构

```text
apps/web/          Vue 3 + Vite + TypeScript + Element Plus
apps/api/          FastAPI
apps/worker/       RQ SimpleWorker（内置模型进程内；学生模型 Docker）
packages/infer/    复用 third_party 的加载 / 预处理 / 着色 / 拼图
packages/admit/    学生源码静态扫描与隔离 runner（仅容器/子进程调用 runner）
deploy/            MySQL8 + Redis；student.Dockerfile 隔离镜像
assets/            已有 NEU 权重与 20 对样例（不要塞进 Redis）
third_party/       已有网络结构与工具（不要整份复制改写）
```

## 环境

- Python 3.11
- Node 20（仅前端）
- Docker Desktop（MySQL 8 + Redis；学生 `.py` 检查/推理走 `steel-lab-student:cpu`）
- 本机 PyTorch CPU 轮

compose 将 MySQL 映射到 **宿主机 3307**（避免与本机已有 3306 冲突），Redis 仍为 6379。若要改端口，同步改 `.env` 里的 `MYSQL_DSN`。

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

alembic -c apps/api/alembic.ini upgrade head
python scripts/seed.py

# 终端 1
uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000 --reload

# 终端 2
python -m apps.worker

# 终端 3
cd apps/web
npm install
npm run dev
```

浏览器：http://127.0.0.1:5173（若端口占用则看 Vite 打印的 5174，请用 `localhost`）  
本地种子账号（密码只写在 `.env.example` / `.env`）：`advisor` 与 `student`。

Worker 使用 RQ **SimpleWorker**：不 fork，L1 能缓存已加载的内置 `nn.Module`，并兼容 Windows。FastAPI / Worker **不得** `import` 学生 `.py`。

学生插件契约：单文件提供 `build_model(num_classes, in_channels=3, **kwargs)` 或表单指定的 `nn.Module` 类；`forward` 主输出为 `B×C×H×W` logits。

## 用 curl 验证 AC-01（无浏览器时）

三个进程都起来后：

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

## 硬性约束（已落实）

- 无 `/train`，不调用 `train.py` / `train_multi.py`
- Web 进程不 `import` 学生 `.py`；学生检查/推理在 Docker（`--network=none`，只读代码/权重）
- PNG / `.pth` / 原图不进 Redis；任务终态在 MySQL
- DeepLab 构建 `pretrained=False`；checkpoint 优先 `model_state`；学生权重 `weights_only`
- 对比写入 `PreprocessSpec`（默认 200×200 CLAHE/椒盐），禁止静默改尺寸
- 检测 / 分类页按钮 disabled；科研助手无 API Key 时显示不可用
