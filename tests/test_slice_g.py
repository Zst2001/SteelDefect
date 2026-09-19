from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party"), str(ROOT / "apps" / "api")]

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    AuditLog,
    Dataset,
    DatasetVersion,
    Model,
    ModelVersion,
    PreprocessSpecRow,
    Sample,
    Task,
    TaskModel,
    TaskSample,
    User,
)
from app.db.session import Base
from app.errors import AppError
from app.services.demo import create_demo_task, payload_has_no_metric_fields, serialize_demo_task
from app.services.demo_identity import DemoIdentity
from app.services.records import (
    list_records,
    maybe_mark_advisor_seen,
    patch_record,
    rerun_record,
    serialize_record,
    submit_to_advisor,
    withdraw_from_advisor,
)
from app.services.seed import _ensure_demo_samples
from app.services.tasks import get_visible_task
from app.util_time import new_id, utcnow
from infer.spec import NEU_CLASS_MAP

WEB = ROOT / "apps" / "web" / "src"


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
def no_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.demo.invalidate_after_write", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.demo._enqueue_task", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.demo.reserve_guest_quota", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.services.demo.release_guest_quota", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.tasks.invalidate_after_write", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.tasks._enqueue_task", lambda *args, **kwargs: None)


def _user(db: Session, role: str = "student", username: str | None = None) -> User:
    row = User(
        id=new_id(),
        username=username or f"{role}-{new_id()[:8]}",
        password_hash="x",
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


def _version(
    db: Session,
    preprocess: PreprocessSpecRow,
    *,
    kind: str = "upload_batch",
    n: int = 2,
    owner_id: str | None = None,
    visibility: str = "private",
    is_fixed_test: bool = False,
    with_mask: bool = True,
) -> DatasetVersion:
    dataset = Dataset(
        id=new_id(),
        owner_id=owner_id,
        name=f"set-{kind}",
        visibility=visibility,
        created_at=utcnow(),
    )
    db.add(dataset)
    db.flush()
    version = DatasetVersion(
        id=new_id(),
        dataset_id=dataset.id,
        kind=kind,
        class_map_json=NEU_CLASS_MAP,
        preprocess_id=preprocess.id,
        is_fixed_test=is_fixed_test,
        forbid_student_gt_download=is_fixed_test,
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
                mask_uri=f"asset:samples/neu/masks/{key}.png" if with_mask else None,
                width=200,
                height=200,
                sha256="abc",
            )
        )
    db.commit()
    return version


def _builtin(db: Session, preprocess: PreprocessSpecRow, slug: str = "unet") -> ModelVersion:
    model = Model(id=new_id(), owner_id=None, name=slug, source="builtin", created_at=utcnow())
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
        requires_cuda=False,
        status="runnable",
        visibility="public",
        created_at=utcnow(),
    )
    db.add(version)
    db.commit()
    return version


