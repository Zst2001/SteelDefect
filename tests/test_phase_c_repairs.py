"""Targeted C-R1/R2/R3 regressions; synthetic inputs and fake Docker only."""
import asyncio
import hashlib
import io
import json
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.datastructures import UploadFile

from test_phase_a_authorization import lab
from app.db.models import ModelVersion, Weight, Task, TaskModel, TaskSample, Sample, ModelPerfProfile
from app.errors import AppError
from app.services import import_model, tasks, perf, demo, input_freeze, submission
from app.services.dispatch import Delivery
from app.services.demo_identity import DemoIdentity
from admit import dockerutil
from infer.spec import DEMO_CATALOG_KIND
from apps.worker import jobs
from app.services import records
from app.util_time import new_id, utcnow


def _record_for_review(lab, *, submitted=True):
    task = Task(id=new_id(), type="compare", creator_id=lab.owner.id,
                dataset_version_id=lab.batch.id, preprocess_id=lab.spec.id,
                status="success", has_gt=False,
                submitted_to_advisor_at=utcnow() if submitted else None)
    lab.db.add(task)
    lab.db.commit()
    lab.db.refresh(task)
    return task


def test_record_withdraw_refreshes_advisor_seen_state(lab):
    task = _record_for_review(lab)
    lab.db.query(Task).filter_by(id=task.id).update(
        {"advisor_seen_at": utcnow()}, synchronize_session=False)
    assert task.advisor_seen_at is None  # Simulate a previously loaded ORM instance.
    with pytest.raises(AppError) as caught:
        records.withdraw_from_advisor(lab.db, lab.owner, task.id)
    assert caught.value.code == "ALREADY_SEEN"
    assert task.submitted_to_advisor_at is not None


def test_record_submit_refreshes_archived_state(lab):
    task = _record_for_review(lab, submitted=False)
    lab.db.query(Task).filter_by(id=task.id).update(
        {"archived": True}, synchronize_session=False)
    assert not task.archived
    with pytest.raises(AppError) as caught:
        records.submit_to_advisor(lab.db, lab.owner, task.id)
    assert caught.value.code == "ARCHIVED"
    assert task.submitted_to_advisor_at is None


def test_record_advisor_seen_rechecks_withdrawn_access(lab):
    task = _record_for_review(lab)
    lab.db.query(Task).filter_by(id=task.id).update(
        {"submitted_to_advisor_at": None}, synchronize_session=False)
    assert task.submitted_to_advisor_at is not None
    with pytest.raises(AppError) as caught:
        records.maybe_mark_advisor_seen(lab.db, task, lab.advisor)
    assert caught.value.code == "NOT_FOUND" and caught.value.status_code == 404
    assert task.advisor_seen_at is None


SOURCE = b"def build_model():\n    return None\n"
WEIGHTS = b"synthetic-weights-never-loaded"


def submit_import(lab, key="same", **changes):
    args = dict(name="repair-test", entry_symbol="build_model", num_classes=4,
                in_channels=3, requires_cuda=False, settings=lab.settings, idempotency_key=key)
    source = changes.pop("source", SOURCE)
    weights = changes.pop("weights", WEIGHTS)
    args.update(changes)
    return asyncio.run(import_model.import_student_model(lab.db, lab.owner,
        py_file=UploadFile(io.BytesIO(source), filename="model.py"),
        pth_file=UploadFile(io.BytesIO(weights), filename="weights.pth"), **args))


@pytest.fixture
def imports(lab, monkeypatch):
    queue = Mock(return_value=Delivery("confirmed", "synthetic-admit"))
    monkeypatch.setattr(import_model, "enqueue_admit", queue)
    monkeypatch.setattr(import_model, "invalidate_after_write", lambda *a: None)
    return queue


@pytest.mark.parametrize("change", [{}, {"source": SOURCE + b"# changed\n"}, {"weights": b"different"},
    {"name": "changed"}, {"entry_symbol": "different"}, {"num_classes": 3}, {"in_channels": 1}, {"requires_cuda": True}])
