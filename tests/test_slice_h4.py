from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party"), str(ROOT / "apps" / "api")]

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Dataset, DatasetVersion, Model, ModelVersion, PreprocessSpecRow, Sample, User
from app.db.session import Base
from app.errors import AppError
from app.services.demo import create_demo_task
from app.services.demo_identity import DemoIdentity, client_ip
from app.services.demo_quota import (
    MemoryQuotaStore,
    QUOTA_MESSAGE,
    assert_demo_submit_rate,
    demo_ip_key,
    reserve_guest_quota,
    set_quota_store,
)
from app.services.seed import _ensure_demo_samples
from app.util_time import new_id, utcnow
from infer.spec import NEU_CLASS_MAP


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


@pytest.fixture
def quota(monkeypatch: pytest.MonkeyPatch) -> MemoryQuotaStore:
    store = MemoryQuotaStore()
    set_quota_store(store)
    monkeypatch.setattr("app.services.demo.invalidate_after_write", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.demo._enqueue_task", lambda *args, **kwargs: None)
    yield store
    set_quota_store(None)


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


def _catalog(db: Session, preprocess: PreprocessSpecRow) -> None:
    dataset = Dataset(id=new_id(), owner_id=None, name="NEU-20", visibility="preset", created_at=utcnow())
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
    for index in range(4):
        key = f"{index + 1:06d}"
        db.add(
            Sample(
                id=new_id(),
                version_id=version.id,
                sample_key=key,
                origin_uri=f"asset:samples/neu/images/{key}.jpg",
                mask_uri=f"asset:samples/neu/masks/{key}.png",
                width=200,
                height=200,
                sha256="abc",
            )
        )
    db.flush()
    _ensure_demo_samples(db, preprocess, version)
    db.commit()


def _unet(db: Session, preprocess: PreprocessSpecRow) -> ModelVersion:
    model = Model(id=new_id(), owner_id=None, name="UNet", source="builtin", created_at=utcnow())
    db.add(model)
    db.flush()
    version = ModelVersion(
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
    db.add(version)
    db.commit()
    return version


def _guest(sid: str = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", ip_hash: str = "ip-a") -> DemoIdentity:
    return DemoIdentity(sid=sid, user=None, ip="127.0.0.1", ip_hash=ip_hash)


def test_rolling_window_and_ip_and_session(quota: MemoryQuotaStore) -> None:
    identity = _guest()
    now = 1_000_000.0
    window = 24 * 3600
    for index in range(3):
        assert quota.reserve(identity.ip_hash, identity.sid, f"t{index}", now=now, window=window, limit=3)
    assert quota.reserve(identity.ip_hash, identity.sid, "t3", now=now, window=window, limit=3) is False
    other_sid = _guest(sid="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    assert quota.reserve(other_sid.ip_hash, other_sid.sid, "t-new-sid", now=now, window=window, limit=3) is False
    assert quota.reserve(identity.ip_hash, identity.sid, "t-old", now=now + window + 1, window=window, limit=3) is True


def test_fourth_guest_enqueue_is_quota(db: Session, quota: MemoryQuotaStore) -> None:
    preprocess = _preprocess(db)
    _catalog(db, preprocess)
    unet = _unet(db, preprocess)
    identity = _guest()
    for _ in range(3):
        create_demo_task(db, identity, sample_keys=["000001"], baseline_version_ids=[unet.id])
    with pytest.raises(AppError) as exc:
        create_demo_task(db, identity, sample_keys=["000001"], baseline_version_ids=[unet.id])
    assert exc.value.code == "DEMO_QUOTA"
    assert exc.value.status_code == 429
    assert "明日再试或登录" in exc.value.message
    assert "明日再试或登录" in QUOTA_MESSAGE
    with pytest.raises(AppError) as still:
        create_demo_task(
            db,
            _guest(sid="cccccccc-cccc-cccc-cccc-cccccccccccc"),
            sample_keys=["000001"],
            baseline_version_ids=[unet.id],
        )
    assert still.value.code == "DEMO_QUOTA"


def test_protocol_failure_does_not_consume_quota(db: Session, quota: MemoryQuotaStore) -> None:
    preprocess = _preprocess(db)
    _catalog(db, preprocess)
    unet = _unet(db, preprocess)
    identity = _guest()
    create_demo_task(db, identity, sample_keys=["000001"], baseline_version_ids=[unet.id])
    with pytest.raises(AppError) as bad:
        create_demo_task(db, identity, sample_keys=["not-a-sample"], baseline_version_ids=[unet.id])
    assert bad.value.code == "SAMPLE_NOT_FOUND"
    create_demo_task(db, identity, sample_keys=["000002"], baseline_version_ids=[unet.id])
    create_demo_task(db, identity, sample_keys=["000003"], baseline_version_ids=[unet.id])
    assert len(quota.zsets[demo_ip_key(identity.ip_hash)]) == 3


def test_logged_in_demo_skips_guest_quota(db: Session, quota: MemoryQuotaStore) -> None:
    preprocess = _preprocess(db)
    _catalog(db, preprocess)
    unet = _unet(db, preprocess)
    student = User(
        id=new_id(),
        username="stu",
        password_hash="x",
        role="student",
        status="active",
        quota_json={},
        created_at=utcnow(),
    )
    db.add(student)
    db.commit()
    identity = DemoIdentity(sid="dddddddd-dddd-dddd-dddd-dddddddddddd", user=student, ip="127.0.0.1", ip_hash="ip-a")
    for _ in range(4):
        task = create_demo_task(db, identity, sample_keys=["000001"], baseline_version_ids=[unet.id])
        assert task.creator_id == student.id
        assert task.guest_sid is None
    assert quota.zsets[demo_ip_key("ip-a")] == {}
    assert reserve_guest_quota(identity, "ignored") is True


def test_submit_rate_limit(quota: MemoryQuotaStore) -> None:
    settings = SimpleNamespace(demo_submit_max=2, demo_submit_window_sec=3600)
    identity = _guest()
    assert_demo_submit_rate(identity, settings)
    assert_demo_submit_rate(identity, settings)
    with pytest.raises(AppError) as exc:
        assert_demo_submit_rate(identity, settings)
    assert exc.value.code == "DEMO_SUBMIT_RATE"
    assert exc.value.status_code == 429


def test_client_ip_rightmost_forwarded_hop_only_behind_local_proxy() -> None:
    request = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"x-forwarded-for": "203.0.113.9, 10.0.0.8"},
    )
    trusted = SimpleNamespace(trust_proxy=True)
    untrusted = SimpleNamespace(trust_proxy=False)
    assert client_ip(request, trusted) == "10.0.0.8"
    assert client_ip(request, untrusted) == "127.0.0.1"
