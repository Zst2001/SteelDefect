"""Offline authorization regressions. Run via tests/run_phase_a_tests.py only."""
from __future__ import annotations

import sys
import zipfile

# Refuse collection before any application import in an unisolated pytest invocation.
if "app.config" not in sys.modules or sys.modules["app.config"].Settings.__name__ != "OfflineSettings":
    raise RuntimeError("Run this suite with: python -B tests/run_phase_a_tests.py")

from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlsplit

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.authz import get_current_user
from app.config import Settings, get_settings
from app.db.models import (
    Artifact, Dataset, DatasetVersion, Model, ModelVersion, PreprocessSpecRow,
    Sample, Task, TaskModel, TaskSample, User,
)
from app.db.session import Base
from app.deps import get_db
from app.errors import AppError, app_error_handler
from app.routers import assistant as assistant_router, demo as demo_router, models as models_router
from app.routers import records as records_router, tasks as tasks_router
from app.services import assistant, tasks, records, dashboard, demo
from app.services.adapt import apply_adapt
from app.services.demo_identity import DemoIdentity, get_demo_identity
from app.services.models import can_view_version
from app.services.records import rerun_record, submit_to_advisor, withdraw_from_advisor
from app.util_time import new_id, utcnow
from apps.worker import jobs


@pytest.fixture
def lab(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    db = factory()
    settings = Settings(storage_root=str(tmp_path), seed_on_start=False)
    queue = Mock()
    for module in (tasks, assistant, jobs, tasks_router, models_router, demo_router, records, dashboard, demo):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "_enqueue_task", queue)
    monkeypatch.setattr(tasks, "invalidate_after_write", lambda *a: None)
    monkeypatch.setattr(jobs, "invalidate_after_write", lambda *a: None)
    monkeypatch.setattr(jobs, "SessionLocal", factory)
    monkeypatch.setattr(assistant, "llm_ready", lambda *a: False)

    def user(role="student"):
        row = User(id=new_id(), username=new_id(), password_hash="unused", role=role, status="active")
        db.add(row)
        db.commit()
        return row

    owner, peer, advisor = user(), user(), user("advisor")
    spec = PreprocessSpecRow(id=new_id(), name="neu_200", height=200, width=200,
                             apply_clahe=False, sp_threshold=.02, dataset="neu")
    db.add(spec)
    db.commit()

    def version(kind="upload_batch", with_gt=False):
        dataset = Dataset(id=new_id(), owner_id=owner.id, name=new_id(), visibility="private")
        db.add(dataset)
        db.flush()
        row = DatasetVersion(id=new_id(), dataset_id=dataset.id, kind=kind, class_map_json={},
                             preprocess_id=spec.id, is_fixed_test=kind == "preset",
                             forbid_student_gt_download=kind == "preset")
        db.add(row)
        db.flush()
        # Eval fixture follows NEU-20 cardinality without accessing actual assets/GT.
        for i in range(20 if kind == "preset" else 1):
            db.add(Sample(id=new_id(), version_id=row.id, sample_key=f"s{i}",
                          origin_uri="data:fake.png", mask_uri="data:fake-gt.png" if with_gt else None,
                          width=200, height=200, sha256="test"))
        db.commit()
        return row

    batch, evaluation = version(), version("preset", True)
    # Synthetic frozen inputs: never resolve real repository assets or GT.
    import hashlib
    (tmp_path / "fake.png").write_bytes(b"synthetic-origin")
    (tmp_path / "fake-gt.png").write_bytes(b"synthetic-mask")
    for sample in db.query(Sample).all():
        sample.sha256 = hashlib.sha256(b"synthetic-origin").hexdigest()
    db.commit()

    def model(source="builtin", creator=None, visibility="public"):
        parent = Model(id=new_id(), owner_id=creator.id if creator else None, name=new_id(), source=source)
        db.add(parent)
        db.flush()
        row = ModelVersion(id=new_id(), model_id=parent.id, slug="unet", entry_symbol="build_model",
                           num_classes=4, in_channels=3, input_h=200, input_w=200,
                           preprocess_id=spec.id, requires_cuda=False, status="runnable", visibility=visibility)
        db.add(row)
        db.commit()
        return row

    builtin = model()
    mine = model("student", owner, "private")
    private = model("student", peer, "private")
    shared = model("student", peer, "shared")
    state = SimpleNamespace(db=db, factory=factory, settings=settings, queue=queue,
                            owner=owner, peer=peer, advisor=advisor, spec=spec, batch=batch,
                            evaluation=evaluation, builtin=builtin, mine=mine, private=private,
                            shared=shared, model=model, tmp=tmp_path)
    yield state
    db.close()
    engine.dispose()