def test_import_idempotency_preserves_bytes_and_hashes(lab, imports, change):
    first = submit_import(lab)
    version_id = first.id
    root = import_model.model_dir(lab.settings, version_id)
    before = [(root / name).read_bytes() for name in ("model.py", "weights.pth")]
    if change:
        with pytest.raises(AppError) as caught:
            submit_import(lab, **change)
        assert caught.value.code == "IDEMPOTENCY_CONFLICT" and caught.value.status_code == 409
        lab.db.rollback()
    else:
        assert submit_import(lab).id == version_id
    assert [(root / name).read_bytes() for name in ("model.py", "weights.pth")] == before
    assert lab.db.get(ModelVersion, version_id).source_sha256 == hashlib.sha256(SOURCE).hexdigest()
    assert lab.db.query(Weight).filter_by(version_id=version_id).one().sha256 == hashlib.sha256(WEIGHTS).hexdigest()
    assert imports.call_count == 1


def test_import_existing_orphan_directory_is_never_overwritten(lab, imports):
    version_id = submission.request_id("import", lab.owner.id, "orphan")
    root = import_model.model_dir(lab.settings, version_id)
    root.mkdir(parents=True)
    (root / "model.py").write_bytes(b"preserve-source")
    (root / "weights.pth").write_bytes(b"preserve-weights")
    with pytest.raises(AppError) as caught:
        submit_import(lab, key="orphan")
    assert caught.value.code == "MODEL_STORAGE_CONFLICT"
    assert (root / "model.py").read_bytes() == b"preserve-source"
    assert (root / "weights.pth").read_bytes() == b"preserve-weights"
    imports.assert_not_called()


def test_failed_insert_keeps_committed_files_and_refuses_orphan_reuse(lab, imports, monkeypatch):
    first = submit_import(lab)
    first_id = first.id
    first_root = import_model.model_dir(lab.settings, first_id)
    fail = IntegrityError("synthetic insert", {}, RuntimeError("synthetic constraint"))
    with monkeypatch.context() as patch:
        patch.setattr(lab.db, "flush", Mock(side_effect=fail))
        with pytest.raises(IntegrityError):
            submit_import(lab, key="failed", source=SOURCE + b"# different\n")
    lab.db.rollback()
    assert (first_root / "model.py").read_bytes() == SOURCE
    assert (first_root / "weights.pth").read_bytes() == WEIGHTS
    assert lab.db.get(ModelVersion, first_id).source_sha256 == hashlib.sha256(SOURCE).hexdigest()
    assert lab.db.query(Weight).filter_by(version_id=first_id).one().sha256 == hashlib.sha256(WEIGHTS).hexdigest()
    failed_id = submission.request_id("import", lab.owner.id, "failed")
    assert lab.db.get(ModelVersion, failed_id) is None
    orphan = import_model.model_dir(lab.settings, failed_id)
    before = (orphan / "model.py").read_bytes()
    with pytest.raises(AppError) as caught:
        submit_import(lab, key="failed")
    assert caught.value.code == "MODEL_STORAGE_CONFLICT"
    assert (orphan / "model.py").read_bytes() == before
    assert imports.call_count == 1


@pytest.mark.parametrize("message,expected", [
    ("Error: No such object: {name}", True),
    ("Error response from daemon: No such container: {name}", True),
    ("no such file or directory", False), ("no such socket", False),
    ("Cannot connect to the Docker daemon", False), ("permission denied", False),
    ("Error: No such object: other-container", False),
    ("Error: No such object: {name}\npermission denied", False),
])
def test_cleanup_missing_requires_exact_target(monkeypatch, message, expected):
    name = "steel-infer-synthetic"
    monkeypatch.setattr(dockerutil.subprocess, "run", Mock(return_value=SimpleNamespace(
        returncode=1, stderr=message.format(name=name), stdout="")))
    assert dockerutil._cleanup(name, [], creation_completed=True) is expected
    assert dockerutil._cleanup(name, [], creation_completed=False) is False


