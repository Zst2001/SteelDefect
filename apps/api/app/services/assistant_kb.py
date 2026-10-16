from __future__ import annotations

import logging
import re
import time
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import AssistantKbDoc
from app.util_time import new_id, utcnow

logger = logging.getLogger(__name__)

SEED_DOCS: list[dict[str, Any]] = [
    {
        "slug": "group-direction",
        "title": "课题组方向与本站定位",
        "category": "direction",
        "sort_order": 10,
        "body": (
            "课题组主线是工业表面缺陷检测，本课题聚焦钢铁缺陷语义分割。"
            "本站是常驻 CPU 实验台：对外限次公开演示，对内学生导入 AutoDL 训练产物后与内置 baseline 对照、在 NEU-20 上做正式评测。"
            "网站不做训练、微调或续训。论文插图不由本站自动排版。"
            "企业产线数据与未授权图像不得进入实验台。"
        ),
    },
    {
        "slug": "learning-path",
        "title": "新生学习路线",
        "category": "path",
        "sort_order": 20,
        "body": (
            "建议顺序：先读需求书里的对比/评测/演示分界 → 在缺陷分割页用内置 UNet / DeepLabV3+ / UNet++ 对照自己的图 → "
            "导入单个 .py 与 .pth，检查通过后再加入对照 → 需要全量指标时用正式评测（仅 NEU-20）。"
            "首页 catalog 文献卡片不是可运行模型，不要把论文名当成 version_id。"
            "导入失败请到该版本模型卡使用模型适配助手，不要让科研助手改源码。"
        ),
    },
    {
        "slug": "writing-protocol",
        "title": "写作与实验纪律",
        "category": "writing",
        "sort_order": 30,
        "body": (
            "NEU-20 是本站预置固定测试集，只有 20 张，不是论文完整 test split，不得写成官方测试集或完整 NEU-DET 评测。"
            "公开演示即使样例带 GT 也不展示、不口述 mIoU / mDice / Acc。"
            "快速对比在全部配对掩码后给出的是本批参考指标，不代表完整测试集性能。"
            "本机 FPS = 1000 / ms/图，协议是 CPU、batch=1、dummy 随机输入，不是 CUDA 论文测速，也不是测试集指标。"
            "学生权重加载保持 strict=True，不去掉 module. 前缀。学生源码只在 Docker（--network=none）里执行。"
        ),
    },
    {
        "slug": "catalog-vs-runnable",
        "title": "首页文献与模型中心",
        "category": "protocol",
        "sort_order": 40,
        "body": (
            "首页 catalog_models / 本组成果是文献与展示条目，没有推理管道。"
            "可运行版本只出现在模型中心：内置 baseline 与检查通过的学生 ModelVersion。"
            "第三方仓库、论文 GitHub、未审定网页不是本组成果，禁止写成已在本站落地。"
        ),
    },
    {
        "slug": "assistant-boundary",
        "title": "科研助手能做什么",
        "category": "protocol",
        "sort_order": 50,
        "body": (
            "科研助手三个专科互不调度。学术只根据审定语料回答，未命中则拒答，不编造 DOI。"
            "分割可分析已完成的对比或正式评测，也可确认后封装快速对比；禁止走公开演示接口，禁止用用户图新建正式评测。"
            "模型专科只调用实验室测参接口，源码建议只出文本，写盘与复检仍走模型适配助手。"
            "检测与分类管道未就绪，不得用分割工具冒充。"
        ),
    },
]


def seed_assistant_kb(db: Session) -> None:
    existing = {row.slug: row for row in db.query(AssistantKbDoc).all()}
    now = utcnow()
    for item in SEED_DOCS:
        row = existing.get(item["slug"])
        if row is None:
            db.add(
                AssistantKbDoc(
                    id=new_id(),
                    slug=item["slug"],
                    title=item["title"],
                    category=item["category"],
                    body=item["body"],
                    source_label="导师审定",
                    sort_order=int(item["sort_order"]),
                    created_at=now,
                    updated_at=now,
                )
            )
            continue
        row.title = item["title"]
        row.category = item["category"]
        row.body = item["body"]
        row.source_label = "导师审定"
        row.sort_order = int(item["sort_order"])
        row.updated_at = now


def _tokens(text: str) -> list[str]:
    lowered = text.lower()
    parts = re.findall(r"[a-z0-9_+.-]{2,}|[\u4e00-\u9fff]{2,}", lowered)
    grams: list[str] = []
    han = re.findall(r"[\u4e00-\u9fff]+", lowered)
    for block in han:
        grams.extend(block[i : i + 2] for i in range(len(block) - 1))
    return parts + grams


def retrieve_local(db: Session, query: str, *, limit: int = 4) -> list[dict[str, Any]]:
    asked = (query or "").strip()
    if not asked:
        return []
    needles = _tokens(asked)
    if not needles:
        return []
    hits: list[tuple[int, AssistantKbDoc]] = []
    for row in db.query(AssistantKbDoc).all():
        blob = f"{row.title}\n{row.body}".lower()
        score = 0
        if asked.lower() in blob:
            score += 12
        for token in needles:
            if token in blob:
                score += 3 if len(token) >= 2 else 1
        if score > 0:
            hits.append((score, row))
    hits.sort(key=lambda item: (-item[0], item[1].sort_order))
    out = []
    for score, row in hits[:limit]:
        out.append(
            {
                "id": row.id,
                "slug": row.slug,
                "file_id": row.slug,
                "title": row.title,
                "category": row.category,
                "source": row.source_label,
                "excerpt": row.body,
                "score": score,
                "via": "local",
            }
        )
    return out


def retrieve_kb(db: Session, query: str, *, settings: Settings | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    settings = settings or get_settings()
    asked = (query or "").strip()
    configured = bool((settings.milvus_uri or "").strip() or (settings.milvus_token or "").strip())
    via = "local"
    hits: list[dict[str, Any]] = []
    if configured:
        via = "local-fallback"
        try:
            from app.services.kb_embed import embed_text
            from app.services.kb_milvus import milvus_configured, search_vectors

            if not milvus_configured(settings):
                raise RuntimeError("集合名不是 ippilab 或 Milvus 未配置完整")
            found = search_vectors(settings, embed_text(asked, settings=settings), query=asked)
            if found is not None:
                hits = found
                via = "milvus"
            else:
                hits = retrieve_local(db, asked)
        except Exception:
            logger.warning("milvus retrieve failed; using local entries", exc_info=True)
            hits = retrieve_local(db, asked)
    else:
        hits = retrieve_local(db, asked)
    return {
        "query": asked[:500],
        "hit": bool(hits),
        "via": via if hits else ("milvus" if via == "milvus" else "none"),
        "hits": hits,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }
