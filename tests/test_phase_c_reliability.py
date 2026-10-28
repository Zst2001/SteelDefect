"""Synthetic-only C regressions; run through run_phase_a_tests.py."""
import asyncio
import hashlib
import io
import json
import subprocess
import time
import zipfile
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError
from rq.exceptions import DuplicateJobError
from sqlalchemy import event
from starlette.datastructures import UploadFile

from test_phase_a_authorization import lab, client, create
from app import cache
from app.db.models import Sample, Task, TaskModel, ModelVersion, ModelPerfProfile
from app.errors import AppError
from app.services import dispatch, tasks, demo, input_freeze, perf, import_model, adapt
from app.services.demo_identity import DemoIdentity
from app.services.records import rerun_record
from apps.worker import jobs
from admit import dockerutil
from infer.spec import DEMO_CATALOG_KIND


@pytest.mark.parametrize("case,expected", [("ok", "confirmed"), ("preflight", "rejected"),
    ("timeout_saved", "confirmed"), ("timeout_absent", "unknown"), ("lookup_failed", "unknown"),
    ("duplicate", "confirmed"), ("hash_only", "unknown")])
def test_dispatch_three_outcomes(lab, monkeypatch, case, expected):
    calls = []
    class Queue:
        def __init__(self, *a, **kw): pass
        def enqueue_call(self, *, unique=False): pass
        def enqueue(self, function, obj, **kw):
            calls.append(kw)
            assert kw["unique"] and kw["job_id"] == "stable-id"
            if case == "duplicate": raise DuplicateJobError("synthetic duplicate")
            if case != "ok": raise RedisTimeoutError("synthetic")
        def fetch_job(self, job_id):
            if case == "lookup_failed": raise RedisConnectionError("synthetic")
            if case == "timeout_absent": return None
            return SimpleNamespace(func_name="worker", args=("object",), get_status=lambda: "queued")
        def get_job_position(self, job_id):
            return None if case == "hash_only" else 0
    conn = SimpleNamespace(ping=Mock(side_effect=RedisConnectionError() if case == "preflight" else None))
    monkeypatch.setattr(dispatch, "Queue", Queue)
    monkeypatch.setattr(dispatch, "rq_connection", lambda: conn)
    result = dispatch.enqueue(lab.settings, "worker", "object", 50, job_id="stable-id")
    assert result.state == expected
    assert len(calls) == (0 if case == "preflight" else 1)


@pytest.mark.parametrize("kind", ["compare", "eval"])
@pytest.mark.parametrize("outcome", ["confirmed", "rejected", "unknown"])
def test_task_delivery_state_and_http(lab, kind, outcome):
    lab.queue.return_value = dispatch.Delivery(outcome, "fake-job")
    response = create(lab, kind)
    assert response.status_code == 200  # Persisted resource, including its dispatch outcome.
    task = lab.db.get(Task, response.json()["id"])
    assert task.status == ("failed" if outcome == "rejected" else "queued")
    assert all(m.status == task.status for m in task.models)
    if outcome == "unknown": assert "QUEUE_UNKNOWN" in task.error_summary


def test_http_idempotency_and_conflict(lab):
    body = {"batch_id": lab.batch.id, "baseline_version_ids": [lab.builtin.id]}
    with client(lab, lab.owner) as http:
        first = http.post("/api/tasks/compare", json=body, headers={"Idempotency-Key": "one"})
        second = http.post("/api/tasks/compare", json=body, headers={"Idempotency-Key": "one"})
        assert first.status_code == second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        conflict = http.post("/api/tasks/compare", json={**body, "student_version_id": lab.mine.id}, headers={"Idempotency-Key": "one"})
        assert conflict.status_code == 409
    assert lab.queue.call_count == 1 and lab.db.query(Task).count() == 1


def test_commit_failure_never_enqueues(lab, monkeypatch):
    monkeypatch.setattr(lab.db, "commit", Mock(side_effect=RuntimeError("synthetic DB failure")))
    with pytest.raises(RuntimeError):
        tasks.create_compare_task(lab.db, lab.owner, batch_id=lab.batch.id,
                                  baseline_version_ids=[lab.builtin.id], student_version_id=None)
    lab.db.rollback()
    assert lab.db.query(Task).count() == 0
    lab.queue.assert_not_called()