@pytest.mark.parametrize("mode", ["admit", "infer", "perf"])
@pytest.mark.parametrize("failure", ["timeout", "oserror", "nonzero"])
def test_uncertain_create_then_exact_absence_is_not_release(tmp_path, monkeypatch, mode, failure):
    monkeypatch.setattr(dockerutil, "docker_available", lambda: True)
    monkeypatch.setattr(dockerutil, "image_present", lambda image: True)
    def run(cmd, **kwargs):
        if cmd[1] == "run":
            if failure == "timeout": raise subprocess.TimeoutExpired(cmd, 1)
            if failure == "oserror": raise OSError("synthetic client failure")
            return SimpleNamespace(returncode=125, stdout="", stderr="synthetic client failure")
        assert cmd[1] == "inspect"
        return SimpleNamespace(returncode=1, stdout="", stderr=f"Error: No such object: {cmd[-1]}")
    monkeypatch.setattr(dockerutil.subprocess, "run", run)
    with pytest.raises(dockerutil.DockerUnavailable, match="清理未确认"):
        dockerutil.run_student_container(image="fake", mode=mode, in_dir=tmp_path,
            out_dir=tmp_path / "out", timeout_sec=1)


@pytest.mark.parametrize("case,expected", [("stop_fails", True), ("rm_fails", False),
    ("rm_missing_exact", True), ("rm_missing_file", False), ("owner", False),
    ("malformed", False), ("null_labels", False), ("timeout", False)])
def test_cleanup_fallback_and_ownership(monkeypatch, case, expected):
    name, actions = "steel-perf-synthetic", []
    def run(cmd, **kwargs):
        action = cmd[1]
        actions.append(action)
        assert cmd[-1] == name and kwargs["timeout"] == 10
        if action == "inspect":
            if case == "timeout": raise subprocess.TimeoutExpired(cmd, 10)
            labels = None if case == "null_labels" else {"steel.operation": "other" if case == "owner" else name}
            output = "bad" if case == "malformed" else json.dumps([{"Config": {"Labels": labels}, "State": {"Running": True}}])
            return SimpleNamespace(returncode=0, stdout=output, stderr="")
        fail = (action == "stop" and case == "stop_fails") or (action == "rm" and case.startswith("rm_"))
        stderr = f"Error response from daemon: No such container: {name}" if case == "rm_missing_exact" else "no such file"
        return SimpleNamespace(returncode=int(fail), stdout="", stderr=stderr)
    monkeypatch.setattr(dockerutil.subprocess, "run", run)
    assert dockerutil._cleanup(name, [], creation_completed=False) is expected
    if case == "stop_fails": assert actions == ["inspect", "stop", "kill", "rm"]
    if case in {"owner", "malformed", "null_labels", "timeout"}: assert actions == ["inspect"]


@pytest.mark.parametrize("kind,count", [("compare", 1), ("eval", 20), ("demo", 1)])
def test_same_request_has_one_task_and_current_associations(lab, monkeypatch, kind, count):
    if kind == "demo":
        lab.batch.kind = DEMO_CATALOG_KIND
        lab.db.commit()
        monkeypatch.setattr(demo, "_enqueue_task", lab.queue)
        monkeypatch.setattr(demo, "invalidate_after_write", lambda *a: None)
    statements = []
    def capture(state):
        if state.is_select:
            statements.append(state.statement)
    event.listen(lab.db, "do_orm_execute", capture)
    try:
        def submit():
            common = dict(baseline_version_ids=[lab.builtin.id], settings=lab.settings, idempotency_key="one")
            if kind == "demo":
                return demo.create_demo_task(lab.db, DemoIdentity("test", lab.owner, "test", "test"), sample_keys=["s0"], **common)
            return getattr(tasks, f"create_{kind}_task")(lab.db, lab.owner, student_version_id=None,
                **{("batch_id" if kind == "compare" else "dataset_version_id"): (lab.batch.id if kind == "compare" else lab.evaluation.id)}, **common)
        first_id = submit().id
        assert submit().id == first_id
        assert lab.db.query(Task).count() == 1
        assert lab.db.query(TaskModel).count() == 1 and lab.db.query(TaskSample).count() == count
        assert lab.queue.call_count == 1
        # This checks emitted query intent, NOT actual SQLite/MySQL locking behavior.
        for table in ("tasks", "task_models", "samples"):
            assert any(table in str(s) and s._for_update_arg is not None for s in statements)
        if kind == "demo":
            assert any("JOIN task_samples" in str(s) and s._for_update_arg is not None for s in statements)
    finally:
        event.remove(lab.db, "do_orm_execute", capture)


