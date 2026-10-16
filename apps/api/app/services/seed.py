from __future__ import annotations

import hashlib
from pathlib import Path

from infer.spec import (
    BUILTIN_DISPLAY_NAMES,
    BUILTIN_SLUGS,
    BUILTIN_WEIGHT_FILES,
    DEMO_CATALOG_KIND,
    NEU_CLASS_MAP,
    NEU_DEFAULT,
)
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import (
    Dataset,
    DatasetVersion,
    Model,
    ModelVersion,
    PreprocessSpecRow,
    Sample,
    User,
    Weight,
)
from app.security import hash_password
from app.services.catalog import seed_catalog
from app.services.assistant_kb import seed_assistant_kb
from app.util_time import new_id

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
MASK_EXTS = (".png", ".bmp", ".jpg", ".jpeg", ".tif", ".tiff")


def _invalidate_model_lists() -> None:
    """Seed can add builtins after the 10-minute models list cache was filled."""
    from app.cache import cache_redis

    client = cache_redis()
    keys = list(client.scan_iter("lab:models:list:*"))
    if keys:
        client.delete(*keys)


def _ensure_user(db: Session, username: str, password: str, role: str) -> User:
    row = db.query(User).filter(User.username == username).one_or_none()
    if row:
        return row
    user = User(
        id=new_id(),
        username=username,
        password_hash=hash_password(password),
        role=role,
        status="active",
        quota_json={"max_upload_images": 50},
    )
    db.add(user)
    db.flush()
    return user


def _ensure_preprocess(db: Session) -> PreprocessSpecRow:
    row = db.query(PreprocessSpecRow).filter(PreprocessSpecRow.name == "neu_200").one_or_none()
    if row:
        return row
    row = PreprocessSpecRow(
        id=new_id(),
        name="neu_200",
        height=NEU_DEFAULT.height,
        width=NEU_DEFAULT.width,
        apply_clahe=NEU_DEFAULT.apply_clahe,
        sp_threshold=NEU_DEFAULT.sp_threshold,
        dataset="neu",
        extra_json={"note": "与训练默认 200x200 CLAHE/椒盐 一致，对比不得静默改尺寸"},
    )
    db.add(row)
    db.flush()
    return row


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _uri_for_image(path: Path, settings: Settings) -> str:
    resolved = path.resolve()
    assets = (settings.repo_root / "assets").resolve()
    try:
        rel = resolved.relative_to(assets)
        return "asset:" + rel.as_posix()
    except ValueError:
        rel = resolved.relative_to(settings.neu_full_path.resolve())
        return "neufull:" + rel.as_posix()


def _find_mask(masks_dir: Path, key: str) -> Path | None:
    if not masks_dir.is_dir():
        return None
    for ext in MASK_EXTS:
        candidate = masks_dir / f"{key}{ext}"
        if candidate.is_file():
            return candidate
    return None


def _ingest_folder_samples(
    db: Session,
    version: DatasetVersion,
    images_dir: Path,
    masks_dir: Path,
    settings: Settings,
) -> int:
    if not images_dir.is_dir():
        return 0
    import cv2

    existing = {
        row.sample_key for row in db.query(Sample).filter(Sample.version_id == version.id).all()
    }
    added = 0
    for image_path in sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS):
        key = image_path.stem
        if key in existing:
            continue
        bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if bgr is None:
            continue
        height, width = bgr.shape[:2]
        mask_path = _find_mask(masks_dir, key)
        mask_uri = _uri_for_image(mask_path, settings) if mask_path is not None else None
        db.add(
            Sample(
                id=new_id(),
                version_id=version.id,
                sample_key=key,
                origin_uri=_uri_for_image(image_path, settings),
                mask_uri=mask_uri,
                width=width,
                height=height,
                sha256=_file_sha256(image_path),
            )
        )
        existing.add(key)
        added += 1
    return added


def _ensure_preset_dataset(db: Session, name: str) -> Dataset:
    dataset = db.query(Dataset).filter(Dataset.name == name, Dataset.visibility == "preset").one_or_none()
    if dataset is None:
        dataset = Dataset(id=new_id(), owner_id=None, name=name, visibility="preset")
        db.add(dataset)
        db.flush()
    return dataset


def _ensure_preset_version(
    db: Session,
    dataset: Dataset,
    preprocess: PreprocessSpecRow,
    *,
    is_fixed_test: bool,
    forbid_student_gt_download: bool,
) -> DatasetVersion:
    version = (
        db.query(DatasetVersion)
        .filter(DatasetVersion.dataset_id == dataset.id, DatasetVersion.kind == "preset")
        .one_or_none()
    )
    if version is None:
        version = DatasetVersion(
            id=new_id(),
            dataset_id=dataset.id,
            kind="preset",
            class_map_json=NEU_CLASS_MAP,
            preprocess_id=preprocess.id,
            is_fixed_test=is_fixed_test,
            forbid_student_gt_download=forbid_student_gt_download,
        )
        db.add(version)
        db.flush()
        return version
    version.is_fixed_test = is_fixed_test
    version.forbid_student_gt_download = forbid_student_gt_download
    version.class_map_json = version.class_map_json or NEU_CLASS_MAP
    return version


