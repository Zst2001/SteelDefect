from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party"), str(ROOT / "apps" / "api")]

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Dataset, DatasetVersion, Model, ModelVersion, PreprocessSpecRow, Sample
from app.db.session import Base
from app.errors import AppError
from app.routers import demo as demo_router
from app.routers.demo import demo_models, demo_samples
from app.services.demo import (
    catalog_has_no_gt_fields,
    get_demo_sample,
    list_demo_catalog,
    list_demo_models,
    serialize_demo_sample,
)
from app.services.seed import _ensure_demo_samples
from app.util_time import new_id, utcnow
from infer.spec import DEMO_CATALOG_KIND, DEMO_DISCLAIMER, DEMO_MODEL_SLUGS, NEU_CLASS_MAP


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


def _eval_version(db: Session, preprocess: PreprocessSpecRow, n: int = 3) -> DatasetVersion:
    dataset = Dataset(
        id=new_id(),
        owner_id=None,
        name="NEU-20",
        visibility="preset",
        created_at=utcnow(),
    )
    db.add(dataset)
    db.flush()
    version = DatasetVersion(
        id=new_id(),
        dataset_id=dataset.id,
        kind="preset",
        class_map_json=NEU_CLASS_MAP,
        preprocess_id=preprocess.id,
        is_fixed_test=True,
        forbid_student_gt_download=True,
        created_at=utcnow(),
    )
    db.add(version)
    db.flush()
    for index in range(n):
        key = f"img_{index:02d}"
        db.add(
            Sample(
                id=new_id(),
                version_id=version.id,
                sample_key=key,
                origin_uri=f"asset:samples/neu/images/{key}.png",
                mask_uri=f"asset:samples/neu/masks/{key}.png",
                width=200,
                height=200,
                sha256="abc",
            )
        )
    db.flush()
    return version


def test_serialize_demo_sample_omits_gt_fields() -> None:
    sample = Sample(
        id="s1",
        version_id="v1",
        sample_key="scratches_01",
        origin_uri="asset:samples/neu/images/scratches_01.png",
        mask_uri="asset:samples/neu/masks/scratches_01.png",
        width=200,
        height=200,
        sha256="abc",
    )
    payload = serialize_demo_sample(sample)
    assert payload["sample_key"] == "scratches_01"
    assert payload["preview_url"].endswith("/scratches_01/preview")
    assert catalog_has_no_gt_fields(payload)
    for banned in ("mask_uri", "has_mask", "origin_uri", "has_gt"):
        assert banned not in payload


def test_demo_catalog_copies_origins_without_masks(db: Session) -> None:
    preprocess = _preprocess(db)
    eval_version = _eval_version(db, preprocess, n=4)
    _ensure_demo_samples(db, preprocess, eval_version)
    db.commit()
    catalog = list_demo_catalog(db)
    assert catalog["n"] == 4
    assert catalog["disclaimer"] == DEMO_DISCLAIMER
    assert catalog_has_no_gt_fields(catalog)
    demo = db.query(DatasetVersion).filter(DatasetVersion.kind == DEMO_CATALOG_KIND).one()
    assert demo.is_fixed_test is False
    rows = db.query(Sample).filter(Sample.version_id == demo.id).all()
    assert len(rows) == 4
    assert all(row.mask_uri is None for row in rows)
    eval_keys = {row.sample_key for row in db.query(Sample).filter(Sample.version_id == eval_version.id)}
    assert {row.sample_key for row in rows} == eval_keys


def test_unknown_sample_not_in_demo_catalog(db: Session) -> None:
    preprocess = _preprocess(db)
    eval_version = _eval_version(db, preprocess, n=1)
    _ensure_demo_samples(db, preprocess, eval_version)
    db.commit()
    with pytest.raises(AppError) as exc:
        get_demo_sample(db, "not_a_sample")
    assert exc.value.status_code == 404


def test_demo_models_only_cpu_builtin_whitelist(db: Session) -> None:
    preprocess = _preprocess(db)
    specs = [
        ("unet", "UNet", "builtin", False, "runnable"),
        ("deeplabv3", "DeepLabV3+", "builtin", True, "runnable"),
        ("unetpp", "UNet++", "builtin", False, "cannot_start"),
        ("unet", "学生UNet", "student", False, "runnable"),
    ]
    for slug, name, source, cuda, status in specs:
        model = Model(id=new_id(), owner_id=None, name=name, source=source, created_at=utcnow())
        db.add(model)
        db.flush()
        db.add(
            ModelVersion(
                id=new_id(),
                model_id=model.id,
                slug=slug,
                num_classes=4,
                in_channels=3,
                input_h=200,
                input_w=200,
                preprocess_id=preprocess.id,
                requires_cuda=cuda,
                status=status,
                visibility="public",
                created_at=utcnow(),
            )
        )
    db.commit()
    payload = list_demo_models(db)
    assert payload["disclaimer"] == DEMO_DISCLAIMER
    slugs = [row["slug"] for row in payload["items"]]
    assert slugs == ["unet"]
    assert all(row["source"] == "builtin" for row in payload["items"])
    assert catalog_has_no_gt_fields(payload)
    assert set(DEMO_MODEL_SLUGS) == {"unet", "deeplabv3", "unetpp"}


def test_demo_http_handlers_are_public_and_omit_gt(db: Session) -> None:
    preprocess = _preprocess(db)
    eval_version = _eval_version(db, preprocess, n=2)
    _ensure_demo_samples(db, preprocess, eval_version)
    model = Model(id=new_id(), owner_id=None, name="UNet", source="builtin", created_at=utcnow())
    db.add(model)
    db.flush()
    db.add(
        ModelVersion(
            id=new_id(),
            model_id=model.id,
            slug="unet",
            num_classes=4,
            in_channels=3,
            input_h=200,
            input_w=200,
            preprocess_id=preprocess.id,
            requires_cuda=False,
            status="runnable",
            visibility="public",
            created_at=utcnow(),
        )
    )
    db.commit()

    catalog = demo_samples(db=db)
    models = demo_models(db=db)
    assert catalog["n"] == 2
    assert catalog_has_no_gt_fields(catalog)
    assert catalog_has_no_gt_fields(models)
    assert [row["slug"] for row in models["items"]] == ["unet"]

    names = []
    for route in demo_router.router.routes:
        for dep in route.dependant.dependencies:
            if dep.call is not None:
                names.append(dep.call.__name__)
    assert "get_current_user" not in names
    assert "require_roles" not in names


def test_neu_asset_folder_has_twenty_images_when_present() -> None:
    images = ROOT / "assets" / "samples" / "neu" / "images"
    if not images.is_dir():
        pytest.skip("NEU sample images not present")
    keys = sorted(p.stem for p in images.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"})
    assert len(keys) == 20
