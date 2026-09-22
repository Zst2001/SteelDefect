from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import CatalogDataset, CatalogFund, CatalogModel, CatalogWork, HomeStat
from app.errors import AppError
from app.util_time import new_id, utcnow

TASK_TYPES = ("classification", "detection", "segmentation")
WORK_KINDS = ("paper", "patent", "software", "award", "other")
FUND_SOURCES = ("nsfc", "provincial", "ministry", "horizontal", "other")
FUND_ROLES = ("pi", "participant")
FUND_STATUSES = ("ongoing", "completed")
STATS_ID = "home"
GROUP_WORK_NAMES = {"EAMINet", "DACNet", "CPANet"}

MODEL_SEEDS: list[dict[str, Any]] = [
    {
        "name": "EAMINet",
        "year": 2021,
        "task_type": "segmentation",
        "backbone": "ResNet-34",
        "keywords": "multi-level feature; fusion, edge",
        "code_url": "https://github.com/zxforchid/Edge-Aware-Multi-Level-Interactive-Network",
    },
    {
        "name": "DACNet",
        "year": 2022,
        "task_type": "segmentation",
        "backbone": "ResNet-34",
        "keywords": "Cascaded network; dense attention",
        "code_url": "https://github.com/zxforchid/DACNet",
    },
    {
        "name": "CPANet",
        "year": 2023,
        "task_type": "segmentation",
        "backbone": "ResNet-50",
        "keywords": "few-shot learning; cross position Aggregation network",
        "code_url": "https://github.com/VDT-2048/CPANet",
    },
    {
        "name": "Benchmark",
        "year": 2024,
        "task_type": "segmentation",
        "backbone": "Transformer; CNN",
        "keywords": "Machine vision; Automated inspection",
        "code_url": "https://github.com/djene-mengistu/dseg_models",
    },
    {
        "name": "DMRAN",
        "year": 2024,
        "task_type": "segmentation",
        "backbone": "U2Net",
        "keywords": "Attention mechanism",
        "code_url": "https://github.com/zz-ux/Metal-surface-defect-detection",
    },
    {
        "name": "DDFNet",
        "year": 2025,
        "task_type": "segmentation",
        "backbone": "MPARNet",
        "keywords": "Dual-branch decoder; Multi-scale attention fusion",
        "code_url": "https://github.com/13140W/DDFNet",
    },
    {
        "name": "MINet",
        "year": 2024,
        "task_type": "segmentation",
        "backbone": None,
        "keywords": "computational cost; multi-scale",
        "code_url": "https://github.com/Kunye-Shen/MINet",
    },
    {
        "name": "DFPANet",
        "year": 2025,
        "task_type": "segmentation",
        "backbone": "ResNet34",
        "keywords": "edge-guided; multiscale fusion",
        "code_url": "https://github.com/hpguo1982/DFPANet",
    },
    {
        "name": "SME-DeepLabV3+",
        "year": 2025,
        "task_type": "segmentation",
        "backbone": "StarNet",
        "keywords": "Multi-scale attention; Star operation",
        "code_url": "https://github.com/Eric-863/SME-main/tree/main",
    },
]

NEU_LINK = "http://faculty.neu.edu.cn/songkc/en/zdylm/263265"
MVIT_LINK = "https://github.com/clovermini/MVIT_metal_datasets"

