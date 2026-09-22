from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party"), str(ROOT / "apps" / "api")]

import numpy as np
import pytest
from app.config import Settings
from app.db.models import Dataset, DatasetVersion, PreprocessSpecRow, Sample, User
from app.db.session import Base
from app.errors import AppError
from app.routers.datasets import summarize_dataset_version
from app.services.datasets import (
    catalog_versions,
    list_dataset_catalog,
    page_samples,
    summarize_dataset_counts,
)
from app.services.seed import _ingest_folder_samples
from app.services.storage import resolve_uri
from app.util_time import new_id, utcnow
from infer.spec import DEMO_CATALOG_KIND, NEU_CLASS_MAP
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _user(db: Session, role: str = "student") -> User:
    row = User(
        id=new_id(),
        username=f"{role}-{new_id()[:8]}",
        password_hash="unused",
        role=role,
        status="active",
        quota_json={"max_upload_images": 50},
        created_at=utcnow(),
    )
    db.add(row)
    db.commit()
    return row


def _preprocess(db: Session) -> PreprocessSpecRow:
    row = PreprocessSpecRow(
        id=new_id(),
        name="neu_200",
        height=200,
        width=200,
        apply_clahe=True,
        sp_threshold=0.02,
        dataset="neu",
        created_at=utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def _dataset(db: Session, name: str, *, visibility: str = "preset", owner_id: str | None = None) -> Dataset:
    row = Dataset(
        id=new_id(),
        owner_id=owner_id,
        name=name,
        visibility=visibility,
        created_at=utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def _version(
    db: Session,
    dataset: Dataset,
    preprocess: PreprocessSpecRow,
    *,
    kind: str = "preset",
    is_fixed_test: bool = False,
) -> DatasetVersion:
    row = DatasetVersion(
        id=new_id(),
        dataset_id=dataset.id,
        kind=kind,
        class_map_json=NEU_CLASS_MAP,
        preprocess_id=preprocess.id,
        is_fixed_test=is_fixed_test,
        forbid_student_gt_download=True,
        created_at=utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def _sample(db: Session, version: DatasetVersion, key: str, *, mask: bool = True) -> Sample:
    row = Sample(
        id=new_id(),
        version_id=version.id,
        sample_key=key,
        origin_uri=f"asset:samples/neu/images/{key}.png",
        mask_uri=f"asset:samples/neu/masks/{key}.png" if mask else None,
        width=200,
        height=200,
        sha256="x",
    )
    db.add(row)
    db.flush()
    return row


def test_full_neu_with_masks_is_not_eval_ready() -> None:
    version = DatasetVersion(
        id="full",
        dataset_id="d",
        kind="preset",
        class_map_json=NEU_CLASS_MAP,
        preprocess_id="p",
        is_fixed_test=False,
        forbid_student_gt_download=True,
        created_at=utcnow(),
    )
    summary = summarize_dataset_counts(version, sample_count=3600, missing_masks=0)
    assert summary["has_gt"] is True
    assert summary["eval_ready"] is False
    assert summary["browse_only"] is True


def test_list_omits_samples_and_hides_demo_catalog(db: Session) -> None:
    user = _user(db)
    preprocess = _preprocess(db)
    dataset = _dataset(db, "NEU-20")
    eval_version = _version(db, dataset, preprocess, is_fixed_test=True)
    demo = _version(db, dataset, preprocess, kind=DEMO_CATALOG_KIND, is_fixed_test=False)
    for index in range(3):
        _sample(db, eval_version, f"k{index}")
        _sample(db, demo, f"k{index}", mask=False)
    db.commit()

    catalog = list_dataset_catalog(db, user)
    assert catalog["items"][0]["name"] == "NEU-20"
    assert "samples" not in catalog["items"][0]
    versions = catalog["items"][0]["versions"]
    assert len(versions) == 1
    assert versions[0]["eval_ready"] is True
    assert versions[0]["sample_count"] == 3
    assert catalog_versions(db, dataset.id)[0].id == eval_version.id
    assert demo.id not in {row["id"] for row in versions}


def test_pagination_does_not_return_whole_set(db: Session) -> None:
    user = _user(db)
    preprocess = _preprocess(db)
    dataset = _dataset(db, "NEU")
    version = _version(db, dataset, preprocess, is_fixed_test=False)
    for index in range(30):
        _sample(db, version, f"{index:03d}")
    db.commit()
    page = page_samples(db, user, dataset.id, version.id, offset=0, limit=24)
    assert page["total"] == 30
    assert len(page["items"]) == 24
    assert page["items"][0]["sample_key"] == "000"
    assert "preview_url" in page["items"][0]
    second = page_samples(db, user, dataset.id, version.id, offset=24, limit=24)
    assert len(second["items"]) == 6


def test_private_dataset_hidden_from_other_student(db: Session) -> None:
    owner = _user(db, "student")
    stranger = _user(db, "student")
    preprocess = _preprocess(db)
    dataset = _dataset(db, "upload-x", visibility="private", owner_id=owner.id)
    version = _version(db, dataset, preprocess, kind="upload_batch")
    _sample(db, version, "a")
    db.commit()
    mine = list_dataset_catalog(db, owner)
    theirs = list_dataset_catalog(db, stranger)
    assert any(row["id"] == dataset.id for row in mine["items"])
    assert all(row["id"] != dataset.id for row in theirs["items"])
    with pytest.raises(AppError) as forbidden:
        page_samples(db, stranger, dataset.id, version.id, offset=0, limit=24)
    assert forbidden.value.code == "FORBIDDEN"


def test_ingest_external_folder_uses_neufull_uri(tmp_path: Path, db: Session) -> None:
    cv2 = pytest.importorskip("cv2")
    images = tmp_path / "images"
    masks = tmp_path / "masks"
    images.mkdir()
    masks.mkdir()
    pixel = np.zeros((16, 16, 3), dtype=np.uint8)
    cv2.imwrite(str(images / "coupon_01.png"), pixel)
    cv2.imwrite(str(masks / "coupon_01.png"), np.zeros((16, 16), dtype=np.uint8))
    settings = Settings(neu_full_root=str(tmp_path), storage_root=str(tmp_path / "storage"))
    preprocess = _preprocess(db)
    dataset = _dataset(db, "NEU")
    version = _version(db, dataset, preprocess, is_fixed_test=False)
    added = _ingest_folder_samples(db, version, images, masks, settings)
    db.commit()
    assert added == 1
    sample = db.query(Sample).one()
    assert sample.origin_uri.startswith("neufull:")
    assert sample.mask_uri and sample.mask_uri.startswith("neufull:")
    path = resolve_uri(sample.origin_uri, settings)
    assert path.is_file()
    again = _ingest_folder_samples(db, version, images, masks, settings)
    assert again == 0


def test_router_summary_still_accepts_sample_list() -> None:
    preset = DatasetVersion(
        id="p",
        dataset_id="d",
        kind="preset",
        class_map_json=NEU_CLASS_MAP,
        preprocess_id="x",
        is_fixed_test=True,
        forbid_student_gt_download=True,
        created_at=utcnow(),
    )
    paired = [Sample(id="1", version_id="p", sample_key="a", origin_uri="asset:a", mask_uri="asset:m", width=1, height=1, sha256="s")]
    assert summarize_dataset_version(preset, paired)["eval_ready"] is True
    assert summarize_dataset_version(preset, [])["eval_ready"] is False