def client(lab, user, *, sid="guest-owner"):
    app = FastAPI()  # Deliberately no production lifespan.
    app.add_exception_handler(AppError, app_error_handler)
    for router in (tasks_router.router, records_router.router, demo_router.router,
                   models_router.router, assistant_router.router):
        app.include_router(router, prefix="/api")

    def database():
        yield lab.db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_demo_identity] = lambda: DemoIdentity(
        sid=sid, user=user, ip="test", ip_hash="test")
    return TestClient(app)


def create(lab, kind="compare", *, user=None, baselines=None, student=None):
    body = {"baseline_version_ids": baselines if baselines is not None else [lab.builtin.id],
            "student_version_id": student}
    body["batch_id" if kind == "compare" else "dataset_version_id"] = (
        lab.batch.id if kind == "compare" else lab.evaluation.id)
    with client(lab, user or lab.owner) as http:
        return http.post(f"/api/tasks/{kind}", json=body)


@pytest.mark.parametrize("kind", ["compare", "eval"])
@pytest.mark.parametrize("actor,student", [("owner", None), ("owner", "mine"),
                                           ("owner", "shared"), ("advisor", "shared")])
def test_valid_creation_roles(lab, kind, actor, student):
    response = create(lab, kind, user=getattr(lab, actor), student=getattr(lab, student).id if student else None)
    assert response.status_code == 200, response.text
    assert lab.queue.call_count == 1
    links = lab.db.query(TaskModel).all()
    assert [(row.model_version_id, row.role) for row in sorted(links, key=lambda x: x.sort_order)] == (
        [(lab.builtin.id, "baseline")] + ([(getattr(lab, student).id, "student_under_test")] if student else []))
    assert lab.db.query(Task).one().creator_id == getattr(lab, actor).id


@pytest.mark.parametrize("kind,count", [("compare", 3), ("eval", 7)])
def test_maximum_baselines_still_allowed(lab, kind, count):
    ids = [lab.builtin.id] + [lab.model().id for _ in range(count - 1)]
    assert create(lab, kind, baselines=ids).status_code == 200
    assert lab.db.query(TaskModel).count() == count


@pytest.mark.parametrize("field,value", [("in_channels", 1), ("input_h", 100), ("input_w", 100)])
@pytest.mark.parametrize("kind", ["compare", "eval"])
def test_channel_and_size_protocol_rejected(lab, kind, field, value):
    setattr(lab.mine, field, value)
    lab.db.commit()
    response = create(lab, kind, student=lab.mine.id)
    assert response.status_code == 400 and response.json()["code"] == "PROTOCOL_MISMATCH"
    assert lab.db.query(Task).count() == lab.db.query(TaskModel).count() == 0
    lab.queue.assert_not_called()


def test_advisor_can_run_and_view_own_private_model_task(lab):
    own = lab.model("student", lab.advisor, "private")
    response = create(lab, user=lab.advisor, student=own.id)
    assert response.status_code == 200
    with client(lab, lab.advisor) as http:
        assert http.get(f"/api/tasks/{response.json()['id']}").status_code == 200


