from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party"), str(ROOT / "apps" / "api")]

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Dataset, DatasetVersion, Model, ModelVersion, PreprocessSpecRow, Sample, User
from app.db.session import Base
from app.errors import AppError
from app.services.demo import (
    assert_demo_worker_contract,
    create_demo_task,
    get_visible_demo_task,
    payload_has_no_metric_fields,
    serialize_demo_task,
)
from app.services.demo_identity import DemoIdentity
from app.services.seed import _ensure_demo_samples
from app.services.tasks import create_compare_task, serialize_metrics
from app.util_time import new_id, utcnow
from infer.spec import DEMO_CATALOG_KIND, DEMO_DISCLAIMER, NEU_CLASS_MAP


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


@pytest.fixture(autouse=True)
def no_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    # Legacy authorization fixtures have metadata-only asset URIs. C input I/O is
    # tested separately with actual temporary files, never these real asset paths.
    monkeypatch.setattr("app.services.tasks.freeze_inputs", lambda *a: None)
    monkeypatch.setattr("app.services.demo.freeze_inputs", lambda *a: None)
    monkeypatch.setattr("app.services.input_freeze.verify_inputs", lambda *a: {})
    monkeypatch.setattr("app.services.demo.invalidate_after_write", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.demo._enqueue_task", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.demo.reserve_guest_quota", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.services.demo.release_guest_quota", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.tasks.invalidate_after_write", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.tasks._enqueue_task", lambda *args, **kwargs: None)


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


def _eval_and_demo(db: Session, preprocess: PreprocessSpecRow, n: int = 6) -> DatasetVersion:
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
    return version


def _builtin(
    db: Session,
    preprocess: PreprocessSpecRow,
    slug: str = "unet",
    *,
    cuda: bool = False,
    source: str = "builtin",
) -> ModelVersion:
    model = Model(id=new_id(), owner_id=None, name=slug, source=source, created_at=utcnow())
    db.add(model)
    db.flush()
    version = ModelVersion(
        id=new_id(),
        model_id=model.id,
        slug=slug,
        num_classes=4,
        in_channels=3,
        input_h=200,
        input_w=200,
        preprocess_id=preprocess.id,
        requires_cuda=cuda,
        status="runnable",
        visibility="public",
        created_at=utcnow(),
    )
    db.add(version)
    db.commit()
    return version


def _guest(sid: str = "11111111-1111-1111-1111-111111111111") -> DemoIdentity:
    return DemoIdentity(sid=sid, user=None, ip="127.0.0.1", ip_hash="hash-a")


def _user(db: Session, role: str = "student") -> User:
    row = User(
        id=new_id(),
        username=f"{role}-{new_id()[:8]}",
        password_hash="x",
        role=role,
        status="active",
        quota_json={"max_upload_images": 50},
        created_at=utcnow(),
    )
    db.add(row)
    db.commit()
    return row


def test_guest_demo_task_is_type_demo_without_gt(db: Session) -> None:
    preprocess = _preprocess(db)
    _eval_and_demo(db, preprocess)
    unet = _builtin(db, preprocess)
    identity = _guest()
    task = create_demo_task(
        db,
        identity,
        sample_keys=["000001", "000002"],
        baseline_version_ids=[unet.id],
    )
    assert task.type == "demo"
    assert task.has_gt is False
    assert task.creator_id is None
    assert task.guest_sid == identity.sid
    assert task.guest_ip_hash == identity.ip_hash
    payload = serialize_demo_task(db, task)
    assert payload["type"] == "demo"
    assert payload["disclaimer"] == DEMO_DISCLAIMER
    assert payload_has_no_metric_fields(payload)
    assert "has_gt" not in payload


def test_logged_in_demo_still_has_no_metrics(db: Session) -> None:
    preprocess = _preprocess(db)
    _eval_and_demo(db, preprocess)
    unet = _builtin(db, preprocess)
    student = _user(db)
    identity = DemoIdentity(sid="22222222-2222-2222-2222-222222222222", user=student, ip="1.1.1.1", ip_hash="h")
    task = create_demo_task(db, identity, sample_keys=["000001"], baseline_version_ids=[unet.id])
    assert task.creator_id == student.id
    assert task.guest_sid is None
    assert task.has_gt is False
    with pytest.raises(AppError) as exc:
        serialize_metrics(task)
    assert exc.value.code == "DEMO_NO_METRICS"
    assert exc.value.status_code == 404


def test_demo_rejects_count_student_and_unknown_sample(db: Session) -> None:
    preprocess = _preprocess(db)
    _eval_and_demo(db, preprocess, n=6)
    unet = _builtin(db, preprocess)
    student_mv = _builtin(db, preprocess, slug="unet", source="student")
    identity = _guest()
    with pytest.raises(AppError) as too_many:
        create_demo_task(
            db,
            identity,
            sample_keys=[f"{i:06d}" for i in range(1, 7)],
            baseline_version_ids=[unet.id],
        )
    assert too_many.value.code == "SAMPLE_COUNT"
    with pytest.raises(AppError) as unknown:
        create_demo_task(db, identity, sample_keys=["not-in-catalog"], baseline_version_ids=[unet.id])
    assert unknown.value.code == "SAMPLE_NOT_FOUND"
    with pytest.raises(AppError) as forbidden:
        create_demo_task(db, identity, sample_keys=["000001"], baseline_version_ids=[student_mv.id])
    assert forbidden.value.code == "DEMO_MODEL_FORBIDDEN"


def test_demo_task_auth_is_sid_or_creator_or_advisor(db: Session) -> None:
    preprocess = _preprocess(db)
    _eval_and_demo(db, preprocess)
    unet = _builtin(db, preprocess)
    owner = _guest()
    task = create_demo_task(db, owner, sample_keys=["000001"], baseline_version_ids=[unet.id])
    visible = get_visible_demo_task(db, task.id, owner)
    assert visible.id == task.id
    with pytest.raises(AppError) as hidden:
        get_visible_demo_task(db, task.id, _guest("33333333-3333-3333-3333-333333333333"))
    assert hidden.value.status_code == 404
    advisor = _user(db, role="advisor")
    advisor_id = DemoIdentity(sid="44444444-4444-4444-4444-444444444444", user=advisor, ip="2.2.2.2", ip_hash="b")
    assert get_visible_demo_task(db, task.id, advisor_id).id == task.id


def test_compare_cannot_use_demo_catalog(db: Session) -> None:
    preprocess = _preprocess(db)
    _eval_and_demo(db, preprocess)
    unet = _builtin(db, preprocess)
    demo = db.query(DatasetVersion).filter(DatasetVersion.kind == DEMO_CATALOG_KIND).one()
    student = _user(db)
    with pytest.raises(AppError) as exc:
        create_compare_task(db, student, batch_id=demo.id, baseline_version_ids=[unet.id], student_version_id=None)
    assert exc.value.code == "DEMO_USE_DEMO_API"


def test_worker_contract_refuses_gt(db: Session) -> None:
    preprocess = _preprocess(db)
    _eval_and_demo(db, preprocess)
    unet = _builtin(db, preprocess)
    task = create_demo_task(db, _guest(), sample_keys=["000001"], baseline_version_ids=[unet.id])
    assert_demo_worker_contract(db, task)
    task.has_gt = True
    with pytest.raises(RuntimeError, match="has_gt"):
        assert_demo_worker_contract(db, task)


def test_worker_source_hard_branches_demo() -> None:
    text = (ROOT / "apps" / "worker" / "jobs.py").read_text(encoding="utf-8")
    assert "def run_demo" in text
    assert 'expected_types=("demo",)' in text
    from types import SimpleNamespace
    from apps.worker.jobs import _run_compare_body
    for kind in ("demo", "classification"):
        with pytest.raises(RuntimeError, match="refused"):
            _run_compare_body(None, SimpleNamespace(type=kind), None)
    assert "demo forbids student models" in text
    assert "demo worker refused sample with mask_uri" in text
