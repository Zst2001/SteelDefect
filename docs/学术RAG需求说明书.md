# 学术 RAG 需求说明书

文档状态：**需求已锁定，R0–R3 已编码，阈值已按金标校准**  
版本：0.2  
日期：2026-10-16  
范围：科研助手 **学术专科** 的检索增强生成  
上级：`docs/科研助手产品说明.md` v0.4；`docs/课题组网站需求分析书.md` v3.1.1 §8.9.4  
并列：写作 LLM 已切到火山方舟 `deepseek-v4-1-flash-260910`（OpenAI 兼容 Chat / SSE）

---

## 0. 相对上一稿的变更

上一轮分析（未落盘）建议：**不自建 pgvector / Milvus**，学术检索走百炼托管知识库，失败再回退本站审定短条目。

本轮导师提供了**远程 Milvus** 与火山方舟密钥，写作模型已切换。需求书 v3.1.1「不上自建 pgvector / Milvus」应理解为：**本仓库不 docker-compose 向量库**。使用导师已有的远程实例，不在本机再起一份 Milvus。

**2026-10-16 已拍板：**

1. **新建集合 `ippilab`**，不复用 `paper_literature` / `paper_literature_ug`。
2. **第一期语料只入库** `docs/kb/` 与现有 `SEED_DOCS` 短条目。PDF、上传稿、全库文献后置。
3. **第一期只做 1024 维稠密检索**（COSINE）。sparse / BM25 / 多向量后置。

编码同期再回写需求书与科研助手产品说明：学术主通道改为 **火山方舟向量化 + Milvus `ippilab`**，百炼 Retrieve 不再作为主路径。

---

## 1. 实测结论（2026-10-15）

未把密钥写入仓库。连通性与结构如下。

### 1.1 Milvus

| 项 | 实测 |
|----|------|
| 地址 | 导师提供的 `MILVUS_URI`（gRPC `:19530`）可达 |
| 鉴权 | `MILVUS_TOKEN` 为 `user:password` 形式，可列出集合 |
| `ippilab` | **已建**（2026-10-16 重建，437 条结构切块） |
| 同实例已有集合 | `paper_literature`（约 11 万条）、`paper_literature_ug`（约 1754 条） |

两份已有集合结构一致，明显是同一套「项目文献库」管道：

- 主键 `id`，稠密向量字段 `vector`，**dim = 1024**
- 索引：`AUTOINDEX` + **COSINE**
- `enable_dynamic_field = true`
- 动态字段含：`text` / `parent_text` / `chunk_level`（样本为 `child`）/ `parent_id` / `file_id` / `file_name` / `author` / `doc_type` / `page_label` / `section_path` / `parser=pymupdf` / `parser_version=md-struct-v5` / `visibility=PRIVATE` / `profile_id` / `source_url`（腾讯云 COS）
- 已是 **父子分块**（child 检索、parent 回填）

这就是导师说的「项目数据库」：不是本站 MySQL，而是同机 Milvus 上的文献切片库。`ippilab` 已由本站按 §5 新建并写入，不写入上述两份已有集合。

### 1.2 火山方舟

| 能力 | 实测 |
|------|------|
| Chat | `POST /api/v3/chat/completions`，模型 `deepseek-v4-1-flash-260910`，科研助手已走 SSE 流式 |
| 旧文本 embedding ID | `doubao-embedding-text-*` / `bge-large-zh` 对本密钥 **404**（未开通或已下线） |
| 当前可用向量化 | `POST /api/v3/embeddings/multimodal`，模型 **`doubao-embedding-vision-251215`** |
| 维度 | 请求 `dimensions=1024` 时返回 1024 维，与现有集合一致 |
| 响应形态 | `data` 是 **对象** `{embedding, object}`，不是 OpenAI 那种 `data[]` 列表 |

官方模型列表已把纯文本 embedding 迁到 `doubao-embedding-vision-251215`。换 embedding 必须重建向量，不能混用旧模型向量。

---

## 2. 要解决什么问题

学术专科现在只有：

1. 本站 `assistant_kb_docs` 五条短条目 + 关键词打分  
2. 可选百炼 Retrieve（密钥已不走百炼 Chat，索引也未作为主路径）