@pytest.mark.parametrize("kind", ["compare", "eval"])
def test_freeze_failure_rolls_back_before_assistant_can_commit(lab, kind):
    (lab.tmp / "fake.png").write_bytes(b"changed before submission")
    with pytest.raises(AppError):
        if kind == "compare":
            tasks.create_compare_task(lab.db, lab.owner, batch_id=lab.batch.id,
                baseline_version_ids=[lab.builtin.id], student_version_id=None)
        else:
            tasks.create_eval_task(lab.db, lab.owner, dataset_version_id=lab.evaluation.id,
                baseline_version_ids=[lab.builtin.id], student_version_id=None)
    lab.db.commit()  # An outer caller can persist its error turn safely.
    assert lab.db.query(Task).count() == lab.db.query(TaskModel).count() == 0
    lab.queue.assert_not_called()


def test_cache_failure_is_only_a_bypass(lab, monkeypatch):
    broken = Mock()
    for name in ("get", "setex", "delete", "scan_iter"):
        getattr(broken, name).side_effect = RedisConnectionError("not logged")
    monkeypatch.setattr(cache, "cache_redis", lambda: broken)
    monkeypatch.setattr(tasks, "invalidate_after_write", cache.invalidate_after_write)
    assert cache.cache_get_json("x") is None
    cache.cache_set_json("x", {}, 1)
    cache.invalidate_models_lists()
    assert create(lab).status_code == 200
    assert lab.queue.call_count == 1
    broken.get.side_effect = ValueError("programming error")
    with pytest.raises(ValueError): cache.cache_get_json("x")


@pytest.mark.parametrize("outcome,refund", [("rejected", 1), ("unknown", 0), ("confirmed", 0)])
def test_demo_quota_and_duplicate(lab, monkeypatch, outcome, refund):
    lab.batch.kind = DEMO_CATALOG_KIND
    lab.db.commit()
    reserve, release = Mock(return_value=True), Mock()
    monkeypatch.setattr(demo, "reserve_guest_quota", reserve)
    monkeypatch.setattr(demo, "release_guest_quota", release)
    monkeypatch.setattr(demo, "invalidate_after_write", lambda *a: None)
    submit = Mock(return_value=dispatch.Delivery(outcome, "demo-job"))
    monkeypatch.setattr(demo, "_enqueue_task", submit)
    identity = DemoIdentity("synthetic-sid", None, "test", "test")
    args = dict(sample_keys=["s0"], baseline_version_ids=[lab.builtin.id], settings=lab.settings, idempotency_key="once")
    first = demo.create_demo_task(lab.db, identity, **args)
    second = demo.create_demo_task(lab.db, identity, **args)
    assert first.id == second.id
    assert reserve.call_count == submit.call_count == 1
    assert release.call_count == refund


@pytest.mark.parametrize("kind", ["compare", "demo"])
@pytest.mark.parametrize("state", ["running", "failed", "success", "partial_success"])
def test_duplicate_worker_skips_all_states(lab, monkeypatch, kind, state):
    task = lab.db.get(Task, create(lab).json()["id"])
    task.status, task.type = state, kind
    lab.db.commit()
    execute = Mock(side_effect=AssertionError("duplicate execution"))
    monkeypatch.setattr(jobs, "_run_compare_body", execute)
    monkeypatch.setattr(jobs, "_run_demo_body", execute)
    (jobs.run_demo if kind == "demo" else jobs.run_compare)(task.id)
    execute.assert_not_called()


@pytest.mark.parametrize("outcome", ["rejected", "unknown"])
def test_import_checking_delivery(lab, monkeypatch, outcome):
    monkeypatch.setattr(import_model, "enqueue_admit", lambda *a: dispatch.Delivery(outcome, "admit-job"))
    monkeypatch.setattr(import_model, "invalidate_after_write", lambda *a: None)
    async def submit():
        return await import_model.import_student_model(lab.db, lab.owner, name="synthetic", entry_symbol="build_model",
            num_classes=4, in_channels=3, requires_cuda=False,
            py_file=UploadFile(io.BytesIO(b"def build_model():\n    return None\n"), filename="model.py"),
            pth_file=UploadFile(io.BytesIO(b"synthetic-never-loaded"), filename="weights.pth"),
            settings=lab.settings, idempotency_key="same-import")
    version = asyncio.run(submit())
    assert version.status == ("cannot_start" if outcome == "rejected" else "checking")
    assert version.fail_stage == "queue"
    assert asyncio.run(submit()).id == version.id