@pytest.mark.parametrize("kind", ["compare", "eval"])
@pytest.mark.parametrize("case,code", [
    ("own_as_baseline", "NOT_BASELINE"), ("peer_as_baseline", "NOT_BASELINE"),
    ("shared_as_baseline", "NOT_BASELINE"), ("peer_student", "FORBIDDEN"),
    ("advisor_private", "FORBIDDEN"), ("builtin_as_student", "NOT_STUDENT_MODEL"),
    ("not_runnable", "MODEL_NOT_RUNNABLE"), ("student_not_runnable", "STUDENT_NOT_RUNNABLE"),
    ("cuda", "CUDA_REQUIRED"), ("student_cuda", "CUDA_REQUIRED"),
    ("protocol", "PROTOCOL_MISMATCH"), ("preprocess", "PREPROCESS_MISMATCH"),
    ("duplicate", "DUP_BASELINE"), ("unknown", "MODEL_NOT_FOUND"),
    ("empty", None), ("too_many", None), ("data_owner", "FORBIDDEN"),
])
def test_rejected_requests_never_persist_or_enqueue(lab, kind, case, code):
    ids, sid, actor = [lab.builtin.id], None, lab.owner
    if case in {"own_as_baseline", "peer_as_baseline", "shared_as_baseline"}:
        ids = [getattr(lab, {"own_as_baseline": "mine", "peer_as_baseline": "private", "shared_as_baseline": "shared"}[case]).id]
    elif case in {"peer_student", "advisor_private"}:
        sid = lab.private.id
        if case == "advisor_private":
            actor = lab.advisor
    elif case == "builtin_as_student":
        sid = lab.builtin.id
    elif case == "not_runnable":
        lab.builtin.status = "cannot_start"
    elif case == "student_not_runnable":
        sid, lab.mine.status = lab.mine.id, "checking"
    elif case == "cuda":
        lab.builtin.requires_cuda = True
    elif case == "student_cuda":
        sid, lab.mine.requires_cuda = lab.mine.id, True
    elif case == "protocol":
        sid, lab.mine.num_classes = lab.mine.id, 9
    elif case == "preprocess":
        row = PreprocessSpecRow(id=new_id(), name="other", height=200, width=200,
                                apply_clahe=False, sp_threshold=.02, dataset="neu")
        lab.db.add(row)
        lab.db.flush()
        lab.builtin.preprocess_id = row.id
    elif case == "duplicate":
        ids *= 2
    elif case == "unknown":
        ids = [new_id()]
    elif case == "empty":
        ids = []
    elif case == "too_many":
        ids = [new_id() for _ in range(8 if kind == "eval" else 4)]
    elif case == "data_owner":
        actor = lab.peer
    lab.db.commit()
    commits = []
    from sqlalchemy import event
    event.listen(lab.db, "after_commit", lambda session: commits.append(True))
    response = create(lab, kind, user=actor, baselines=ids, student=sid)
    assert response.status_code in {400, 403, 404, 422}, response.text
    if code:
        assert response.json()["code"] == code
    assert not commits
    assert lab.db.query(Task).count() == lab.db.query(TaskModel).count() == lab.db.query(TaskSample).count() == 0
    lab.queue.assert_not_called()


@pytest.mark.parametrize("confirm", [False, True])
@pytest.mark.parametrize("entry", ["turns", "messages", "messages/stream"])
def test_assistant_all_entrypoints_reject_private_peer(lab, confirm, entry):
    session = assistant.create_session(lab.db, lab.advisor, specialty="segment")
    with client(lab, lab.advisor) as http:
        response = http.post(f"/api/assistant/sessions/{session.id}/{entry}", json={
            "tool": "infer.run", "batch_id": lab.batch.id,
            "baseline_version_ids": [lab.builtin.id], "student_version_id": lab.private.id,
            "confirm": confirm,
        })
    if entry.endswith("stream"):
        assert '"type": "error"' in response.text and '"code": "FORBIDDEN"' in response.text
    else:
        assert response.status_code == 403
    assert lab.db.query(Task).count() == 0
    lab.queue.assert_not_called()