`docs/kb/` 里已有较长审定稿（学习路线、检测综述骨架），关键词检索盖不住语义问法（「研一从哪读」「检测和分割差在哪」「NEU-20 能不能写进论文 test split」）。

目标：学生在学术专科用自然语言提问，只根据**审定并入库的切片**回答，带来源；未命中则拒答，不编 DOI、不把公开演示 / catalog 说成本组成果。

---

## 3. 非目标（硬禁令）

1. 本仓库不部署 Milvus / pgvector / Elasticsearch。  
2. 不上 RAGFlow / Dify / LangChain / LlamaIndex 作为运行时。  
3. 不读、不写 `paper_literature` / `paper_literature_ug`。不把其中约 11 万条（含其他 `profile_id`、PRIVATE 文献）暴露给本站学生。  
4. 不联网抓未审定网页、顶刊全文、知网账号代下。第一期不解析 PDF、不做 OCR。  
5. 不跨专科：分割证据包、测参 FPS 不得写入学术检索上下文。  
6. 不因 RAG 改学生 `.py`、不放宽权重加载、不分析公开演示。  
7. Web 进程不 `import` 学生源码。  
8. 密钥不进 Git、不进接口回显、不进审计全文。

---

## 4. 锁定架构

```text
第一期语料（docs/kb/*.md + SEED_DOCS 短条目）
    → Markdown 父子分块
    → 火山方舟 multimodal embeddings（仅稠密，1024 维）
    → 新建 Milvus 集合 ippilab（COSINE）
    → 学术专科 kb.retrieve
         命中 → kb.answer（deepseek 流式，只根据 hits + 会话历史）
         未命中 → 拒答
MySQL assistant_kb_docs：短条目原文与语料清单
Redis：仅缓存 query embedding 与检索结果，不是知识源
短条目关键词检索：仅当 Milvus 不可用时回退，不是主通道
```

职责划分：

| 层 | 存什么 | 不存什么 |
|----|--------|----------|
| Milvus `ippilab` | 切片向量 + 可回显的 text/parent/来源字段 | 账号、会话、审计 |
| MySQL | 审定目录、会话、命中摘要、审计 | 向量 |
| Redis | embedding / 命中缓存（TTL） | 权威正文 |
| 火山方舟 | Chat + Embedding API | 本站语料原文 |

---

## 5. 集合（已锁定：新建 `ippilab`）

本站只创建并读写集合 **`ippilab`**。不查询、不插入 `paper_literature` 与 `paper_literature_ug`。

- 主键 `id`；稠密字段 `vector`，**dim = 1024**；metric **COSINE**；索引 AUTOINDEX（与同实例文献库一致，便于以后运维）。  
- 不建稀疏字段、不建 BM25 function、不建多向量字段。  
- `enable_dynamic_field = true`。动态字段：`text, parent_text, parent_id, chunk_level, file_id, file_name, section_path, source_label, category, slug, approved, parser`。第一期 `page_label` 可空（Markdown 无页码）。  
- 入库切片一律 `approved = true`。学生检索只搜本集合；若以后写入未审定切片，表达式必须带 `approved == true`。  
- 集合已存在且 dim / metric 不一致时拒绝写入，不删别人的集合，不静默重建错维索引。

---

## 6. 向量化与检索

### 6.1 Embedding

- 模型：`doubao-embedding-vision-251215`  
- 接口：`/api/v3/embeddings/multimodal`  
- 入库与查询用**同一** `dimensions=1024`。第一期不传 `instructions`；若以后启用，入库与查询必须成对。  
- **只取稠密向量 `embedding`。** 不请求 `sparse_embedding`、不请求 `multi_embedding`。  
- 解析响应按 **对象** `data.embedding`，不要按 OpenAI `data[0].embedding` 写死。返回长度不是 1024 则整批失败。

### 6.2 分块

三份调研稿不用固定字数滑窗。滑窗会把论文卡的 DOI 和推荐条件拆开，也会把表头和数据行拆开。检索用 child，回填给模型的 parent 不跨结构边界。每条 child 开头重复从文档标题到当前小节的 `section_path`。