DATASET_SEEDS: list[dict[str, Any]] = [
    {
        "name": "NEU-CLS",
        "task_type": "classification",
        "source_object": "Hot rolled steel strip",
        "numbers_text": "1800 images (6 defect types, 300 samples each)",
        "image_count": 1800,
        "class_count": 6,
        "size": "200×200 pixels",
        "url": NEU_LINK,
    },
    {
        "name": "NEU-CLS-64",
        "task_type": "classification",
        "source_object": "Hot rolled steel strip",
        "numbers_text": "9 defect types",
        "class_count": 9,
        "size": "64×64 pixels",
        "url": NEU_LINK,
    },
    {
        "name": "X-SSD",
        "task_type": "classification",
        "source_object": "Hot rolled steel strip",
        "numbers_text": "7 typical defects, 1360 defect images",
        "image_count": 1360,
        "class_count": 7,
        "size": "640×640 pixels",
        "url": "https://github.com/Fighter20092392/X-SDD-A-New-benchmark",
    },
    {
        "name": "SteelBlastQC",
        "task_type": "classification",
        "source_object": "Sandblasted steel surface",
        "numbers_text": "1654 images",
        "image_count": 1654,
        "size": "512×512 pixels",
        "url": "https://www.selectdataset.com/dataset/82d51b3d89d46f589afda3aa1600de21",
    },
    {
        "name": "MSD-CLS",
        "task_type": "classification",
        "source_object": "Steel",
        "numbers_text": "500 images (10 defect types, 50 samples each)",
        "image_count": 500,
        "class_count": 10,
        "size": "224×224 pixels",
        "url": "https://github.com/successhaha/Gtnet",
    },
    {
        "name": "NEU-DET",
        "task_type": "detection",
        "source_object": "Hot rolled steel strip",
        "numbers_text": "1800 images (6 defect types, 300 samples each)",
        "image_count": 1800,
        "class_count": 6,
        "size": "200×200 pixels",
        "url": NEU_LINK,
    },
    {
        "name": "GC10-DET",
        "task_type": "detection",
        "source_object": "Steel strip",
        "numbers_text": "3570 images with 10 defect types",
        "image_count": 3570,
        "class_count": 10,
        "size": "2048×1000 pixels",
        "url": "https://github.com/lvxiaoming2019/GC10-DET-Metallic-Surface-Defect-Datasets",
    },
    {
        "name": "Severstal-steel-defect",
        "task_type": "detection",
        "source_object": "Steel strip",
        "numbers_text": "6666 grayscale images (4 defect types)",
        "image_count": 6666,
        "class_count": 4,
        "size": "800×128 pixels",
        "url": "https://www.kaggle.com/c/severstal-steel-defect-detection/data",
    },
    {
        "name": "MHPSDS",
        "task_type": "detection",
        "source_object": "Medium and Heavy Plate",
        "numbers_text": "4 typical defects, 680 images",
        "image_count": 680,
        "class_count": 4,
        "size": "256×256 pixels",
        "url": MVIT_LINK,
    },
    {
        "name": "Casting Billet Dataset",
        "task_type": "detection",
        "source_object": "Casting Billet",
        "numbers_text": "6 typical defects, 1060 images",
        "image_count": 1060,
        "class_count": 6,
        "size": "96×106 to 3228×492",
        "url": MVIT_LINK,
    },
    {
        "name": "Steel Pipe Dataset",
        "task_type": "detection",
        "source_object": "Steel Pipe",
        "numbers_text": "4 typical defects, 1,227 images",
        "image_count": 1227,
        "class_count": 4,
        "size": "728×544 pixels",
        "url": MVIT_LINK,
    },
    {
        "name": "NEU_Seg",
        "task_type": "segmentation",
        "source_object": "Hot rolled steel strip",
        "numbers_text": "4470 images (3 defect types)",
        "image_count": 4470,
        "class_count": 3,
        "size": "200×200 pixels",
        "url": NEU_LINK,
    },
    {
        "name": "KolektorSDD2",
        "task_type": "segmentation",
        "source_object": "Multiple types",
        "numbers_text": "Training: 2,085; Test: 1,004",
        "size": "230×630 pixels",
        "url": "https://modelscope.cn/datasets/OpenDataLab/KolektorSDD2",
    },
    {
        "name": "BSData",
        "task_type": "segmentation",
        "source_object": "Ball Screw",
        "numbers_text": "1104 three-channel images",
        "image_count": 1104,
        "size": "multiple pixels",
        "url": "https://hf-mirror.com/datasets/Gssmc/BSData",
    },
    {
        "name": "RSDDs dataset",
        "task_type": "segmentation",
        "source_object": "Rail surface",
        "numbers_text": "2 types (67 images; 128 images)",
        "class_count": 2,
        "size": "multiple pixels",
        "url": "https://aistudio.baidu.com/dataset/detail/97732/file",
    },
    {
        "name": "SD-saliency-900",
        "task_type": "segmentation",
        "source_object": "Bar Steel",
        "numbers_text": "900 images",
        "image_count": 900,
        "size": "200×200 pixels",
        "url": "https://github.com/SongGuorong/MCITF/tree/master/SD-saliency-900",
    },
    {
        "name": "FSSD-12",
        "task_type": "segmentation",
        "source_object": "Steel strip",
        "numbers_text": "12 typical defects, 50 samples each",
        "class_count": 12,
        "size": "200×200 pixels",
        "url": "https://pan.baidu.com/s/15k5QQXX8Ha7yXNcdWQvV5Q?pwd=pfnc",
        "access_note": "提取码 pfnc",
    },
    {
        "name": "Severstal Steel Defect",
        "task_type": "segmentation",
        "source_object": "Steel strip",
        "numbers_text": "Training: 5280; Test: 5506",
        "size": "1600×256 pixels",
        "url": "https://pan.baidu.com/s/1U9KIqbNx9F1Sv7MTH_PzXQ?pwd=ydc3",
        "access_note": "提取码 ydc3",
    },
]


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _clean_backbone(value: str | None) -> str | None:
    text = _blank(value)
    if text in {None, "-", "—"}:
        return None
    return text


