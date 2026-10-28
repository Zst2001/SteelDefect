from __future__ import annotations

from urllib.parse import quote

from infer.spec import NEU_CLASS_MAP, NEU_LEGEND
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Dataset, DatasetVersion, PreprocessSpecRow, Sample, User
from app.errors import AppError
from app.services.storage import resolve_uri

CATALOG_KINDS = frozenset({"preset", "upload_batch"})
SAMPLE_PAGE_DEFAULT = 24
SAMPLE_PAGE_MAX = 48
NEU_FULL_NAME = "NEU"
NEU20_NAME = "NEU-20"


def can_view_dataset(user: User, dataset: Dataset) -> bool:
    if dataset.visibility == "preset":
        return True
    if user.role == "advisor":
        return True
    return dataset.owner_id == user.id


def get_visible_dataset(db: Session, user: User, dataset_id: str) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise AppError("数据集不存在", code="NOT_FOUND", stage="file", status_code=404)
    if not can_view_dataset(user, dataset):
        raise AppError("无权查看该数据集", code="FORBIDDEN", stage="auth", status_code=403)
    return dataset


def catalog_versions(db: Session, dataset_id: str) -> list[DatasetVersion]:
    return (
        db.query(DatasetVersion)
        .filter(
            DatasetVersion.dataset_id == dataset_id,
            DatasetVersion.kind.in_(CATALOG_KINDS),
        )
        .order_by(DatasetVersion.created_at.asc())
        .all()
    )


def version_stats(db: Session, version_ids: list[str]) -> dict[str, tuple[int, int]]:
    if not version_ids:
        return {}
    missing_expr = func.sum(case((Sample.mask_uri.is_(None), 1), else_=0))
    rows = (
        db.query(Sample.version_id, func.count(Sample.id), missing_expr)
        .filter(Sample.version_id.in_(version_ids))
        .group_by(Sample.version_id)
        .all()
    )
    return {version_id: (int(total), int(missing or 0)) for version_id, total, missing in rows}


def summarize_dataset_version(version: DatasetVersion, samples: list[Sample]) -> dict:
    has_gt = bool(samples) and all(sample.mask_uri for sample in samples)
    return summarize_dataset_counts(version, sample_count=len(samples), missing_masks=0 if has_gt else 1)


def summarize_dataset_counts(version: DatasetVersion, *, sample_count: int, missing_masks: int) -> dict:
    has_gt = sample_count > 0 and missing_masks == 0
    eval_ready = version.kind == "preset" and bool(version.is_fixed_test) and has_gt
    return {
        "id": version.id,
        "kind": version.kind,
        "is_fixed_test": bool(version.is_fixed_test),
        "forbid_student_gt_download": bool(version.forbid_student_gt_download),
        "sample_count": sample_count,
        "has_gt": has_gt,
        "eval_ready": eval_ready,
        "browse_only": version.kind == "preset" and not version.is_fixed_test,
    }


def _ingest_hint(dataset: Dataset, sample_count: int) -> str | None:
    if dataset.name == NEU_FULL_NAME and dataset.visibility == "preset" and sample_count == 0:
        return (
            "全量 NEU 还没有登记样本。把配对的 images/ 与 masks/ 放到站点配置的 NEU 全量目录"
            "（默认 assets/datasets/neu，可用 NEU_FULL_ROOT 改路径）后重启实验台即可扫描。"
            "本集只读浏览，不能当作正式评测集。"
        )
    return None


def _dataset_payload(dataset: Dataset, version_payload: list[dict]) -> dict:
    sample_total = sum(row["sample_count"] for row in version_payload)
    return {
        "id": dataset.id,
        "name": dataset.name,
        "visibility": dataset.visibility,
        "owner_id": dataset.owner_id,
        "eval_ready": any(row["eval_ready"] for row in version_payload),
        "sample_count": sample_total,
        "ingest_hint": _ingest_hint(dataset, sample_total),
        "versions": version_payload,
    }


def list_dataset_catalog(db: Session, user: User) -> dict:
    # Classification batches are browsed through their authorized task result.
    # Do not render them as empty segmentation datasets with NEU mask legends.
    rows = db.query(Dataset).filter(
        ~Dataset.versions.any(DatasetVersion.kind == "classification_batch")
        | Dataset.versions.any(DatasetVersion.kind.in_(CATALOG_KINDS))
    ).all()
    visible = [row for row in rows if can_view_dataset(user, row)]
    version_map: dict[str, list[DatasetVersion]] = {}
    all_version_ids: list[str] = []
    for dataset in visible:
        versions = catalog_versions(db, dataset.id)
        version_map[dataset.id] = versions
        all_version_ids.extend(version.id for version in versions)
    stats = version_stats(db, all_version_ids)
    items = []
    for dataset in visible:
        version_payload = []
        for version in version_map[dataset.id]:
            total, missing = stats.get(version.id, (0, 0))
            version_payload.append(summarize_dataset_counts(version, sample_count=total, missing_masks=missing))
        items.append(_dataset_payload(dataset, version_payload))
    items.sort(key=lambda row: (0 if row["eval_ready"] else 1, 0 if row["visibility"] == "preset" else 1, row["name"]))
    return {"items": items}


