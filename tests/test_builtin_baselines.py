from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party"), str(ROOT / "apps" / "api")]

import pytest
from app.db.models import Model, ModelVersion, PreprocessSpecRow, User
from app.db.session import Base
from app.services.models import list_visible_versions
from app.util_time import new_id, utcnow
from infer.spec import BUILTIN_DISPLAY_NAMES, BUILTIN_SLUGS, DEMO_MODEL_SLUGS, builtin_sort_key
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

WEIGHT_DIR = ROOT / "assets" / "baselines" / "neu"


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


def test_demo_whitelist_matches_builtins() -> None:
    assert BUILTIN_SLUGS == (
        "unet",
        "deeplabv3",
        "unetpp",
        "bisenet",
        "danet",
        "pspnet",
        "segformer",
    )
    assert DEMO_MODEL_SLUGS == BUILTIN_SLUGS
    for slug in ("bisenet", "danet", "pspnet", "segformer"):
        assert slug in DEMO_MODEL_SLUGS
        assert slug in BUILTIN_DISPLAY_NAMES


def test_builtin_sort_keeps_original_three_first() -> None:
    shuffled = ["segformer", "bisenet", "unetpp", "danet", "unet", "pspnet", "deeplabv3"]
    assert sorted(shuffled, key=builtin_sort_key)[:3] == ["unet", "deeplabv3", "unetpp"]


def test_list_visible_versions_orders_builtins_by_slug(db: Session) -> None:
    user = User(
        id=new_id(),
        username="advisor",
        password_hash="x",
        role="advisor",
        status="active",
        created_at=utcnow(),
    )
    preprocess = PreprocessSpecRow(
        id=new_id(),
        name="neu_200",
        height=200,
        width=200,
        apply_clahe=True,
        sp_threshold=0.02,
        dataset="neu",
        created_at=utcnow(),
    )
    db.add(user)
    db.add(preprocess)
    db.flush()
    for slug in ("segformer", "bisenet", "unet", "danet", "deeplabv3", "pspnet", "unetpp"):
        model = Model(
            id=new_id(),
            owner_id=user.id,
            name=BUILTIN_DISPLAY_NAMES[slug],
            source="builtin",
            created_at=utcnow(),
        )
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
                requires_cuda=False,
                status="runnable",
                visibility="public",
                created_at=utcnow(),
            )
        )
    db.commit()
    items = list_visible_versions(db, user)
    assert [row["slug"] for row in items] == list(BUILTIN_SLUGS)


@pytest.mark.parametrize("slug", ["bisenet", "danet", "pspnet", "segformer"])
def test_new_baselines_load_strict_and_forward(slug: str) -> None:
    pytest.importorskip("timm")
    pytest.importorskip("torch")
    weight = WEIGHT_DIR / f"best_{slug}.pth"
    if not weight.is_file():
        pytest.skip(f"missing {weight.name}")

    import numpy as np
    import torch
    from infer.engine import (
        drop_l1,
        extract_whitelisted_state,
        get_builtin_module,
        load_checkpoint_file,
        predict_mask,
    )

    ckpt = load_checkpoint_file(weight)
    state, name = extract_whitelisted_state(ckpt)
    assert name == slug
    assert state
    cache_key = f"test-{slug}"
    try:
        module = get_builtin_module(cache_key, slug, weight, num_classes=4)
        dummy = torch.zeros(3, 200, 200)
        pred = predict_mask(module, dummy)
        assert pred.shape == (200, 200)
        assert pred.dtype == np.uint8
    finally:
        drop_l1(cache_key)