def test_assistant_preview_rechecks_on_confirm(lab):
    session = assistant.create_session(lab.db, lab.owner, specialty="segment")
    args = dict(batch_id=lab.batch.id, baseline_version_ids=[lab.builtin.id], student_version_id=lab.shared.id)
    assert assistant.add_infer_turn(lab.db, lab.owner, session.id, **args)["needs_confirm"]
    lab.shared.visibility = "private"
    lab.db.commit()
    with pytest.raises(AppError, match="无权"):
        assistant.add_infer_turn(lab.db, lab.owner, session.id, confirm=True, **args)
    assert lab.db.query(Task).count() == 0
    lab.queue.assert_not_called()


@pytest.mark.parametrize("case,code", [("student_baseline", "NOT_BASELINE"),
                                      ("not_runnable", "MODEL_NOT_RUNNABLE"),
                                      ("cuda", "CUDA_REQUIRED"), ("duplicate", "DUP_BASELINE")])
def test_assistant_preview_uses_creation_checks(lab, case, code):
    ids = [lab.builtin.id]
    if case == "student_baseline":
        ids = [lab.mine.id]
    elif case == "not_runnable":
        lab.builtin.status = "checking"
    elif case == "cuda":
        lab.builtin.requires_cuda = True
    else:
        ids *= 2
    lab.db.commit()
    with pytest.raises(AppError) as error:
        assistant.preview_infer_run(lab.db, lab.owner, batch_id=lab.batch.id,
                                    baseline_version_ids=ids, student_version_id=None)
    assert error.value.code == code
    assert lab.db.query(Task).count() == 0
    lab.queue.assert_not_called()


@pytest.mark.parametrize("kind", ["compare", "eval"])
def test_rerun_rechecks_revoked_sharing(lab, kind):
    response = create(lab, kind, student=lab.shared.id)
    original = lab.db.get(Task, response.json()["id"])
    lab.shared.visibility = "private"
    lab.db.commit()
    lab.queue.reset_mock()
    with pytest.raises(AppError):
        rerun_record(lab.db, lab.owner, original.id)
    assert lab.db.query(Task).count() == 1
    lab.queue.assert_not_called()


def worker_spies(monkeypatch):
    spies = [Mock(side_effect=AssertionError("executor must not run")) for _ in range(3)]
    for name, spy in zip(("get_builtin_module", "infer_student_masks", "predict_mask"), spies):
        monkeypatch.setattr(jobs, name, spy)
    return spies


@pytest.mark.parametrize("kind", ["compare", "eval"])
@pytest.mark.parametrize("case", ["revoked", "role", "student_role", "unknown_source", "missing_model",
                                 "missing_version", "unknown_role", "disabled_creator", "not_runnable", "cuda"])
def test_worker_preflight_fails_whole_task_before_any_executor(lab, monkeypatch, kind, case):
    task_id = create(lab, kind, student=lab.shared.id).json()["id"]
    version_id = lab.shared.id
    # Separate transaction represents an admin changing permissions after enqueue.
    with lab.factory() as writer:
        mv = writer.get(ModelVersion, version_id)
        link = writer.query(TaskModel).filter_by(task_id=task_id, model_version_id=version_id).one()
        if case == "revoked":
            mv.visibility = "private"
        elif case == "role":
            link.role = "baseline"
        elif case == "student_role":
            writer.query(TaskModel).filter_by(task_id=task_id, model_version_id=lab.builtin.id).one().role = "student_under_test"
        elif case == "unknown_source":
            writer.get(Model, mv.model_id).source = "unknown"
        elif case == "missing_model":
            mv.model_id = "missing"
        elif case == "missing_version":
            link.model_version_id = "missing"
        elif case == "unknown_role":
            link.role = "other"
        elif case == "disabled_creator":
            writer.get(User, lab.owner.id).status = "disabled"
        elif case == "not_runnable":
            mv.status = "cannot_start"
        elif case == "cuda":
            mv.requires_cuda = True
        writer.commit()
    spies = worker_spies(monkeypatch)
    lab.queue.reset_mock()
    run = jobs.run_compare if kind == "compare" else jobs.run_eval
    with pytest.raises(AppError):
        run(task_id)
    lab.db.expire_all()
    task = lab.db.get(Task, task_id)
    assert task.status == "failed"
    assert task.error_summary and version_id not in task.error_summary
    assert str(lab.tmp) not in task.error_summary
    assert all(link.status == "failed" and link.fail_stage in {"auth", "protocol", "resource"} for link in task.models)
    # Submission now freezes inputs before enqueue; authorization must still
    # fail before inference produces any output or student working directory.
    assert {p.name for p in (lab.tmp / "tasks" / task_id).iterdir()} == {"inputs.json"}
    run(task_id)  # terminal failed tasks are not retried or replaced
    for spy in spies:
        spy.assert_not_called()
    lab.queue.assert_not_called()
    assert lab.db.query(Task).count() == 1