@pytest.mark.parametrize("kind", ["compare", "eval"])
def test_lock_exception_after_insert_rolls_back_all_links(lab, monkeypatch, kind):
    def fail(*args):
        raise OperationalError("synthetic lock wait", {}, RuntimeError("lock timeout"))
    monkeypatch.setattr(tasks, "freeze_inputs", fail)
    with pytest.raises(OperationalError):
        getattr(tasks, f"create_{kind}_task")(lab.db, lab.owner, baseline_version_ids=[lab.builtin.id], student_version_id=None,
            **{("batch_id" if kind == "compare" else "dataset_version_id"): (lab.batch.id if kind == "compare" else lab.evaluation.id)})
    lab.db.commit()
    assert lab.db.query(Task).count() == lab.db.query(TaskModel).count() == lab.db.query(TaskSample).count() == 0
    lab.queue.assert_not_called()


def test_perf_current_profile_keeps_new_generation(lab, monkeypatch):
    monkeypatch.setattr(perf, "get_settings", lambda: lab.settings)
    monkeypatch.setattr(perf, "invalidate_models_lists", lambda: None)
    monkeypatch.setattr(perf, "invalidate_after_write", lambda *a: None)
    queue = Mock(return_value=Delivery("confirmed", "fake"))
    monkeypatch.setattr(perf, "enqueue_perf", queue)
    first = perf.request_measure(lab.db, lab.mine, lab.mine.model, idempotency_key="first")
    version_id, profile_id = lab.mine.id, first.id
    lab.db.query(ModelPerfProfile).filter_by(id=profile_id).update(
        {"job_id": "newer-generation", "status": "measuring"}, synchronize_session=False)
    # Keep deliberately stale ORM attributes; a current read must refresh them.
    second = perf.request_measure(lab.db, lab.mine, lab.mine.model, idempotency_key="second")
    assert second.job_id == "newer-generation" and second.status == "measuring"
    assert second.version_id == version_id and queue.call_count == 1


def test_worker_parent_lock_order_precedes_input_and_model_locks(lab, monkeypatch):
    task = tasks.create_compare_task(lab.db, lab.owner, batch_id=lab.batch.id,
        baseline_version_ids=[lab.builtin.id], student_version_id=None)
    task_id = task.id
    locked = []
    def capture(state):
        if state.is_select and state.statement._for_update_arg is not None:
            locked.append(str(state.statement))
    from sqlalchemy.orm import Session
    event.listen(Session, "do_orm_execute", capture)
    monkeypatch.setattr(jobs, "_run_compare_body", lambda *a: None)
    try:
        jobs.run_compare(task_id)
    finally:
        event.remove(Session, "do_orm_execute", capture)
    def position(table):
        return next(i for i, statement in enumerate(locked) if f"FROM {table} " in statement.replace("\n", " "))
    assert position("users") < position("dataset_versions") < position("tasks")
    assert position("tasks") < position("task_models") < position("model_versions")
    assert position("dataset_versions") < position("samples")