def _require_task_type(task_type: str) -> str:
    value = task_type.strip()
    if value not in TASK_TYPES:
        raise AppError("任务类型须为 classification / detection / segmentation", code="BAD_TASK_TYPE", stage="catalog")
    return value


def serialize_stats(row: HomeStat) -> dict[str, Any]:
    return {
        "research_models": row.research_models,
        "papers": row.papers,
        "updated_at": row.updated_at.isoformat() + "Z",
    }


def serialize_model(row: CatalogModel) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "year": row.year,
        "task_type": row.task_type,
        "backbone": row.backbone,
        "keywords": row.keywords,
        "paper_url": row.paper_url,
        "code_url": row.code_url,
        "dataset": row.dataset,
        "detail": row.detail,
        "is_group_work": row.is_group_work,
        "sort_order": row.sort_order,
        "created_at": row.created_at.isoformat() + "Z",
        "updated_at": row.updated_at.isoformat() + "Z",
    }


def serialize_work(row: CatalogWork) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "year": row.year,
        "venue": row.venue,
        "authors": row.authors,
        "summary": row.summary,
        "link_url": row.link_url,
        "sort_order": row.sort_order,
        "created_at": row.created_at.isoformat() + "Z",
        "updated_at": row.updated_at.isoformat() + "Z",
    }


def serialize_fund(row: CatalogFund) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "source": row.source,
        "number": row.number,
        "role": row.role,
        "start_year": row.start_year,
        "end_year": row.end_year,
        "status": row.status,
        "amount_text": row.amount_text,
        "detail": row.detail,
        "sort_order": row.sort_order,
        "created_at": row.created_at.isoformat() + "Z",
        "updated_at": row.updated_at.isoformat() + "Z",
    }


def serialize_dataset(row: CatalogDataset) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "task_type": row.task_type,
        "source_object": row.source_object,
        "numbers_text": row.numbers_text,
        "image_count": row.image_count,
        "class_count": row.class_count,
        "defect_types": row.defect_types,
        "size": row.size,
        "url": row.url,
        "access_note": row.access_note,
        "detail": row.detail,
        "sort_order": row.sort_order,
        "created_at": row.created_at.isoformat() + "Z",
        "updated_at": row.updated_at.isoformat() + "Z",
    }


def ensure_home_stats(db: Session) -> HomeStat:
    row = db.get(HomeStat, STATS_ID)
    if row:
        return row
    row = HomeStat(id=STATS_ID, research_models=0, papers=0, updated_at=utcnow())
    db.add(row)
    db.flush()
    return row


def get_home_payload(db: Session) -> dict[str, Any]:
    stats = ensure_home_stats(db)
    models = db.query(CatalogModel).order_by(CatalogModel.sort_order.asc(), CatalogModel.year.asc(), CatalogModel.name.asc()).all()
    datasets = (
        db.query(CatalogDataset).order_by(CatalogDataset.sort_order.asc(), CatalogDataset.name.asc()).all()
    )
    works = db.query(CatalogWork).order_by(CatalogWork.sort_order.asc(), CatalogWork.year.desc(), CatalogWork.name.asc()).all()
    funds = (
        db.query(CatalogFund)
        .order_by(CatalogFund.sort_order.asc(), CatalogFund.start_year.desc(), CatalogFund.name.asc())
        .all()
    )
    return {
        "stats": serialize_stats(stats),
        "models": [serialize_model(row) for row in models],
        "datasets": [serialize_dataset(row) for row in datasets],
        "works": [serialize_work(row) for row in works],
        "funds": [serialize_fund(row) for row in funds],
    }