def seed_all(db: Session, settings: Settings) -> None:
    advisor = _ensure_user(
        db, settings.seed_advisor_username, settings.seed_advisor_password, "advisor"
    )
    _ensure_user(db, settings.seed_student_username, settings.seed_student_password, "student")
    preprocess = _ensure_preprocess(db)

    for slug in BUILTIN_SLUGS:
        model = db.query(Model).filter(Model.source == "builtin", Model.name == BUILTIN_DISPLAY_NAMES[slug]).one_or_none()
        if model is None:
            model = Model(id=new_id(), owner_id=advisor.id, name=BUILTIN_DISPLAY_NAMES[slug], source="builtin")
            db.add(model)
            db.flush()
        version = (
            db.query(ModelVersion)
            .filter(ModelVersion.model_id == model.id, ModelVersion.slug == slug)
            .one_or_none()
        )
        weight_rel = BUILTIN_WEIGHT_FILES[slug]
        weight_path = settings.repo_root / "assets" / weight_rel
        sha = _file_sha256(weight_path) if weight_path.is_file() else "missing"
        status = "runnable" if weight_path.is_file() else "cannot_start"
        fail_stage = None if weight_path.is_file() else "file"
        fail_message = None if weight_path.is_file() else f"缺少权重文件 {weight_rel}"
        if version is None:
            version = ModelVersion(
                id=new_id(),
                model_id=model.id,
                slug=slug,
                entry_symbol=slug,
                num_classes=4,
                in_channels=3,
                input_h=200,
                input_w=200,
                preprocess_id=preprocess.id,
                requires_cuda=False,
                status=status,
                fail_stage=fail_stage,
                fail_message=fail_message,
                source_sha256=sha,
                visibility="public",
            )
            db.add(version)
            db.flush()
        else:
            version.status = status
            version.fail_stage = fail_stage
            version.fail_message = fail_message
            version.source_sha256 = sha
        if db.query(Weight).filter(Weight.version_id == version.id).first() is None:
            db.add(
                Weight(
                    id=new_id(),
                    version_id=version.id,
                    file_uri=f"asset:{weight_rel.replace(chr(92), '/')}",
                    sha256=sha,
                    param_count=None,
                )
            )

    neu20 = _ensure_preset_dataset(db, "NEU-20")
    neu20_version = _ensure_preset_version(
        db,
        neu20,
        preprocess,
        is_fixed_test=True,
        forbid_student_gt_download=True,
    )
    _ingest_folder_samples(
        db,
        neu20_version,
        settings.repo_root / "assets" / "samples" / "neu" / "images",
        settings.repo_root / "assets" / "samples" / "neu" / "masks",
        settings,
    )
    _ensure_demo_samples(db, preprocess, neu20_version)

    neu_full = _ensure_preset_dataset(db, "NEU")
    neu_full_version = _ensure_preset_version(
        db,
        neu_full,
        preprocess,
        is_fixed_test=False,
        forbid_student_gt_download=True,
    )
    full_root = settings.neu_full_path
    try:
        full_root.resolve().relative_to((settings.repo_root / "assets").resolve())
        (full_root / "images").mkdir(parents=True, exist_ok=True)
        (full_root / "masks").mkdir(parents=True, exist_ok=True)
    except ValueError:
        pass
    _ingest_folder_samples(db, neu_full_version, full_root / "images", full_root / "masks", settings)
    seed_catalog(db)
    seed_assistant_kb(db)

    db.commit()
    _invalidate_model_lists()


def _ensure_demo_samples(db: Session, preprocess: PreprocessSpecRow, eval_version: DatasetVersion) -> None:
    """Public demo catalog shares NEU-20 origins but never stores mask_uri."""
    demo = (
        db.query(DatasetVersion)
        .filter(DatasetVersion.dataset_id == eval_version.dataset_id, DatasetVersion.kind == DEMO_CATALOG_KIND)
        .one_or_none()
    )
    if demo is None:
        demo = DatasetVersion(
            id=new_id(),
            dataset_id=eval_version.dataset_id,
            kind=DEMO_CATALOG_KIND,
            class_map_json=NEU_CLASS_MAP,
            preprocess_id=preprocess.id,
            is_fixed_test=False,
            forbid_student_gt_download=True,
        )
        db.add(demo)
        db.flush()
    for row in db.query(Sample).filter(Sample.version_id == demo.id).all():
        if row.mask_uri is not None:
            row.mask_uri = None
            db.add(row)
    existing = {
        row.sample_key for row in db.query(Sample).filter(Sample.version_id == demo.id).all()
    }
    sources = (
        db.query(Sample)
        .filter(Sample.version_id == eval_version.id)
        .order_by(Sample.sample_key.asc())
        .all()
    )
    for src in sources:
        if src.sample_key in existing:
            continue
        db.add(
            Sample(
                id=new_id(),
                version_id=demo.id,
                sample_key=src.sample_key,
                origin_uri=src.origin_uri,
                mask_uri=None,
                width=src.width,
                height=src.height,
                sha256=src.sha256,
            )
        )