def dataset_detail_payload(db: Session, user: User, dataset_id: str) -> dict:
    dataset = get_visible_dataset(db, user, dataset_id)
    versions = catalog_versions(db, dataset.id)
    if not versions and db.query(DatasetVersion.id).filter_by(
        dataset_id=dataset.id, kind="classification_batch"
    ).first() is not None:
        raise AppError("分类批次请从对应任务查看", code="NOT_FOUND", stage="file", status_code=404)
    stats = version_stats(db, [version.id for version in versions])
    version_payload = []
    class_map = None
    preprocess_name = None
    for version in versions:
        total, missing = stats.get(version.id, (0, 0))
        summary = summarize_dataset_counts(version, sample_count=total, missing_masks=missing)
        if class_map is None:
            class_map = version.class_map_json or NEU_CLASS_MAP
        if preprocess_name is None:
            spec = db.get(PreprocessSpecRow, version.preprocess_id)
            preprocess_name = spec.name if spec else None
        version_payload.append(summary)
    payload = _dataset_payload(dataset, version_payload)
    payload["class_map"] = class_map or NEU_CLASS_MAP
    payload["legend"] = NEU_LEGEND
    payload["preprocess"] = preprocess_name
    payload["disclaimer"] = _disclaimer(dataset, version_payload)
    return payload


def _disclaimer(dataset: Dataset, versions: list[dict]) -> str:
    if dataset.name == NEU20_NAME or any(row["eval_ready"] for row in versions):
        return "当前固定测试集为 NEU-20，不是论文完整 test split。学生不可下载该集 GT。"
    if dataset.name == NEU_FULL_NAME:
        return "全量 NEU 只读浏览，不能进入正式评测。正式评测仍只用 NEU-20。"
    return "私有批次来自快速对比上传，受 50 张限制；完整数据集请使用预置登记或后续 ZIP 导入。"


def page_samples(
    db: Session,
    user: User,
    dataset_id: str,
    version_id: str,
    *,
    offset: int = 0,
    limit: int = SAMPLE_PAGE_DEFAULT,
) -> dict:
    dataset = get_visible_dataset(db, user, dataset_id)
    if offset < 0:
        raise AppError("offset 不能为负", code="BAD_PAGE", stage="file", status_code=400)
    limit = min(max(limit, 1), SAMPLE_PAGE_MAX)
    version = (
        db.query(DatasetVersion)
        .filter(DatasetVersion.id == version_id, DatasetVersion.dataset_id == dataset.id)
        .one_or_none()
    )
    if version is None or version.kind not in CATALOG_KINDS:
        raise AppError("数据版本不存在", code="NOT_FOUND", stage="file", status_code=404)
    total = db.query(func.count(Sample.id)).filter(Sample.version_id == version.id).scalar() or 0
    rows = (
        db.query(Sample)
        .filter(Sample.version_id == version.id)
        .order_by(Sample.sample_key.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    items = []
    for sample in rows:
        items.append(
            {
                "id": sample.id,
                "sample_key": sample.sample_key,
                "width": sample.width,
                "height": sample.height,
                "has_mask": sample.mask_uri is not None,
                "preview_url": (
                    f"/api/datasets/{dataset.id}/versions/{version.id}"
                    f"/samples/{quote(sample.sample_key, safe='')}/preview"
                ),
            }
        )
    return {
        "version_id": version.id,
        "total": int(total),
        "offset": offset,
        "limit": limit,
        "items": items,
    }


def sample_preview_path(
    db: Session,
    user: User,
    dataset_id: str,
    version_id: str,
    sample_key: str,
    settings: Settings | None = None,
):
    settings = settings or get_settings()
    dataset = get_visible_dataset(db, user, dataset_id)
    sample = (
        db.query(Sample)
        .join(DatasetVersion, DatasetVersion.id == Sample.version_id)
        .filter(
            DatasetVersion.id == version_id,
            DatasetVersion.dataset_id == dataset.id,
            DatasetVersion.kind.in_(CATALOG_KINDS),
            Sample.sample_key == sample_key,
        )
        .one_or_none()
    )
    if sample is None:
        raise AppError("没有对应样本", code="NOT_FOUND", stage="file", status_code=404)
    path = resolve_uri(sample.origin_uri, settings)
    if not path.is_file():
        raise AppError("样本文件缺失", code="SAMPLE_FILE_MISSING", stage="file", status_code=404)
    return path, sample