| `block_type` | 切法 |
|--------------|------|
| `stage` | 学习路线的 `##` 阶段（第 1–11、14、15 节和附录）。超过约 1500 字时只在空行处再分，每块仍带该节检索关键词 |
| `paper_card` | `### 12.x` 一卡一块。短名、文献、DOI、前置阶段、推荐触发在同一块 |
| `table_row` | 表头加一行。推荐表、PRISMA、方法族、数据集、Gap、论文速查、排行榜都按行 |
| `reference` | 一条文献一块。作者、年份、题名、DOI 在一起 |
| `narrative` | 综述里的散文小节，一个 `###` 一块；没有 `###` 时用 `##`。过长只在段落边界切开。短条目也用这个类型 |

规则：

- 检索 child，写作使用对应 parent（去重后 top 3–5 parent）。  
- `file_name` 区分检测稿和分割稿，避免把分割排行榜数字当成检测结论。  
- 时间线代码块跟所在小节走，不从中间切开。  
- **第一期只切 Markdown**：`docs/kb/*.md` 与 `SEED_DOCS`。不解析 PDF，不做 OCR，不扫 `docs/kb` 以外的目录。  
- 不足约 20 字、只有分隔线、或只有「检索关键词」一行的碎片不入库。

### 6.3 检索

```text
用户问句
  → embed（1024 维稠密，与入库同一模型）
  → Milvus search(ippilab, anns_field=vector, metric=COSINE, limit=12)
  → 分数阈值（2026-10-16 金标校准后 COSINE ≥ 0.48）
  → 去重到 ≤5 条 parent
  → 低于阈值或 0 条 → hit=false，拒答
```

第一期不做查询改写，不做稠密与稀疏混排。

2026-10-16 对重建后的 437 条结构切块打了 10 条金标。应命中最低分 0.540，应拒答最高分 0.431，中间有空档。0.35 低于这条空档，「番茄叶片病害用什么数据集」会以 0.431 误命中分割稿的数据集表。阈值取空档中的 **0.48**。

| 问句 | 期望 | top | 文件 / 块 |
|------|------|-----|-----------|
| NEU-20 是不是论文完整 test split | 命中 | 0.617 | 写作与实验纪律 / narrative |
| 还不会 Python 该推荐哪篇论文 | 命中 | 0.544 | 学习路线 §13 / table_row |
| ResNet CVPR 2016 的 DOI 是什么 | 命中 | 0.594 | 学习路线附录 A / table_row |
| 分割排行榜的 mIoU 能不能当成检测的 mAP | 命中 | 0.540 | 检测稿 §6.1 Gap / table_row |
| Song 2013 热轧钢板表面缺陷图的 DOI | 命中 | 0.712 | 检测稿 §10 / reference |
| 小麦赤霉病遥感指数怎么计算 | 拒答 | 0.335 | 低于阈值 |
| 量子计算如何实现 Shor 算法 | 拒答 | 0.304 | 低于阈值 |
| 番茄叶片病害用什么数据集 | 拒答 | 0.431 | 低于 0.48；高于旧的 0.35 |
| 如何办理美国学生签证 | 拒答 | 0.246 | 低于阈值 |
| 北京今天会下雨吗 | 拒答 | 0.251 | 低于阈值 |

追问：「刚才 / 展开 / 那条」仍先检索；若新检索落空，允许复用**本会话已命中**的 hits（与现 CH-02 一致），不得用模型记忆补文献。

### 6.4 生成

- 继续 `kb.answer` + 现有 `SYSTEM_KB` 纪律：只转述 hits，段末带来源标题/文件名。  
- 走已有 SSE 流式。  
- `metrics.available` 类数字仍禁止从语料外编造；语料里出现的 DOI 必须能在 hits 原文找到。  
- 无 Key：检索卡片仍出，写作关（与现契约一致）。  
- Milvus 超时 / 5xx：回退本站关键词短条目，并在卡片标明 `via=local-fallback`，不得假装向量命中。

---

## 7. 配置与密钥

`.env`（示例名，真实值不进 Git）：

```text
LLM_API_KEY=
LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
LLM_MODEL=deepseek-v4-1-flash-260910
LLM_EMBED_MODEL=doubao-embedding-vision-251215
LLM_EMBED_DIM=1024
MILVUS_URI=http://host:19530
MILVUS_TOKEN=
MILVUS_COLLECTION_NAME=ippilab
```

客户端：`pymilvus.MilvusClient(uri, token)`。Chat 与 Embedding 共用方舟 Key，路径不同。

