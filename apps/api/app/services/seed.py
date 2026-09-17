from __future__ import annotations

import hashlib
from pathlib import Path

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
from app.util_time import new_id

from infer.spec import BUILTIN_DISPLAY_NAMES, BUILTIN_SLUGS, BUILTIN_WEIGHT_FILES, NEU_CLASS_MAP, NEU_DEFAULT


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

    dataset = db.query(Dataset).filter(Dataset.name == "NEU-20", Dataset.visibility == "preset").one_or_none()
    if dataset is None:
        dataset = Dataset(id=new_id(), owner_id=None, name="NEU-20", visibility="preset")
        db.add(dataset)
        db.flush()
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
            is_fixed_test=True,
            forbid_student_gt_download=True,
        )
        db.add(version)
        db.flush()

    images_dir = settings.repo_root / "assets" / "samples" / "neu" / "images"
    masks_dir = settings.repo_root / "assets" / "samples" / "neu" / "masks"
    if images_dir.is_dir():
        import cv2

        existing = {
            row.sample_key
            for row in db.query(Sample).filter(Sample.version_id == version.id).all()
        }
        exts = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
        for image_path in sorted(p for p in images_dir.iterdir() if p.suffix.lower() in exts):
            key = image_path.stem
            if key in existing:
                continue
            bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if bgr is None:
                continue
            h, w = bgr.shape[:2]
            mask_path = None
            for ext in (".png", ".bmp", ".jpg", ".jpeg"):
                candidate = masks_dir / f"{key}{ext}"
                if candidate.is_file():
                    mask_path = candidate
                    break
            rel_img = image_path.relative_to(settings.repo_root / "assets").as_posix()
            mask_uri = None
            if mask_path is not None:
                mask_uri = "asset:" + mask_path.relative_to(settings.repo_root / "assets").as_posix()
            db.add(
                Sample(
                    id=new_id(),
                    version_id=version.id,
                    sample_key=key,
                    origin_uri="asset:" + rel_img,
                    mask_uri=mask_uri,
                    width=w,
                    height=h,
                    sha256=_file_sha256(image_path),
                )
            )

    db.commit()