def test_worker_authorized_models_use_distinct_mocked_paths(lab, monkeypatch):
    task_id = create(lab, student=lab.shared.id).json()["id"]
    rgb = np.zeros((200, 200, 3), dtype=np.uint8)
    pred = np.zeros((200, 200), dtype=np.uint8)
    builtin = Mock(return_value=object())
    student = Mock(return_value={"s0": pred})
    monkeypatch.setattr(jobs, "read_rgb", lambda path: rgb)
    monkeypatch.setattr(jobs, "preprocess_rgb", lambda image, spec: object())
    monkeypatch.setattr(jobs, "get_builtin_module", builtin)
    monkeypatch.setattr(jobs, "predict_mask", Mock(return_value=pred))
    monkeypatch.setattr(jobs, "infer_student_masks", student)
    monkeypatch.setattr(jobs, "_try_write_cam", lambda **kwargs: {})
    jobs.run_compare(task_id)  # Actual orchestration/PNG/ZIP writes only under tmp_path.
    lab.db.expire_all()
    task = lab.db.get(Task, task_id)
    assert task.status == "success"
    assert all(link.status == "success" for link in task.models)
    assert builtin.call_count == student.call_count == 1
    assert builtin.call_args.args[0] == lab.builtin.id
    assert inspect(student.call_args.args[1]).identity[0] == lab.shared.id
    assert not (lab.tmp / "tasks" / task_id / "metrics.json").exists()


def test_worker_does_not_interrupt_or_restart_running_task(lab, monkeypatch):
    task_id = create(lab, student=lab.shared.id).json()["id"]
    task = lab.db.get(Task, task_id)
    task.status = "running"
    lab.shared.visibility = "private"
    lab.db.commit()
    spies = worker_spies(monkeypatch)
    jobs.run_compare(task_id)
    lab.db.expire_all()
    assert lab.db.get(Task, task_id).status == "running"
    for spy in spies:
        spy.assert_not_called()


def test_worker_refreshes_cached_authorization_rows(lab):
    task_id = create(lab, student=lab.shared.id).json()["id"]
    version_id = lab.shared.id
    with lab.factory() as worker:
        task = worker.get(Task, task_id)
        cached = worker.get(ModelVersion, version_id)
        assert cached.visibility == "shared"
        with lab.factory() as admin:
            admin.get(ModelVersion, version_id).visibility = "private"
            admin.commit()
        with pytest.raises(AppError) as error:
            jobs._assert_lab_execution_authorized(worker, task)
        assert error.value.code == "FORBIDDEN"


def result_task(lab, kind="compare", *, submitted=False):
    task_id = create(lab, kind if kind != "demo" else "compare").json()["id"]
    row = lab.db.get(Task, task_id)
    row.status = "success"
    row.type = kind
    row.submitted_to_advisor_at = utcnow() if submitted else None
    root = lab.tmp / "tasks" / task_id
    root.mkdir(parents=True, exist_ok=True)
    (root / "origin").mkdir()
    (root / "origin/s0.png").write_bytes(b"test-layer")
    (root / "task.json").write_text("{}", encoding="utf-8")
    with zipfile.ZipFile(root / "bundle.zip", "w") as archive:
        archive.write(root / "origin/s0.png", "origin/s0.png")
        archive.write(root / "task.json", "task.json")
    for kind, rel, sample in (("origin", "origin/s0.png", "s0"), ("log", "task.json", None), ("bundle", "bundle.zip", None)):
        lab.db.add(Artifact(id=new_id(), task_id=task_id, sample_key=sample, kind=kind, rel_path=rel))
    lab.db.commit()
    return row