def update_stats(db: Session, *, research_models: int, papers: int) -> HomeStat:
    if research_models < 0 or papers < 0:
        raise AppError("统计数字不能为负数", code="BAD_STATS", stage="catalog")
    row = ensure_home_stats(db)
    row.research_models = research_models
    row.papers = papers
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _next_model_order(db: Session) -> int:
    current = db.query(CatalogModel.sort_order).order_by(CatalogModel.sort_order.desc()).first()
    return (current[0] + 10) if current else 10


def _next_dataset_order(db: Session) -> int:
    current = db.query(CatalogDataset.sort_order).order_by(CatalogDataset.sort_order.desc()).first()
    return (current[0] + 10) if current else 10


def _next_work_order(db: Session) -> int:
    current = db.query(CatalogWork.sort_order).order_by(CatalogWork.sort_order.desc()).first()
    return (current[0] + 10) if current else 10


def _next_fund_order(db: Session) -> int:
    current = db.query(CatalogFund.sort_order).order_by(CatalogFund.sort_order.desc()).first()
    return (current[0] + 10) if current else 10


def _require_choice(value: str, allowed: tuple[str, ...], message: str, code: str) -> str:
    text = (value or "").strip()
    if text not in allowed:
        raise AppError(message, code=code, stage="catalog")
    return text