百炼 `BAILIAN_KB_INDEX_ID` 可保留但不作为学术主通道。

---

## 8. 权限与安全

| 角色 | 检索 | 入库 / 重建索引 |
|------|------|-----------------|
| 学生 | 只搜 `ippilab` | 否 |
| 导师 | 同学生 | 第一期用本地脚本重建 `docs/kb/` + 短条目；页面上传后置 |
| 访客 | 无 | 无 |

- 远程 Milvus 对公网开放，Token 只放 `.env`，轮换后改本地配置。本次对话已出现 Token，建议控制台改密。  
- 不把 `source_url` 的 COS 预签名或 Token 回传前端。  
- 审计记：query 截断、hit 数、file_id 列表、via、耗时；不记完整 embedding。

---

## 9. 接口（学术专科，现有工具 id 不变）

| 现有 | 变化 |
|------|------|
| `kb.retrieve` / `kb.answer` | 检索实现改为 embed + Milvus；卡片 `via=milvus` |
| `POST /assistant/sessions/{id}/messages/stream` | 写作仍流式；先出命中卡片再流式正文 |
| 重建（第一期可做成脚本，HTTP 可后置） | 只重切并重嵌 `docs/kb/` + `SEED_DOCS`，写入 `ippilab` |

前端：来源通道文案由「百炼知识库」改为「实验室知识库（Milvus）」；未命中文案保持拒答。

---

## 10. 编码分期

| 阶段 | 内容 | 依赖 |
|------|------|------|
| R0 | 配置项、pymilvus 连通、按 §5 创建 `ippilab`、单测 mock | 已拍板 |
| R1 | 只切 `docs/kb/*.md` 与 `SEED_DOCS`，1024 维稠密入库 | R0 |
| R2 | `retrieve_kb` 改为只搜 `ippilab`；阈值；失败回退短条目关键词 | R1 |
| R3 | 流式 `kb.answer` 引用 parent；前端 via 文案改为实验室知识库 | R2 |
| 后置 | PDF / 上传审定稿、查询改写、sparse / BM25、导师 HTTP 重建接口 | 另拍板 |
| 不做 | 读写 `paper_literature*`、本机再部署向量库、RAG 编排框架 | — |

---

## 11. 验收

- **RAG-01** 问「NEU-20 是不是论文完整 test split」：命中审定条目，回答否定，带来源，不编造官方 test split。2026-10-16：top 0.617，命中「写作与实验纪律」。  
- **RAG-02** 问与语料无关的问题：`hit=false`，拒答，不出现 DOI。2026-10-16：小麦赤霉病 0.335、番茄叶片病害 0.431，均低于 0.48。  
- **RAG-03** 同一学术会话「刚才那条再展开」：可引用本会话已命中 parent。  
- **RAG-04** 停 Milvus 或错误 Token：回退短条目或明确失败，对比/演示主流程不受影响。错误集合名在构造客户端之前拒绝。  
- **RAG-05** embedding 与集合 dim 不一致时拒绝入库，不静默截断。  
- **RAG-06** 密钥不出现在接口 JSON / 前端。  
- 既有 CH-01～CH-05、AI 禁演示 / 不写盘 仍有效。

2026-10-16 用学术会话复核（阈值 0.48）：RAG-01 回答「NEU-20 不是论文完整 test split」，来源为写作与实验纪律；RAG-02「番茄叶片病害用什么数据集」`hit=false`，正文无 DOI；RAG-03「刚才那条再展开」`reused=true` 并继续引用同一 parent；RAG-04 把 Milvus 指到拒绝连接的地址后 `via=local-fallback`；会话 JSON 不含密钥。RAG-05 由维度不符的单测覆盖。

---

## 12. 已拍板（2026-10-16）

1. **集合**：新建 `ippilab`。不复用 `paper_literature`。  
2. **语料**：第一期只入库 `docs/kb/` 与现有短条目。PDF 后置。  
3. **检索**：第一期只做 1024 维稠密 COSINE。sparse / BM25 后置。分数阈值按 2026-10-16 金标定为 **0.48**。

R0–R3 已按本节编码：`retrieve_kb` 只搜 `ippilab`，入库脚本为 `scripts/index_kb.py`。需求书与科研助手产品说明中的学术检索口径已改为 Milvus `ippilab`。