@pytest.mark.parametrize("kind", ["compare", "eval"])
@pytest.mark.parametrize("path", ["", "/samples/s0/view", "/metrics", "/file/origin/s0.png", "/bundle"])
def test_advisor_read_endpoints_require_submission(lab, kind, path):
    task = result_task(lab, kind)
    with client(lab, lab.advisor) as http:
        response = http.get(f"/api/tasks/{task.id}{path}")
        assert response.status_code == 404
    with client(lab, lab.owner) as http:
        assert http.get(f"/api/tasks/{task.id}{path}").status_code == 200
    submit_to_advisor(lab.db, lab.owner, task.id)
    with client(lab, lab.advisor) as http:
        assert http.get(f"/api/tasks/{task.id}{path}").status_code == 200
    with client(lab, lab.peer) as http:
        assert http.get(f"/api/tasks/{task.id}{path}").status_code == 404


def test_record_inbox_owner_actions_and_withdrawal(lab):
    task = result_task(lab)
    with client(lab, lab.advisor) as http:
        assert http.get("/api/records?scope=inbox").json()["items"] == []
        assert http.patch(f"/api/records/{task.id}", json={"note": "x"}).status_code == 404
        assert http.post(f"/api/records/{task.id}/rerun").status_code == 404
    submit_to_advisor(lab.db, lab.owner, task.id)
    with client(lab, lab.advisor) as http:
        assert [row["id"] for row in http.get("/api/records?scope=inbox").json()["items"]] == [task.id]
        assert http.patch(f"/api/records/{task.id}", json={"note": "x"}).status_code == 403
        assert http.post(f"/api/records/{task.id}/rerun").status_code == 403
    withdraw_from_advisor(lab.db, lab.owner, task.id)
    with client(lab, lab.advisor) as http:
        assert http.get(f"/api/tasks/{task.id}/file/origin/s0.png").status_code == 404
    # There is no GET /records/{id} route: record detail uses GET /tasks/{id}.


@pytest.mark.parametrize("path", ["", "/file/origin/s0.png", "/bundle"])
def test_demo_policy_remains_independent(lab, path):
    task = result_task(lab, "demo")
    for actor in (lab.owner, lab.advisor):
        with client(lab, actor) as http:
            assert http.get(f"/api/demo/tasks/{task.id}{path}").status_code == 200
            assert http.get(f"/api/tasks/{task.id}{path}").status_code == 200
    with client(lab, lab.peer) as http:
        assert http.get(f"/api/demo/tasks/{task.id}{path}").status_code == 404
    task.creator_id, task.guest_sid = None, "guest-owner"
    lab.db.commit()
    with client(lab, None) as http:
        assert http.get(f"/api/demo/tasks/{task.id}{path}").status_code == 200
    with client(lab, None, sid="other-guest") as http:
        assert http.get(f"/api/demo/tasks/{task.id}{path}").status_code == 404


@pytest.mark.parametrize("actor", ["owner", "advisor"])
@pytest.mark.parametrize("entry", ["turns", "messages", "messages/stream"])
@pytest.mark.parametrize("visibility", ["shared", "private"])
def test_code_advice_content_policy_and_no_writes(lab, actor, entry, visibility, monkeypatch):
    mv = lab.shared
    mv.visibility = visibility
    lab.db.commit()
    root = lab.tmp / "models" / mv.id
    root.mkdir(parents=True)
    source = b"# fixture only; never imported\nclass MyModel: pass\n"
    (root / "model.py").write_bytes(source)
    monkeypatch.setattr(assistant, "_iter_writing", lambda *a, **k: iter([
        {"type": "end", "llm_status": "skipped", "llm_model": None, "writing": None}]))
    user = getattr(lab, actor)
    session = assistant.create_session(lab.db, user, specialty="model")
    with client(lab, user) as http:
        response = http.post(f"/api/assistant/sessions/{session.id}/{entry}", json={"tool": "code.advise", "version_id": mv.id})
    if visibility == "shared":
        assert response.status_code == 200
        assert "MyModel" in response.text
    elif entry.endswith("stream"):
        assert '"type": "error"' in response.text and '"code": "NOT_FOUND"' in response.text
    else:
        assert response.status_code == 404
    assert (root / "model.py").read_bytes() == source
    assert mv.status == "runnable"