def create_model(
    db: Session,
    *,
    name: str,
    year: int | None,
    task_type: str,
    backbone: str | None,
    keywords: str | None,
    paper_url: str | None,
    code_url: str | None,
    dataset: str | None,
    detail: str | None,
    is_group_work: bool,
    sort_order: int | None = None,
) -> CatalogModel:
    title = name.strip()
    if not title:
        raise AppError("名称不能为空", code="BAD_NAME", stage="catalog")
    now = utcnow()
    row = CatalogModel(
        id=new_id(),
        name=title,
        year=year,
        task_type=_require_task_type(task_type),
        backbone=_clean_backbone(backbone),
        keywords=_blank(keywords),
        paper_url=_blank(paper_url),
        code_url=_blank(code_url),
        dataset=_blank(dataset),
        detail=_blank(detail),
        is_group_work=is_group_work,
        sort_order=sort_order if sort_order is not None else _next_model_order(db),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_model(db: Session, model_id: str, **fields: Any) -> CatalogModel:
    row = db.get(CatalogModel, model_id)
    if row is None:
        raise AppError("成果或模型不存在", code="NOT_FOUND", stage="catalog", status_code=404)
    if "name" in fields and fields["name"] is not None:
        title = str(fields["name"]).strip()
        if not title:
            raise AppError("名称不能为空", code="BAD_NAME", stage="catalog")
        row.name = title
    if "year" in fields:
        row.year = fields["year"]
    if "task_type" in fields and fields["task_type"] is not None:
        row.task_type = _require_task_type(fields["task_type"])
    if "backbone" in fields:
        row.backbone = _clean_backbone(fields["backbone"])
    if "keywords" in fields:
        row.keywords = _blank(fields["keywords"])
    if "paper_url" in fields:
        row.paper_url = _blank(fields["paper_url"])
    if "code_url" in fields:
        row.code_url = _blank(fields["code_url"])
    if "dataset" in fields:
        row.dataset = _blank(fields["dataset"])
    if "detail" in fields:
        row.detail = _blank(fields["detail"])
    if "is_group_work" in fields and fields["is_group_work"] is not None:
        row.is_group_work = bool(fields["is_group_work"])
    if "sort_order" in fields and fields["sort_order"] is not None:
        row.sort_order = int(fields["sort_order"])
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_model(db: Session, model_id: str) -> None:
    row = db.get(CatalogModel, model_id)
    if row is None:
        raise AppError("成果或模型不存在", code="NOT_FOUND", stage="catalog", status_code=404)
    db.delete(row)
    db.commit()


def create_dataset(
    db: Session,
    *,
    name: str,
    task_type: str,
    source_object: str | None,
    numbers_text: str | None,
    image_count: int | None,
    class_count: int | None,
    defect_types: str | None,
    size: str | None,
    url: str | None,
    access_note: str | None,
    detail: str | None,
    sort_order: int | None = None,
) -> CatalogDataset:
    title = name.strip()
    if not title:
        raise AppError("名称不能为空", code="BAD_NAME", stage="catalog")
    now = utcnow()
    row = CatalogDataset(
        id=new_id(),
        name=title,
        task_type=_require_task_type(task_type),
        source_object=_blank(source_object),
        numbers_text=_blank(numbers_text),
        image_count=image_count,
        class_count=class_count,
        defect_types=_blank(defect_types),
        size=_blank(size),
        url=_blank(url),
        access_note=_blank(access_note),
        detail=_blank(detail),
        sort_order=sort_order if sort_order is not None else _next_dataset_order(db),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_dataset(db: Session, dataset_id: str, **fields: Any) -> CatalogDataset:
    row = db.get(CatalogDataset, dataset_id)
    if row is None:
        raise AppError("数据集不存在", code="NOT_FOUND", stage="catalog", status_code=404)
    if "name" in fields and fields["name"] is not None:
        title = str(fields["name"]).strip()
        if not title:
            raise AppError("名称不能为空", code="BAD_NAME", stage="catalog")
        row.name = title
    if "task_type" in fields and fields["task_type"] is not None:
        row.task_type = _require_task_type(fields["task_type"])
    for key in ("source_object", "numbers_text", "defect_types", "size", "url", "access_note", "detail"):
        if key in fields:
            setattr(row, key, _blank(fields[key]))
    if "image_count" in fields:
        row.image_count = fields["image_count"]
    if "class_count" in fields:
        row.class_count = fields["class_count"]
    if "sort_order" in fields and fields["sort_order"] is not None:
        row.sort_order = int(fields["sort_order"])
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_dataset(db: Session, dataset_id: str) -> None:
    row = db.get(CatalogDataset, dataset_id)
    if row is None:
        raise AppError("数据集不存在", code="NOT_FOUND", stage="catalog", status_code=404)
    db.delete(row)
    db.commit()


def create_work(
    db: Session,
    *,
    name: str,
    kind: str,
    year: int | None,
    venue: str | None,
    authors: str | None,
    summary: str | None,
    link_url: str | None,
    sort_order: int | None = None,
) -> CatalogWork:
    title = name.strip()
    if not title:
        raise AppError("名称不能为空", code="BAD_NAME", stage="catalog")
    now = utcnow()
    row = CatalogWork(
        id=new_id(),
        name=title,
        kind=_require_choice(kind, WORK_KINDS, "成果类型无效", "BAD_WORK_KIND"),
        year=year,
        venue=_blank(venue),
        authors=_blank(authors),
        summary=_blank(summary),
        link_url=_blank(link_url),
        sort_order=sort_order if sort_order is not None else _next_work_order(db),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_work(db: Session, work_id: str, **fields: Any) -> CatalogWork:
    row = db.get(CatalogWork, work_id)
    if row is None:
        raise AppError("成果不存在", code="NOT_FOUND", stage="catalog", status_code=404)
    if "name" in fields and fields["name"] is not None:
        title = str(fields["name"]).strip()
        if not title:
            raise AppError("名称不能为空", code="BAD_NAME", stage="catalog")
        row.name = title
    if "kind" in fields and fields["kind"] is not None:
        row.kind = _require_choice(fields["kind"], WORK_KINDS, "成果类型无效", "BAD_WORK_KIND")
    if "year" in fields:
        row.year = fields["year"]
    for key in ("venue", "authors", "summary", "link_url"):
        if key in fields:
            setattr(row, key, _blank(fields[key]))
    if "sort_order" in fields and fields["sort_order"] is not None:
        row.sort_order = int(fields["sort_order"])
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_work(db: Session, work_id: str) -> None:
    row = db.get(CatalogWork, work_id)
    if row is None:
        raise AppError("成果不存在", code="NOT_FOUND", stage="catalog", status_code=404)
    db.delete(row)
    db.commit()


def create_fund(
    db: Session,
    *,
    name: str,
    source: str,
    number: str | None,
    role: str,
    start_year: int | None,
    end_year: int | None,
    status: str,
    amount_text: str | None,
    detail: str | None,
    sort_order: int | None = None,
) -> CatalogFund:
    title = name.strip()
    if not title:
        raise AppError("名称不能为空", code="BAD_NAME", stage="catalog")
    now = utcnow()
    row = CatalogFund(
        id=new_id(),
        name=title,
        source=_require_choice(source, FUND_SOURCES, "基金类别无效", "BAD_FUND_SOURCE"),
        number=_blank(number),
        role=_require_choice(role, FUND_ROLES, "承担角色无效", "BAD_FUND_ROLE"),
        start_year=start_year,
        end_year=end_year,
        status=_require_choice(status, FUND_STATUSES, "基金状态无效", "BAD_FUND_STATUS"),
        amount_text=_blank(amount_text),
        detail=_blank(detail),
        sort_order=sort_order if sort_order is not None else _next_fund_order(db),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_fund(db: Session, fund_id: str, **fields: Any) -> CatalogFund:
    row = db.get(CatalogFund, fund_id)
    if row is None:
        raise AppError("基金不存在", code="NOT_FOUND", stage="catalog", status_code=404)
    if "name" in fields and fields["name"] is not None:
        title = str(fields["name"]).strip()
        if not title:
            raise AppError("名称不能为空", code="BAD_NAME", stage="catalog")
        row.name = title
    if "source" in fields and fields["source"] is not None:
        row.source = _require_choice(fields["source"], FUND_SOURCES, "基金类别无效", "BAD_FUND_SOURCE")
    if "role" in fields and fields["role"] is not None:
        row.role = _require_choice(fields["role"], FUND_ROLES, "承担角色无效", "BAD_FUND_ROLE")
    if "status" in fields and fields["status"] is not None:
        row.status = _require_choice(fields["status"], FUND_STATUSES, "基金状态无效", "BAD_FUND_STATUS")
    if "start_year" in fields:
        row.start_year = fields["start_year"]
    if "end_year" in fields:
        row.end_year = fields["end_year"]
    for key in ("number", "amount_text", "detail"):
        if key in fields:
            setattr(row, key, _blank(fields[key]))
    if "sort_order" in fields and fields["sort_order"] is not None:
        row.sort_order = int(fields["sort_order"])
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_fund(db: Session, fund_id: str) -> None:
    row = db.get(CatalogFund, fund_id)
    if row is None:
        raise AppError("基金不存在", code="NOT_FOUND", stage="catalog", status_code=404)
    db.delete(row)
    db.commit()


def seed_catalog(db: Session) -> None:
    ensure_home_stats(db)
    existing_models = {row.name for row in db.query(CatalogModel).all()}
    for index, item in enumerate(MODEL_SEEDS, start=1):
        if item["name"] in existing_models:
            continue
        now = utcnow()
        db.add(
            CatalogModel(
                id=new_id(),
                name=item["name"],
                year=item.get("year"),
                task_type=item["task_type"],
                backbone=_clean_backbone(item.get("backbone")),
                keywords=_blank(item.get("keywords")),
                paper_url=_blank(item.get("paper_url")),
                code_url=_blank(item.get("code_url")),
                dataset=_blank(item.get("dataset")),
                detail=_blank(item.get("detail")),
                is_group_work=item["name"] in GROUP_WORK_NAMES,
                sort_order=index * 10,
                created_at=now,
                updated_at=now,
            )
        )
    existing_datasets = {row.name for row in db.query(CatalogDataset).all()}
    for index, item in enumerate(DATASET_SEEDS, start=1):
        if item["name"] in existing_datasets:
            continue
        now = utcnow()
        db.add(
            CatalogDataset(
                id=new_id(),
                name=item["name"],
                task_type=item["task_type"],
                source_object=_blank(item.get("source_object")),
                numbers_text=_blank(item.get("numbers_text")),
                image_count=item.get("image_count"),
                class_count=item.get("class_count"),
                defect_types=_blank(item.get("defect_types")),
                size=_blank(item.get("size")),
                url=_blank(item.get("url")),
                access_note=_blank(item.get("access_note")),
                detail=_blank(item.get("detail")),
                sort_order=index * 10,
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()