def test_perf_delivery_and_no_duplicate_worker(lab, monkeypatch):
    monkeypatch.setattr(perf, "get_settings", lambda: lab.settings)
    monkeypatch.setattr(perf, "invalidate_models_lists", lambda: None)
    monkeypatch.setattr(perf, "invalidate_after_write", lambda *a: None)
    enqueue = Mock(return_value=dispatch.Delivery("unknown", "fake"))
    monkeypatch.setattr(perf, "enqueue_perf", enqueue)
    profile = perf.request_measure(lab.db, lab.mine, lab.mine.model)
    job_id = profile.job_id
    assert profile.status == "queued" and "QUEUE_UNKNOWN" in profile.fail_message
    assert perf.request_measure(lab.db, lab.mine, lab.mine.model).job_id == job_id
    assert enqueue.call_count == 1
    profile.status = "success"
    lab.db.commit()
    monkeypatch.setattr(jobs, "measure_student_version", Mock(side_effect=AssertionError("must not execute")))
    jobs.run_perf(lab.mine.id)


@pytest.mark.parametrize("outcome", ["rejected", "unknown", "confirmed"])
def test_adapt_dispatch_keeps_diagnostic_and_never_runnable(lab, monkeypatch, outcome):
    from test_slice_adapt import _source
    version = lab.mine
    version.status, version.fail_stage, version.fail_message = "cannot_start", "build", "missing build_model"
    lab.db.commit()
    folder = lab.tmp / "models" / version.id
    folder.mkdir(parents=True)
    source = folder / "model.py"
    source.write_text(_source(), encoding="utf-8")
    monkeypatch.setattr(adapt, "enqueue_admit", lambda *a: dispatch.Delivery(outcome, "synthetic-adapt"))
    monkeypatch.setattr(adapt, "invalidate_after_write", lambda *a: None)
    result = adapt.apply_adapt(lab.db, lab.owner, version, version.model, consent=True, settings=lab.settings)
    assert result["applied"] and version.status != "runnable"
    assert version.status == ("cannot_start" if outcome == "rejected" else "checking")
    assert "LAB_BUILD" in source.read_text(encoding="utf-8").upper()
    assert version.source_sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    if outcome != "confirmed":
        report = import_model.read_report(lab.settings, version.id)
        assert report["status"] == version.status and report["fail_stage"] == "queue"


def test_admit_duplicate_and_stale_generation_do_not_execute(lab, monkeypatch):
    version = lab.mine
    version.status, version.fail_stage = "checking", "admit_running"
    lab.db.commit()
    executor = Mock(side_effect=AssertionError("duplicate admit"))
    monkeypatch.setattr(jobs, "admit_version", executor)
    jobs.run_admit(version.id)
    version.fail_stage = None
    lab.db.commit()
    monkeypatch.setattr(jobs, "get_current_job", lambda: SimpleNamespace(id="old-generation"))
    jobs.run_admit(version.id)
    executor.assert_not_called()


def test_outer_job_timeout_reserves_cleanup_budget(monkeypatch):
    from apps.worker import student_exec
    from datetime import datetime, timezone
    job = SimpleNamespace(started_at=datetime.now(timezone.utc), timeout=50)
    monkeypatch.setattr(student_exec, "get_current_job", lambda: job)
    with pytest.raises(dockerutil.DockerUnavailable): student_exec._container_timeout(300, 600)
    job.timeout = 200
    assert 1 <= student_exec._container_timeout(300, 600) <= 100


def test_demo_database_failure_compensates_only_absent_record(lab, monkeypatch):
    lab.batch.kind = DEMO_CATALOG_KIND
    lab.db.commit()
    identity = DemoIdentity("synthetic-sid", None, "test", "test")
    release = Mock()
    monkeypatch.setattr(demo, "reserve_guest_quota", lambda *a: True)
    monkeypatch.setattr(demo, "release_guest_quota", release)
    monkeypatch.setattr(lab.db, "commit", Mock(side_effect=RuntimeError("commit failed")))
    with pytest.raises(RuntimeError):
        demo.create_demo_task(lab.db, identity, sample_keys=["s0"], baseline_version_ids=[lab.builtin.id], settings=lab.settings)
    assert lab.db.query(Task).count() == 0 and release.call_count == 1