@pytest.mark.parametrize("actor", ["owner", "advisor", "peer"])
@pytest.mark.parametrize("visibility", ["shared", "private"])
def test_admit_log_policy(lab, actor, visibility):
    mv = lab.shared
    mv.visibility = visibility
    lab.db.commit()
    root = lab.tmp / "models" / mv.id
    root.mkdir(parents=True)
    (root / "admit.log").write_text("safe fixture log", encoding="utf-8")
    with client(lab, getattr(lab, actor)) as http:
        response = http.get(f"/api/models/{mv.id}/admit-log")
    permitted = visibility == "shared" or actor == "peer"  # this version belongs to peer
    assert response.status_code == (200 if permitted else 404)
    if permitted:
        assert response.text == "safe fixture log"
    # Advisor metadata visibility remains intact; only content/run permissions narrow.
    assert can_view_version(lab.advisor, mv.model, mv)


def test_shared_does_not_grant_adapt_or_cross_specialty_access(lab):
    for user in (lab.owner, lab.advisor):
        with pytest.raises(AppError):
            apply_adapt(lab.db, user, lab.shared, lab.shared.model, consent=True, settings=lab.settings)
        session = assistant.create_session(lab.db, user, specialty="academic")
        with pytest.raises(AppError) as error:
            assistant.add_code_turn(lab.db, user, session.id, version_id=lab.shared.id)
        assert error.value.code == "TOOL_FORBIDDEN"


def test_no_new_model_source_or_weight_download_routes(lab):
    with client(lab, lab.owner) as http:
        for suffix in ("model.py", "weights.pth", "source", "weights", "file/model.py"):
            assert http.get(f"/api/models/{lab.shared.id}/{suffix}").status_code == 404
    # Task-directory artifacts are independently checked by the phase-B suite.


def test_isolation_ignores_process_settings(monkeypatch):
    monkeypatch.setenv("STORAGE_ROOT", "must-not-use-process-setting")
    monkeypatch.setenv("MILVUS_URI", "http://must-not-connect.invalid")
    settings = Settings()
    assert settings.storage_root != "must-not-use-process-setting"
    assert settings.milvus_uri == ""
    assert settings.mysql_dsn == "sqlite://"
    assert get_settings().seed_on_start is False


@pytest.mark.parametrize("sample_key", ["ordinary", "line #1", "query?fixture", "100%steel", "裂纹 01"])
def test_dataset_preview_url_round_trips_sample_names(lab, monkeypatch, sample_key):
    """Returned URLs must survive browser URL parsing without changing the key."""
    from app.routers import datasets as datasets_router
    from app.services import datasets

    monkeypatch.setattr(datasets, "get_settings", lambda: lab.settings)
    sample = lab.db.query(Sample).filter_by(version_id=lab.batch.id).one()
    sample.sample_key = sample_key
    lab.db.commit()
    with client(lab, lab.owner) as http:
        http.app.include_router(datasets_router.router, prefix="/api")
        listing = http.get(f"/api/datasets/{lab.batch.dataset_id}/versions/{lab.batch.id}/samples")
        assert listing.status_code == 200
        item = listing.json()["items"][0]
        assert item["sample_key"] == sample_key
        parsed = urlsplit(item["preview_url"])
        assert not parsed.fragment and not parsed.query
        preview = http.get(item["preview_url"])
        assert preview.status_code == 200
        assert preview.content == b"synthetic-origin"
    # URL escaping must not grant another student access to a private batch.
    with client(lab, lab.peer) as http:
        http.app.include_router(datasets_router.router, prefix="/api")
        assert http.get(item["preview_url"]).status_code == 403
