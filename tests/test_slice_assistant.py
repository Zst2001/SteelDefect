from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party"), str(ROOT / "apps" / "api")]

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.models import (
    AssistantSession,
    AssistantTurn,
    AuditLog,
    CatalogModel,
    Dataset,
    DatasetVersion,
    MetricSet,
    Model,
    ModelPerfProfile,
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
from app.routers import assistant as assistant_router
from app.services.assistant import (
    add_analyze_turn,
    add_code_turn,
    add_infer_turn,
    add_kb_turn,
    add_message,
    add_perf_turn,
    iter_add_message,
    build_evidence_pack,
    create_session,
    dispatch_turn,
    get_analyzable_task,
    get_session,
    list_analyzable_tasks,
    list_sessions,
    preview_infer_run,
)
from app.services.assistant_kb import seed_assistant_kb
from app.services.demo import create_demo_task
from app.services.demo_identity import DemoIdentity
from app.services.seed import _ensure_demo_samples
from app.util_time import new_id, utcnow
from infer.spec import NEU_CLASS_MAP

WEB = ROOT / "apps" / "web" / "src"
API = ROOT / "apps" / "api" / "app"


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
def no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    # Legacy authorization fixtures have metadata-only asset URIs. C input I/O is
    # tested separately with actual temporary files, never these real asset paths.
    monkeypatch.setattr("app.services.tasks.freeze_inputs", lambda *a: None)
    monkeypatch.setattr("app.services.demo.freeze_inputs", lambda *a: None)
    monkeypatch.setattr("app.services.input_freeze.verify_inputs", lambda *a: {})
    monkeypatch.setattr("app.services.assistant.llm_ready", lambda settings=None: False)
    monkeypatch.setattr("app.services.demo.invalidate_after_write", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.demo._enqueue_task", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.demo.reserve_guest_quota", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.services.demo.release_guest_quota", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.tasks._enqueue_task", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.tasks.invalidate_after_write", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.perf.enqueue_perf", lambda *args, **kwargs: "job-test")
    monkeypatch.setattr("app.services.perf.invalidate_models_lists", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.perf.invalidate_after_write", lambda *args, **kwargs: None)


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


def _student_model(db: Session, user: User, preprocess: PreprocessSpecRow, *, status: str = "runnable") -> ModelVersion:
    model = Model(id=new_id(), owner_id=user.id, name="student-net", source="student", created_at=utcnow())
    db.add(model)
    db.flush()
    version = ModelVersion(
        id=new_id(),
        model_id=model.id,
        slug="student-net",
        num_classes=4,
        in_channels=3,
        input_h=200,
        input_w=200,
        preprocess_id=preprocess.id,
        requires_cuda=False,
        status=status,
        fail_stage="static" if status != "runnable" else None,
        fail_message="import 失败" if status != "runnable" else None,
        visibility="private",
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
    has_gt: bool | None = None,
) -> Task:
    samples = db.query(Sample).filter(Sample.version_id == version.id).order_by(Sample.sample_key.asc()).all()
    task = Task(
        id=new_id(),
        type=type,
        creator_id=user.id,
        dataset_version_id=version.id,
        preprocess_id=model.preprocess_id,
        status=status,
        has_gt=type != "demo" if has_gt is None else has_gt,
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


def _attach_metrics(db: Session, task: Task, miou: float = 0.71) -> None:
    db.add(
        MetricSet(
            id=new_id(),
            task_id=task.id,
            scope="batch_reference",
            n=2,
            payload_json={
                "models": [{"name": "UNet", "mIoU": miou, "mDice": 0.8, "Acc": 0.9, "classes": []}],
            },
        )
    )
    db.commit()
    db.refresh(task)


def test_ai01_no_key_returns_pack_without_writing(db: Session) -> None:
    preprocess = _preprocess(db)
    student = _user(db)
    version = _version(db, preprocess, owner_id=student.id)
    model = _builtin(db, preprocess)
    task = _task(db, student, version, model, has_gt=False)
    session = create_session(db, student)
    turn = add_analyze_turn(db, student, session.id, task_id=task.id)
    assert turn.llm_status == "skipped"
    assert turn.writing is None
    pack = turn.evidence_json or {}
    assert pack["metrics"]["available"] is False
    assert pack["task"]["id"] == task.id
    assert "无法谈精度" in json.dumps(pack, ensure_ascii=False)


def test_ai02_demo_rejected_without_metrics(db: Session) -> None:
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
    session = create_session(db, student)
    with pytest.raises(AppError) as exc:
        add_analyze_turn(db, student, session.id, task_id=demo.id)
    assert exc.value.code == "DEMO_NO_ANALYZE"
    assert exc.value.status_code == 400
    blob = (exc.value.message or "").lower()
    assert "miou" not in blob
    assert "mdice" not in blob
    listed = list_analyzable_tasks(db, student)
    assert demo.id not in {row["id"] for row in listed["items"]}


def test_ai03_no_gt_pack_omits_accuracy_numbers(db: Session) -> None:
    preprocess = _preprocess(db)
    student = _user(db)
    version = _version(db, preprocess, owner_id=student.id, with_mask=False)
    model = _builtin(db, preprocess)
    task = _task(db, student, version, model, has_gt=False)
    pack = build_evidence_pack(db, task)
    blob = json.dumps(pack.get("metrics") or {}, ensure_ascii=False).lower()
    assert pack["metrics"]["available"] is False
    assert "miou" not in blob
    assert "mdice" not in blob
    assert "acc" not in blob


def test_ai07_router_requires_login() -> None:
    source = (API / "routers" / "assistant.py").read_text(encoding="utf-8")
    assert "get_current_user" in source
    assert source.count("Depends(get_current_user)") >= 4


def test_ai08_cannot_analyze_unsubmitted_peer(db: Session) -> None:
    preprocess = _preprocess(db)
    alice = _user(db, username="alice")
    bob = _user(db, username="bob")
    advisor = _user(db, role="advisor", username="adv")
    version = _version(db, preprocess, owner_id=alice.id)
    model = _builtin(db, preprocess)
    task = _task(db, alice, version, model)
    with pytest.raises(AppError) as hidden:
        get_analyzable_task(db, task.id, bob)
    assert hidden.value.status_code == 404
    with pytest.raises(AppError) as advisor_hidden:
        get_analyzable_task(db, task.id, advisor)
    assert advisor_hidden.value.status_code == 404
    bob_session = create_session(db, bob)
    with pytest.raises(AppError):
        add_analyze_turn(db, bob, bob_session.id, task_id=task.id)


def test_ai09_advisor_can_analyze_submitted(db: Session) -> None:
    preprocess = _preprocess(db)
    student = _user(db)
    advisor = _user(db, role="advisor")
    version = _version(db, preprocess, owner_id=student.id)
    model = _builtin(db, preprocess)
    task = _task(db, student, version, model)
    task.submitted_to_advisor_at = utcnow()
    db.add(task)
    db.commit()
    session = create_session(db, advisor)
    turn = add_analyze_turn(db, advisor, session.id, task_id=task.id)
    assert turn.task_id == task.id
    ids = {row["id"] for row in list_analyzable_tasks(db, advisor)["items"]}
    assert task.id in ids


def test_ai10_writing_uses_pack_numbers(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    preprocess = _preprocess(db)
    student = _user(db)
    version = _version(db, preprocess, owner_id=student.id)
    model = _builtin(db, preprocess)
    task = _task(db, student, version, model, has_gt=True)
    _attach_metrics(db, task, miou=0.71)

    def fake_draft(pack, *, question=None, history=None, settings=None):
        miou = pack["metrics"]["models"][0]["mIoU"]
        return f"【测量事实】UNet mIoU {miou}"

    monkeypatch.setattr("app.services.assistant.llm_ready", lambda settings=None: True)
    monkeypatch.setattr("app.services.assistant.draft_analyze_copy", fake_draft)
    session = create_session(db, student)
    settings = Settings(llm_api_key="sk-test", llm_model="qwen3.8-max")
    turn = add_analyze_turn(db, student, session.id, task_id=task.id, settings=settings)
    assert turn.llm_status == "ok"
    assert turn.writing is not None
    assert "0.71" in turn.writing
    assert turn.evidence_json["metrics"]["available"] is True
    assert turn.evidence_json["metrics"]["models"][0]["mIoU"] == 0.71


def test_ai11_specialty_shell_without_cross_tab() -> None:
    view = (WEB / "views" / "AssistantView.vue").read_text(encoding="utf-8")
    assert "学术" in view
    assert "分割" in view
    assert "模型" in view
    assert "模型检测" not in view
    assert "demo/tasks" not in view
    assert "去模型测评" in view
    assert "/models/perf" in view
    assert "分割代跑" in view
    assert "源码建议" in view
    assert "新对话" in view
    assert "对话列表" in view
    assert "专科选择器" in view
    assert "<el-tabs" not in view
    switch_fn = view.split("function switchSpecialty", 1)[1].split("async function sendPayload", 1)[0]
    assert "createSession" not in switch_fn
    new_fn = view.split("function newConversation", 1)[1].split("function switchSpecialty", 1)[0]
    assert "createSession" not in new_fn
    assert "openAuthFile" in view
    labels = (WEB / "api" / "labels.ts").read_text(encoding="utf-8")
    assert "openAuthFile" in labels
    records = (WEB / "views" / "records" / "RecordsView.vue").read_text(encoding="utf-8")
    assert "用科研助手分析" in records
    service = (API / "services" / "assistant.py").read_text(encoding="utf-8")
    assert "infer.run" in service
    assert "kb.answer" in service
    assert "perf.measure" in service
    assert "task.analyze" in service
    assert "create_demo_task" not in service
    assert "create_eval_task" not in service
    router = (API / "routers" / "assistant.py").read_text(encoding="utf-8")
    assert "/messages" in router
    assert "/sessions" in router


def test_ai12_session_turn_and_audit_persist(db: Session) -> None:
    preprocess = _preprocess(db)
    student = _user(db)
    version = _version(db, preprocess, owner_id=student.id)
    model = _builtin(db, preprocess)
    task = _task(db, student, version, model, has_gt=False)
    session = create_session(db, student)
    add_analyze_turn(db, student, session.id, task_id=task.id)
    stored = db.get(AssistantSession, session.id)
    assert stored is not None
    assert stored.user_id == student.id
    assert stored.specialty == "segment"
    turns = db.query(AssistantTurn).filter(AssistantTurn.session_id == session.id).all()
    assert len(turns) == 1
    assert turns[0].tool_name == "task.analyze"
    assert turns[0].llm_status == "skipped"
    logs = db.query(AuditLog).filter(AuditLog.action == "assistant.task.analyze").all()
    assert len(logs) == 1
    assert logs[0].actor_id == student.id
    assert logs[0].target_id == task.id
    peer = _user(db, username="peer")
    with pytest.raises(AppError) as hidden:
        get_session(db, session.id, peer)
    assert hidden.value.status_code == 404


def test_running_task_not_ready(db: Session) -> None:
    preprocess = _preprocess(db)
    student = _user(db)
    version = _version(db, preprocess, owner_id=student.id)
    model = _builtin(db, preprocess)
    task = _task(db, student, version, model, status="running")
    with pytest.raises(AppError) as exc:
        get_analyzable_task(db, task.id, student)
    assert exc.value.code == "NOT_READY"


def test_closed_specialty_rejected(db: Session) -> None:
    student = _user(db)
    with pytest.raises(AppError) as exc:
        create_session(db, student, specialty="detect")
    assert exc.value.code == "SPECIALTY_CLOSED"


def test_router_is_mounted() -> None:
    assert assistant_router.router.prefix == "/assistant"
    source = (API / "main.py").read_text(encoding="utf-8")
    assert "assistant.router" in source
    view = (WEB / "views" / "compare" / "CompareTaskView.vue").read_text(encoding="utf-8")
    assert "/assistant" in view
    assert "用科研助手分析" in view
    records = (WEB / "views" / "records" / "RecordsView.vue").read_text(encoding="utf-8")
    assert "用科研助手分析" in records


def test_ai04_infer_rejects_demo_and_eval_batches(db: Session) -> None:
    preprocess = _preprocess(db)
    student = _user(db)
    builtin = _builtin(db, preprocess)
    demo_batch = _version(db, preprocess, kind="demo_samples", owner_id=student.id, is_fixed_test=False)
    with pytest.raises(AppError) as demo_exc:
        preview_infer_run(
            db,
            student,
            batch_id=demo_batch.id,
            baseline_version_ids=[builtin.id],
            student_version_id=None,
        )
    assert demo_exc.value.code in {"DEMO_NO_INFER", "INFER_BATCH_FORBIDDEN"}
    eval_batch = _version(db, preprocess, kind="preset", owner_id=None, is_fixed_test=True, visibility="preset")
    with pytest.raises(AppError) as eval_exc:
        preview_infer_run(
            db,
            student,
            batch_id=eval_batch.id,
            baseline_version_ids=[builtin.id],
            student_version_id=None,
        )
    assert eval_exc.value.code == "INFER_BATCH_FORBIDDEN"


def test_ai05_catalog_not_runnable(db: Session) -> None:
    preprocess = _preprocess(db)
    student = _user(db)
    batch = _version(db, preprocess, owner_id=student.id)
    paper = CatalogModel(
        id=new_id(),
        name="PaperNet",
        task_type="segmentation",
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(paper)
    db.commit()
    with pytest.raises(AppError) as exc:
        preview_infer_run(
            db,
            student,
            batch_id=batch.id,
            baseline_version_ids=[paper.id],
            student_version_id=None,
        )
    assert exc.value.code == "CATALOG_NOT_RUNNABLE"


def test_ai04_infer_confirm_then_compare(db: Session) -> None:
    preprocess = _preprocess(db)
    student = _user(db)
    builtin = _builtin(db, preprocess)
    batch = _version(db, preprocess, owner_id=student.id, with_mask=False)
    session = create_session(db, student, specialty="segment")
    preview = add_infer_turn(
        db,
        student,
        session.id,
        batch_id=batch.id,
        baseline_version_ids=[builtin.id],
        confirm=False,
    )
    assert isinstance(preview, dict)
    assert preview["needs_confirm"] is True
    assert db.query(Task).count() == 0
    turn = add_infer_turn(
        db,
        student,
        session.id,
        batch_id=batch.id,
        baseline_version_ids=[builtin.id],
        confirm=True,
    )
    assert turn.tool_name == "infer.run"
    task = db.get(Task, turn.task_id)
    assert task is not None
    assert task.type == "compare"
    assert task.has_gt is False


def test_academic_cannot_run_infer(db: Session) -> None:
    preprocess = _preprocess(db)
    student = _user(db)
    builtin = _builtin(db, preprocess)
    batch = _version(db, preprocess, owner_id=student.id)
    session = create_session(db, student, specialty="academic")
    with pytest.raises(AppError) as exc:
        add_infer_turn(
            db,
            student,
            session.id,
            batch_id=batch.id,
            baseline_version_ids=[builtin.id],
            confirm=True,
        )
    assert exc.value.code == "TOOL_FORBIDDEN"


def test_ai06_detect_unavailable(db: Session) -> None:
    student = _user(db)
    session = create_session(db, student, specialty="segment")
    with pytest.raises(AppError) as exc:
        dispatch_turn(db, student, session.id, tool="infer.detect")
    assert exc.value.code == "UNAVAILABLE"


def _kb_audit_texts(db: Session, session_id: str) -> list[str]:
    rows = db.query(AuditLog).filter(AuditLog.target_id == session_id).all()
    return [row.reason or "" for row in rows]


def _kb_audit_text(db: Session, session_id: str) -> str:
    texts = _kb_audit_texts(db, session_id)
    assert texts
    return texts[-1]


def test_kb01_miss_refuses(db: Session) -> None:
    seed_assistant_kb(db)
    db.commit()
    student = _user(db)
    session = create_session(db, student, specialty="academic")
    turn = add_kb_turn(db, student, session.id, question="小麦赤霉病遥感指数怎么计算？")
    pack = turn.evidence_json or {}
    assert pack.get("hit") is False
    assert pack.get("refused") is True
    assert turn.writing is not None
    assert "拒" in turn.writing or "未覆盖" in turn.writing
    reason = _kb_audit_text(db, session.id)
    assert "hit=0" in reason
    assert "via=" in reason
    assert "ms=" in reason
    assert "embedding" not in reason.lower()


def test_kb01_hit_returns_source(db: Session) -> None:
    seed_assistant_kb(db)
    db.commit()
    student = _user(db)
    session = create_session(db, student, specialty="academic")
    turn = add_kb_turn(db, student, session.id, question="NEU-20 是不是论文完整 test split？")
    pack = turn.evidence_json or {}
    assert pack.get("hit") is True
    assert pack.get("hits")
    assert pack["hits"][0]["source"]
    blob = json.dumps(pack, ensure_ascii=False)
    assert "NEU-20" in blob
    reason = _kb_audit_text(db, session.id)
    file_id = str(pack["hits"][0].get("file_id") or pack["hits"][0].get("slug") or "")
    assert file_id
    assert file_id in reason
    assert "via=" in reason
    assert "embedding" not in reason.lower()


def test_kb02_seed_has_no_student_weights() -> None:
    from app.services.assistant_kb import SEED_DOCS

    blob = json.dumps(SEED_DOCS, ensure_ascii=False)
    assert "def build_model" not in blob
    assert "load_state_dict" not in blob


def test_m01_code_advise_does_not_write(db: Session, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    preprocess = _preprocess(db)
    student = _user(db)
    version = _student_model(db, student, preprocess, status="cannot_start")
    source = tmp_path / "model.py"
    source.write_text("def build_model():\n    raise RuntimeError('x')\n", encoding="utf-8")
    monkeypatch.setattr(
        "app.services.assistant._read_student_source",
        lambda *_args, **_kwargs: source.read_text(encoding="utf-8"),
    )
    session = create_session(db, student, specialty="model")
    turn = add_code_turn(db, student, session.id, version_id=version.id)
    assert turn.tool_name == "code.advise"
    assert (turn.evidence_json or {}).get("wrote_disk") is False
    assert source.read_text(encoding="utf-8").startswith("def build_model")
    assert db.get(ModelVersion, version.id).status == "cannot_start"


def test_perf_measure_readonly_then_enqueue(db: Session) -> None:
    preprocess = _preprocess(db)
    student = _user(db)
    version = _builtin(db, preprocess)
    session = create_session(db, student, specialty="model")
    preview = add_perf_turn(db, student, session.id, version_id=version.id, enqueue=False)
    assert isinstance(preview, dict)
    assert preview["needs_confirm"] is True
    assert "dummy" in json.dumps(preview, ensure_ascii=False)
    turn = add_perf_turn(db, student, session.id, version_id=version.id, enqueue=True)
    assert turn.tool_name == "perf.measure"
    assert "不是 CUDA 论文测速" in json.dumps(turn.evidence_json, ensure_ascii=False)
    existing = db.query(ModelPerfProfile).filter(ModelPerfProfile.version_id == version.id).one_or_none()
    if existing is None:
        db.add(
            ModelPerfProfile(
                id=new_id(),
                version_id=version.id,
                status="success",
                param_count=1000,
                latency_ms_per_image=12.5,
                warmup_runs=3,
                timed_runs=10,
                batch=1,
                input_h=200,
                input_w=200,
                input_kind="dummy",
                device="cpu",
                updated_at=utcnow(),
            )
        )
    else:
        existing.status = "success"
        existing.param_count = 1000
        existing.latency_ms_per_image = 12.5
    db.commit()
    read = add_perf_turn(db, student, session.id, version_id=version.id, enqueue=False)
    assert not isinstance(read, dict)
    assert (read.evidence_json or {}).get("queued") is False
    assert (read.evidence_json or {}).get("perf", {}).get("param_count") == 1000


def test_perf_cannot_start_refused(db: Session) -> None:
    preprocess = _preprocess(db)
    student = _user(db)
    version = _student_model(db, student, preprocess, status="cannot_start")
    session = create_session(db, student, specialty="model")
    with pytest.raises(AppError) as exc:
        add_perf_turn(db, student, session.id, version_id=version.id, enqueue=True)
    assert exc.value.code == "NOT_RUNNABLE"


def test_ch01_followup_sends_history(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    preprocess = _preprocess(db)
    student = _user(db)
    version = _version(db, preprocess, owner_id=student.id)
    model = _builtin(db, preprocess)
    task = _task(db, student, version, model, has_gt=True)
    _attach_metrics(db, task, miou=0.71)
    captured: list[list[dict]] = []

    def fake_completion(messages, settings=None):
        captured.append(messages)
        return "【测量事实】UNet mIoU 0.71。弱类见证据包。"

    def fake_iter(messages, settings=None):
        captured.append(messages)
        yield "【测量事实】UNet mIoU 0.71。弱类见证据包。"

    monkeypatch.setattr("app.services.assistant.llm_ready", lambda settings=None: True)
    monkeypatch.setattr("app.services.llm_client.chat_completion", fake_completion)
    monkeypatch.setattr("app.services.assistant.iter_chat_completion", fake_iter)
    session = create_session(db, student, specialty="segment")
    settings = Settings(llm_api_key="sk-test", llm_model="qwen3.8-max")
    add_analyze_turn(db, student, session.id, task_id=task.id, question="先看整体", settings=settings)
    stored = db.get(AssistantSession, session.id)
    assert stored is not None
    assert (stored.working_json or {}).get("task_id") == task.id
    payload = add_message(db, student, session.id, content="弱类是哪些")
    assert len(captured) >= 2
    follow = captured[-1]
    blob = json.dumps(follow, ensure_ascii=False)
    assert any(item.get("role") == "assistant" for item in follow)
    assert "先看整体" in blob or "0.71" in blob
    assert "弱类是哪些" in blob
    roles = [item["role"] for item in payload["turns"]]
    assert "user" in roles
    assert payload["turns"][-1]["role"] == "assistant"
    assert payload["working"]["task_id"] == task.id


def test_ch02_academic_followup_reuses_hits(db: Session) -> None:
    seed_assistant_kb(db)
    db.commit()
    student = _user(db)
    session = create_session(db, student, specialty="academic")
    first = add_message(db, student, session.id, content="NEU-20 是不是论文完整 test split？")
    assert first["turns"][-1]["evidence_pack"]["hit"] is True
    second = add_message(db, student, session.id, content="刚才那条再展开")
    pack = second["turns"][-1]["evidence_pack"]
    assert pack.get("hit") is True
    assert pack.get("refused") is False
    titles = " ".join(hit.get("title") or "" for hit in pack.get("hits") or [])
    excerpts = " ".join(hit.get("excerpt") or "" for hit in pack.get("hits") or [])
    assert "NEU" in titles + excerpts or pack.get("reused") is True or pack.get("rewritten") is True
    reasons = _kb_audit_texts(db, session.id)
    assert any("via=session" in item or "rewritten=1" in item for item in reasons)
    assert all("embedding" not in item.lower() for item in reasons)


def _fake_hit(file_id: str, excerpt: str) -> dict:
    return {
        "title": file_id,
        "excerpt": excerpt,
        "file_id": file_id,
        "slug": file_id,
        "source": "导师审定",
    }


def test_followup_rewrites_then_searches(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    student = _user(db)
    session = create_session(db, student, specialty="academic")
    seen: list[str] = []

    def fake_retrieve(_db, query: str, settings=None):
        seen.append(query)
        return {
            "query": query,
            "hit": True,
            "via": "milvus",
            "hits": [_fake_hit("writing-protocol", "NEU-20 不是论文完整 test split")],
            "elapsed_ms": 4,
        }

    monkeypatch.setattr("app.services.assistant.retrieve_kb", fake_retrieve)
    add_kb_turn(db, student, session.id, question="NEU-20 是不是论文完整 test split？", want_answer=False)
    follow = add_kb_turn(db, student, session.id, question="刚才那条再展开", want_answer=False)
    pack = follow.evidence_json or {}
    assert seen[1] == "NEU-20 是不是论文完整 test split？\n刚才那条再展开"
    assert pack.get("rewritten") is True
    assert pack.get("via") == "milvus"
    assert "rewritten=1" in _kb_audit_text(db, session.id)
    assert "embedding" not in _kb_audit_text(db, session.id).lower()


def test_pronoun_followup_rewrites_named_question_does_not(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    student = _user(db)
    session = create_session(db, student, specialty="academic")
    seen: list[str] = []

    def fake_retrieve(_db, query: str, settings=None):
        seen.append(query)
        return {
            "query": query,
            "hit": True,
            "via": "milvus",
            "hits": [_fake_hit("writing-protocol", "NEU-20 不是论文完整 test split")],
            "elapsed_ms": 1,
        }

    monkeypatch.setattr("app.services.assistant.retrieve_kb", fake_retrieve)
    add_kb_turn(db, student, session.id, question="NEU-20 是不是论文完整 test split？", want_answer=False)
    pronoun = add_kb_turn(db, student, session.id, question="它的 DOI 呢", want_answer=False)
    assert seen[1] == "NEU-20 是不是论文完整 test split？\n它的 DOI 呢"
    assert (pronoun.evidence_json or {}).get("rewritten") is True
    named = add_kb_turn(db, student, session.id, question="ResNet 的 DOI", want_answer=False)
    assert seen[2] == "ResNet 的 DOI"
    assert (named.evidence_json or {}).get("rewritten") is False


def test_followup_reuses_when_rewrite_misses(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    student = _user(db)
    session = create_session(db, student, specialty="academic")

    def fake_retrieve(_db, query: str, settings=None):
        if "刚才" in query:
            return {"query": query, "hit": False, "via": "milvus", "hits": [], "elapsed_ms": 2}
        return {
            "query": query,
            "hit": True,
            "via": "milvus",
            "hits": [_fake_hit("writing-protocol", "NEU-20 不是论文完整 test split")],
            "elapsed_ms": 3,
        }

    monkeypatch.setattr("app.services.assistant.retrieve_kb", fake_retrieve)
    add_kb_turn(db, student, session.id, question="NEU-20 是不是论文完整 test split？", want_answer=False)
    follow = add_kb_turn(db, student, session.id, question="刚才那条再展开", want_answer=False)
    pack = follow.evidence_json or {}
    assert pack.get("reused") is True
    assert pack.get("via") == "session"
    assert pack.get("rewritten") is False
    assert "via=session" in _kb_audit_text(db, session.id)


def test_nth_hit_reuses_without_embed(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    student = _user(db)
    session = create_session(db, student, specialty="academic")
    calls = {"n": 0}

    def fake_retrieve(_db, query: str, settings=None):
        calls["n"] += 1
        return {
            "query": query,
            "hit": True,
            "via": "milvus",
            "hits": [
                _fake_hit("one", "第一段"),
                _fake_hit("two", "第二段"),
                _fake_hit("three", "第三段正文"),
            ],
            "elapsed_ms": 5,
        }

    monkeypatch.setattr("app.services.assistant.retrieve_kb", fake_retrieve)
    add_kb_turn(db, student, session.id, question="钢铁缺陷检测入门读什么？", want_answer=False)
    picked = add_kb_turn(db, student, session.id, question="展开第三条", want_answer=False)
    pack = picked.evidence_json or {}
    assert calls["n"] == 1
    assert pack.get("via") == "session"
    assert pack["hits"][0]["excerpt"] == "第三段正文"
    assert pack["hits"][0]["file_id"] == "three"
    missing = add_kb_turn(db, student, session.id, question="展开第五条", want_answer=False)
    assert (missing.evidence_json or {}).get("hit") is False
    assert calls["n"] == 1


def test_ch03_list_sessions(db: Session) -> None:
    seed_assistant_kb(db)
    db.commit()
    student = _user(db)
    peer = _user(db, username="peer-chat")
    a = create_session(db, student, specialty="academic")
    add_message(db, student, a.id, content="NEU-20 是不是论文完整 test split？")
    s = create_session(db, student, specialty="segment")
    add_message(db, student, s.id, content="还没有任务")
    empty = create_session(db, student, specialty="model")
    other = create_session(db, peer, specialty="model")
    add_message(db, peer, other.id, content="查看测参档案")
    listed = list_sessions(db, student)
    ids = {item["id"] for item in listed["items"]}
    assert a.id in ids
    assert s.id in ids
    assert empty.id not in ids
    assert other.id not in ids
    academic_only = list_sessions(db, student, specialty="academic")
    assert {item["id"] for item in academic_only["items"]} == {a.id}


def test_ch04_academic_message_cannot_infer(db: Session) -> None:
    preprocess = _preprocess(db)
    student = _user(db)
    builtin = _builtin(db, preprocess)
    batch = _version(db, preprocess, owner_id=student.id)
    session = create_session(db, student, specialty="academic")
    with pytest.raises(AppError) as exc:
        add_message(
            db,
            student,
            session.id,
            content="帮我跑分割",
            tool="infer.run",
            batch_id=batch.id,
            baseline_version_ids=[builtin.id],
            confirm=True,
        )
    assert exc.value.code == "TOOL_FORBIDDEN"


def test_ch05_chat_canvas_not_form_tabs() -> None:
    view = (WEB / "views" / "AssistantView.vue").read_text(encoding="utf-8")
    spec = (ROOT / "docs" / "科研助手产品说明.md").read_text(encoding="utf-8")
    reqs = (ROOT / "docs" / "课题组网站需求分析书.md").read_text(encoding="utf-8")
    assert "版本：0.4" in spec
    assert "对话画布" in spec
    assert "专科选择器" in spec
    assert "v3.1.1" in reqs
    assert "el-tab-pane" not in view
    assert "session-list" in view
    assert "对话列表" in view
    assert "drawer" in view
    assert "/assistant/sessions/${sessionId}/messages" in view or "/messages" in view
    assert "/messages/stream" in view
    router = (API / "routers" / "assistant.py").read_text(encoding="utf-8")
    assert "/messages/stream" in router


def test_iter_chat_completion_parses_sse(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.llm_client import iter_chat_completion

    class DummyResponse:
        status_code = 200

        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"你"}}]}'
            yield 'data: {"choices":[{"delta":{"content":"好"}}]}'
            yield "data: [DONE]"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class DummyClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def stream(self, *_args, **_kwargs):
            return DummyResponse()

    monkeypatch.setattr("app.services.llm_client.httpx.Client", DummyClient)
    settings = Settings(
        llm_api_key="sk-test",
        llm_base_url="https://ark.cn-beijing.volces.com/api/v3",
        llm_model="deepseek-v4-1-flash-260910",
    )
    text = "".join(iter_chat_completion([{"role": "user", "content": "hi"}], settings=settings))
    assert text == "你好"


def test_iter_add_message_emits_deltas(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_assistant_kb(db)
    db.commit()
    student = _user(db)
    session = create_session(db, student, specialty="academic")
    monkeypatch.setattr("app.services.assistant.llm_ready", lambda settings=None: True)

    def fake_iter(messages, settings=None):
        yield "语"
        yield "料"

    monkeypatch.setattr("app.services.assistant.iter_chat_completion", fake_iter)
    events = list(iter_add_message(db, student, session.id, content="NEU-20 是不是论文完整 test split？"))
    kinds = [item.get("type") for item in events]
    assert kinds.count("delta") >= 2
    assert kinds[-1] == "done"
    assert "".join(item.get("text") or "" for item in events if item.get("type") == "delta") == "语料"
    assert events[-1]["session"]["turns"][-1]["writing"] == "语料"