def test_mask_upload_then_freeze_and_new_batch(lab, monkeypatch):
    import numpy as np
    from app.routers import uploads
    from infer.masks import encode_index_png
    monkeypatch.setattr(uploads, "get_settings", lambda: lab.settings)
    first_mask = encode_index_png(np.zeros((200, 200), dtype=np.uint8))
    second_mask = encode_index_png(np.ones((200, 200), dtype=np.uint8))
    with client(lab, lab.owner) as http:
        http.app.include_router(uploads.router, prefix="/api")
        def upload(data):
            return http.post("/api/uploads/masks", data={"batch_id": lab.batch.id}, files={"files": ("s0.png", data, "image/png")})
        assert upload(first_mask).status_code == 200
        sample = lab.db.query(Sample).filter_by(version_id=lab.batch.id).one()
        old_uri = sample.mask_uri
        old_file = lab.tmp / old_uri.removeprefix("data:")
        assert upload(second_mask).status_code == 200
        lab.db.refresh(sample)
        assert old_uri != sample.mask_uri and old_file.read_bytes() == first_mask
        task = lab.db.get(Task, create(lab).json()["id"])
        assert task.has_gt
        assert upload(first_mask).status_code == 409
        frozen = input_freeze.verify_inputs(lab.db, task, lab.settings)
        assert frozen["samples"][0]["mask_sha256"] == hashlib.sha256(second_mask).hexdigest()
        import cv2
        image = np.full((200, 200, 3), 114, dtype=np.uint8)
        image[10:50, 10:70] = (47, 80, 153)
        _, encoded = cv2.imencode(".jpg", image)
        uploaded = http.post("/api/uploads/images", files={"files": ("s0.jpg", encoded.tobytes(), "image/jpeg")})
        assert uploaded.status_code == 200
        new_batch = uploaded.json()["batch_id"]
        assert new_batch != lab.batch.id
        corrected = http.post("/api/uploads/masks", data={"batch_id": new_batch}, files={"files": ("s0.png", first_mask, "image/png")})
        assert corrected.status_code == 200
        assert http.get(f"/api/tasks/{task.id}/file/inputs.json").status_code == 404
    assert input_freeze.verify_inputs(lab.db, task, lab.settings) == frozen


@pytest.mark.parametrize("status", ["queued", "running", "success", "failed"])
def test_referenced_batch_rejects_masks(lab, status):
    task = lab.db.get(Task, create(lab).json()["id"])
    task.status = status
    lab.db.commit()
    version = input_freeze.lock_version(lab.db, lab.batch.id)
    with pytest.raises(AppError, match="新批次") as caught:
        input_freeze.assert_unreferenced(lab.db, version)
    assert caught.value.code == "DATASET_FROZEN"
    assert list(lab.tmp.glob("uploads/**/masks/*")) == []


@pytest.mark.parametrize("change", ["origin_bytes", "mask_bytes", "mask_uri", "sample_key", "manifest_missing"])
def test_input_changes_rejected(lab, change):
    task = lab.db.get(Task, create(lab, "eval").json()["id"])
    if change == "origin_bytes": (lab.tmp / "fake.png").write_bytes(b"changed")
    elif change == "mask_bytes": (lab.tmp / "fake-gt.png").write_bytes(b"changed")
    elif change == "manifest_missing": input_freeze.manifest_path(lab.settings, task.id).unlink()
    else:
        sample = lab.db.get(Sample, task.samples[0].sample_id)
        setattr(sample, change, "changed")
        lab.db.commit()
    with pytest.raises(AppError) as caught: input_freeze.verify_inputs(lab.db, task, lab.settings)
    assert caught.value.code == "INPUT_CHANGED"


def test_hashes_and_rerun_version_binding(lab):
    task = lab.db.get(Task, create(lab).json()["id"])
    inputs = input_freeze.verify_inputs(lab.db, task, lab.settings)
    assert inputs["samples"][0]["origin_sha256"] == hashlib.sha256(b"synthetic-origin").hexdigest()
    assert "origin_uri" not in inputs["samples"][0]
    rerun = rerun_record(lab.db, lab.owner, task.id)
    assert rerun.id != task.id and rerun.dataset_version_id == task.dataset_version_id
    assert input_freeze.verify_inputs(lab.db, rerun, lab.settings) == inputs