def _task(
    db: Session,
    user: User,
    version: DatasetVersion,
    model: ModelVersion,
    *,
    type: str = "compare",
    status: str = "success",
    archived: bool = False,
) -> Task:
    samples = db.query(Sample).filter(Sample.version_id == version.id).order_by(Sample.sample_key.asc()).all()
    task = Task(
        id=new_id(),
        type=type,
        creator_id=user.id,
        dataset_version_id=version.id,
        preprocess_id=model.preprocess_id,
        status=status,
        has_gt=type != "demo",
        archived=archived,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(task)
    db.flush()
    db.add(
        TaskModel(
            id=new_id(),
            task_id=task.id,
            model_version_id=model.id,
            role="baseline",
            sort_order=0,
            status=status,
        )
    )
    for index, sample in enumerate(samples):
        db.add(TaskSample(id=new_id(), task_id=task.id, sample_id=sample.id, sort_order=index))
    db.commit()
    db.refresh(task)
    return task


def _ids(payload: dict) -> set[str]:
    return {row["id"] for row in payload["items"]}


def test_classmate_cannot_see_or_operate_peer_task(db: Session) -> None:
    preprocess = _preprocess(db)
    alice = _user(db, username="alice")
    bob = _user(db, username="bob")
    version = _version(db, preprocess, owner_id=alice.id)
    model = _builtin(db, preprocess)
    task = _task(db, alice, version, model)
    mine = list_records(db, bob, scope="mine")
    assert task.id not in _ids(mine)
    with pytest.raises(AppError) as hidden:
        get_visible_task(db, task.id, bob)
    assert hidden.value.status_code == 404
    with pytest.raises(AppError) as forbidden:
        submit_to_advisor(db, bob, task.id)
    assert forbidden.value.status_code == 404


def test_demo_cannot_submit_and_list_has_no_metrics(db: Session) -> None:
    preprocess = _preprocess(db)
    student = _user(db)
    eval_version = _version(db, preprocess, kind="preset", visibility="preset", is_fixed_test=True, owner_id=None)
    _ensure_demo_samples(db, preprocess, eval_version)
    db.commit()
    unet = _builtin(db, preprocess)
    identity = DemoIdentity(sid=new_id(), user=student, ip="1.1.1.1", ip_hash="h")
    demo = create_demo_task(db, identity, sample_keys=["000001"], baseline_version_ids=[unet.id])
    demo.status = "success"
    db.add(demo)
    db.commit()
    with pytest.raises(AppError) as exc:
        submit_to_advisor(db, student, demo.id)
    assert exc.value.code == "DEMO_NO_SUBMIT"
    payload = list_records(db, student, scope="mine", type="demo")
    assert demo.id in _ids(payload)
    item = next(row for row in payload["items"] if row["id"] == demo.id)
    assert item["can_submit"] is False
    assert item["open_path"] == f"/demo/{demo.id}"
    assert item["has_gt"] is False
    assert payload_has_no_metric_fields(item)


def test_advisor_inbox_only_submitted_lab_tasks(db: Session) -> None:
    preprocess = _preprocess(db)
    student = _user(db, username="stu")
    peer = _user(db, username="peer")
    advisor = _user(db, role="advisor", username="adv")
    version = _version(db, preprocess, owner_id=student.id)
    peer_version = _version(db, preprocess, owner_id=peer.id)
    model = _builtin(db, preprocess)
    ready = _task(db, student, version, model, status="success")
    queued = _task(db, student, version, model, status="queued")
    hidden = _task(db, peer, peer_version, model, status="success")
    eval_version = _version(db, preprocess, kind="preset", visibility="preset", is_fixed_test=True)
    _ensure_demo_samples(db, preprocess, eval_version)
    db.commit()
    demo = create_demo_task(
        db,
        DemoIdentity(sid=new_id(), user=student, ip="1.1.1.1", ip_hash="h"),
        sample_keys=["000001"],
        baseline_version_ids=[model.id],
    )
    demo.status = "success"
    db.add(demo)
    db.commit()
    submit_to_advisor(db, student, ready.id)
    inbox = list_records(db, advisor, scope="inbox")
    assert _ids(inbox) == {ready.id}
    assert inbox["items"][0]["creator_username"] == "stu"
    with pytest.raises(AppError) as denied:
        list_records(db, student, scope="inbox")
    assert denied.value.status_code == 403
    assert queued.id not in _ids(inbox)
    assert hidden.id not in _ids(inbox)
    assert demo.id not in _ids(inbox)
    empty_demo = list_records(db, advisor, scope="inbox", type="demo")
    assert empty_demo["total"] == 0


def test_withdraw_blocked_after_advisor_seen(db: Session) -> None:
    preprocess = _preprocess(db)
    student = _user(db)
    advisor = _user(db, role="advisor")
    version = _version(db, preprocess, owner_id=student.id)
    model = _builtin(db, preprocess)
    task = _task(db, student, version, model)
    submit_to_advisor(db, student, task.id)
    logs = db.query(AuditLog).filter(AuditLog.action == "task.submit_advisor").all()
    assert len(logs) == 1
    withdraw_from_advisor(db, student, task.id)
    assert get_visible_task(db, task.id, student).submitted_to_advisor_at is None
    submit_to_advisor(db, student, task.id)
    visible = get_visible_task(db, task.id, advisor)
    maybe_mark_advisor_seen(db, visible, advisor)
    assert visible.advisor_seen_at is not None
    with pytest.raises(AppError) as seen:
        withdraw_from_advisor(db, student, task.id)
    assert seen.value.code == "ALREADY_SEEN"
    assert seen.value.status_code == 409
    pending = list_records(db, advisor, scope="inbox", inbox_state="pending")
    assert task.id not in _ids(pending)
    already = list_records(db, advisor, scope="inbox", inbox_state="seen")
    assert task.id in _ids(already)


def test_rerun_compare_and_demo_create_new_ids(db: Session) -> None:
    preprocess = _preprocess(db)
    student = _user(db)
    version = _version(db, preprocess, owner_id=student.id)
    model = _builtin(db, preprocess)
    compare = _task(db, student, version, model)
    clone = rerun_record(db, student, compare.id)
    assert clone.id != compare.id
    assert clone.type == "compare"
    assert clone.creator_id == student.id
    assert clone.status == "queued"
    assert db.get(Task, compare.id) is not None

    eval_version = _version(db, preprocess, kind="preset", visibility="preset", is_fixed_test=True)
    _ensure_demo_samples(db, preprocess, eval_version)
    db.commit()
    demo = create_demo_task(
        db,
        DemoIdentity(sid=new_id(), user=student, ip="1.1.1.1", ip_hash="h"),
        sample_keys=["000001"],
        baseline_version_ids=[model.id],
    )
    demo_clone = rerun_record(db, student, demo.id)
    assert demo_clone.id != demo.id
    assert demo_clone.type == "demo"
    assert demo_clone.creator_id == student.id
    body = serialize_demo_task(db, demo_clone)
    assert payload_has_no_metric_fields(body)


def test_note_archive_and_archived_submit_blocked(db: Session) -> None:
    preprocess = _preprocess(db)
    student = _user(db)
    advisor = _user(db, role="advisor")
    version = _version(db, preprocess, owner_id=student.id)
    model = _builtin(db, preprocess)
    task = _task(db, student, version, model)
    patched = patch_record(db, student, task.id, note="  给导师看  ", archived=None)
    assert patched.note == "给导师看"
    payload = serialize_record(db, patched, student)
    assert payload["can_note"] is True
    with pytest.raises(AppError) as too_long:
        patch_record(db, student, task.id, note="x" * 256)
    assert too_long.value.code == "NOTE_TOO_LONG"
    submit_to_advisor(db, student, task.id)
    patch_record(db, student, task.id, archived=True)
    inbox = list_records(db, advisor, scope="inbox")
    assert task.id in _ids(inbox)
    mine_live = list_records(db, student, scope="mine", archived=False)
    assert task.id not in _ids(mine_live)
    mine_archived = list_records(db, student, scope="mine", archived=True)
    assert task.id in _ids(mine_archived)
    other = _task(db, student, version, model)
    patch_record(db, student, other.id, archived=True)
    with pytest.raises(AppError) as archived:
        submit_to_advisor(db, student, other.id)
    assert archived.value.code == "ARCHIVED"
    with pytest.raises(AppError) as rerun:
        rerun_record(db, student, other.id)
    assert rerun.value.code == "ARCHIVED"
    with pytest.raises(AppError) as advisor_patch:
        patch_record(db, advisor, task.id, note="改学生备注")
    assert advisor_patch.value.status_code == 403


def test_records_page_is_private_and_demo_has_no_metrics() -> None:
    router = (WEB / "router" / "index.ts").read_text(encoding="utf-8")
    page = (WEB / "views" / "records" / "RecordsView.vue").read_text(encoding="utf-8")
    workbench = (WEB / "views" / "WorkbenchView.vue").read_text(encoding="utf-8")
    labels = (WEB / "api" / "labels.ts").read_text(encoding="utf-8")
    models = (ROOT / "apps" / "api" / "app" / "db" / "models.py").read_text(encoding="utf-8")
    assert "RecordsView.vue" in router
    assert 'path: "records"' in router
    records_line = next(line for line in router.splitlines() if 'path: "records"' in line)
    assert "public" not in records_line
    for token in ("/metrics", "mIoU", "mDice"):
        assert token not in page
    assert "提交导师" in page
    assert "同学之间互不可见" in page
    assert "taskPath" in workbench
    assert "/demo/${id}" in labels
    assert "class Share" not in models
    assert "submitted_to_advisor_at" in models