@pytest.mark.parametrize("failure", [None, "timeout", "start", "read", "read_io", "stop", "kill", "rm", "inspect", "owner"])
@pytest.mark.parametrize("mode", ["admit", "infer"])
def test_container_cleanup_uses_exact_identity(lab, monkeypatch, failure, mode):
    calls, names = [], []
    exists = False
    out = lab.tmp / "docker-out"
    out.mkdir()
    (out / "result.json").write_text("invalid" if failure == "read" else '{"ok": true}', encoding="utf-8")
    if failure == "read_io":
        from pathlib import Path
        original_read = Path.read_text
        def read(path, *args, **kwargs):
            if path == out / "result.json": raise OSError("synthetic output read failure")
            return original_read(path, *args, **kwargs)
        monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(dockerutil, "docker_available", lambda: True)
    monkeypatch.setattr(dockerutil, "image_present", lambda *a: True)
    def run(cmd, **kwargs):
        nonlocal exists
        calls.append(cmd)
        action = cmd[1]
        if action == "run":
            name = cmd[cmd.index("--name") + 1]
            names.append(name)
            assert f"steel.operation={name}" in cmd
            assert all(x in cmd for x in ("--network=none", "--read-only", "--cap-drop", "--user", "--memory", "--cpus"))
            if failure == "start": raise OSError("synthetic CLI failure")
            exists = True
            if failure in {"timeout", "stop", "kill", "rm", "inspect", "owner"}: raise subprocess.TimeoutExpired(cmd, 1)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        assert cmd[-1] == names[-1]  # No global prune, wildcard or unrelated container.
        if action == "inspect":
            if failure == "inspect": raise OSError("inspect unavailable")
            if not exists: return SimpleNamespace(returncode=1, stdout="", stderr="No such object")
            data = [{"Config": {"Labels": {"steel.operation": "other" if failure == "owner" else names[-1]}}, "State": {"Running": True}}]
            return SimpleNamespace(returncode=0, stdout=json.dumps(data), stderr="")
        return SimpleNamespace(returncode=1 if action == failure or (failure == "kill" and action == "stop") else 0, stdout="", stderr="failed")
    monkeypatch.setattr(dockerutil.subprocess, "run", run)
    if failure:
        with pytest.raises(dockerutil.DockerUnavailable) as caught:
            dockerutil.run_student_container(image="fake", mode=mode, in_dir=lab.tmp, out_dir=out, timeout_sec=1, operation_id="task/version")
        if failure in {"rm", "inspect", "owner"}: assert "清理未确认" in str(caught.value)
    else:
        for _ in range(2):
            result = dockerutil.run_student_container(image="fake", mode=mode, in_dir=lab.tmp, out_dir=out, timeout_sec=1)
            assert result["cleanup_confirmed"] is True
        assert names[0] != names[1]
    if failure == "owner": assert not any(c[1] in {"stop", "kill", "rm"} for c in calls)


@pytest.mark.parametrize("sample_count", [1, 20, 50])
def test_artifact_serialization_measurement(lab, monkeypatch, capsys, sample_count):
    from test_task_artifact_access import result_task, layers, register
    from app.db.models import TaskSample
    from app.util_time import new_id
    task = result_task(lab)
    layers(lab, task)
    for i in range(1, sample_count):
        sample = Sample(id=new_id(), version_id=task.dataset_version_id, sample_key=f"s{i}",
                        origin_uri="data:fake.png", sha256="synthetic", width=200, height=200)
        lab.db.add(sample)
        lab.db.flush()
        lab.db.add(TaskSample(id=new_id(), task_id=task.id, sample_id=sample.id, sort_order=i))
        register(lab, task, f"origin/s{i}.png", "origin", sample=f"s{i}")
        register(lab, task, f"pred/{lab.builtin.id}/s{i}.png", "pred_color", sample=f"s{i}", model=lab.builtin.id)
    lab.db.commit()
    from app.services.task_artifacts import write_bundle
    write_bundle(lab.db, task, lab.settings)
    sql_count = 0
    opens = 0
    def query(*a):
        nonlocal sql_count
        sql_count += 1
    original = zipfile.ZipFile
    def archive(*a, **kw):
        nonlocal opens
        opens += 1
        return original(*a, **kw)
    monkeypatch.setattr(zipfile, "ZipFile", archive)
    event.listen(lab.db.bind, "before_cursor_execute", query)
    try:
        start = time.perf_counter()
        result = tasks.serialize_task(lab.db, task)
        elapsed = time.perf_counter() - start
    finally:
        event.remove(lab.db.bind, "before_cursor_execute", query)
    assert result["bundle_ready"]
    with capsys.disabled(): print(f"C5 synthetic samples={sample_count}: SQL={sql_count} ZIP_OPEN={opens} elapsed_ms={elapsed*1000:.3f}")
    assert opens == 1
    # A later request must not reuse the serializer's successful observation.
    (lab.tmp / "tasks" / task.id / "bundle.zip").write_bytes(b"changed")
    with client(lab, lab.owner) as http:
        assert http.get(f"/api/tasks/{task.id}/bundle").status_code == 404
