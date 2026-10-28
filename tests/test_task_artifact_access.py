"""Offline stage-B regressions; collected only through the reviewed runner."""
from __future__ import annotations
import json

import stat
import warnings
import zipfile
from pathlib import Path
from unittest.mock import Mock

import pytest

# Import guarded phase-A fixtures, preserving the same isolated app and actors.
from test_phase_a_authorization import lab, client, create, result_task
from app.db.models import Artifact, Dataset, MetricSet, Sample, Task, TaskModel
from app.errors import AppError
from app.services import dashboard, demo, records, tasks, task_artifacts
from app.services.task_artifacts import TaskArtifacts, write_bundle
from app.util_time import new_id
from apps.worker import jobs


def register(lab, task, rel, kind, sample="s0", model=None, *, data=b"fixture", flush=True):
    path = lab.tmp / "tasks" / task.id / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    row = Artifact(id=new_id(), task_id=task.id, rel_path=rel, kind=kind,
                   sample_key=sample, model_version_id=model)
    lab.db.add(row)
    if flush:
        lab.db.flush()
    return row


def policy(lab, task):
    return TaskArtifacts(lab.db, task, lab.settings)


def pair_gt(lab, task):
    task.has_gt = True
    for sample in lab.db.query(Sample).filter_by(version_id=task.dataset_version_id):
        sample.mask_uri = "data:synthetic-gt.png"
    lab.db.commit()


def layers(lab, task):
    mid = lab.builtin.id
    specs = [("pred_color", f"pred/{mid}/s0.png", mid),
             ("overlay", f"overlay/{mid}/s0.png", mid),
             ("boundary", f"boundary/{mid}/s0.png", mid),
             ("cam", f"cam/{mid}/s0__c1.png", mid),
             ("montage", "montage/s0__mask.png", None),
             ("montage", "montage/s0__overlay.png", None),
             ("montage", "montage/s0__cam_c1.png", None)]
    for kind, rel, model in specs:
        register(lab, task, rel, kind, model=model)
    return [rel for _, rel, _ in specs]


@pytest.mark.parametrize("kind", ["compare", "eval", "demo"])
def test_legitimate_layers_and_serializers(lab, kind):
    task = result_task(lab, kind)
    rels = layers(lab, task)
    write_bundle(lab.db, task, lab.settings)
    lab.db.commit()
    expected = {"origin/s0.png", "task.json", *rels}
    if kind == "eval":
        expected -= {"montage/s0__mask.png", "montage/s0__overlay.png"}
    with client(lab, lab.owner) as http:
        for prefix in (["/api/tasks", "/api/demo/tasks"] if kind == "demo" else ["/api/tasks"]):
            for rel in expected:
                assert http.get(f"{prefix}/{task.id}/file/{rel}").status_code == 200
            for suffix in ("/bundle", "/file/bundle.zip"):
                response = http.get(f"{prefix}/{task.id}{suffix}")
                assert response.status_code == 200
            payload = http.get(f"{prefix}/{task.id}").json()
            assert payload["bundle_ready"] is True
            assert payload["preview_sample_keys"] == ["s0"]
            assert {a["url"].split('/file/')[1] for a in payload["artifacts"]} == expected | {"bundle.zip"}
    with zipfile.ZipFile(lab.tmp / "tasks" / task.id / "bundle.zip") as archive:
        assert set(archive.namelist()) == expected
    assert records.serialize_record(lab.db, task, lab.owner)["bundle_ready"]
    assert dashboard._task_payload(task, lab.db)["bundle_ready"]


@pytest.mark.parametrize("restriction", [None, "fixed", "forbid", "preset", "wrong_owner", "missing_gt"])
def test_gt_derivative_policy(lab, restriction):
    task = result_task(lab)
    pair_gt(lab, task)
    if restriction == "fixed": lab.batch.is_fixed_test = True
    if restriction == "forbid": lab.batch.forbid_student_gt_download = True
    if restriction == "preset": lab.batch.kind = "preset"
    if restriction == "wrong_owner": lab.db.get(Dataset, lab.batch.dataset_id).owner_id = lab.peer.id
    if restriction == "missing_gt": lab.db.query(Sample).filter_by(version_id=lab.batch.id).one().mask_uri = None
    lab.db.commit()
    mid = lab.builtin.id
    gt = ["gt/s0.png", f"error/{mid}/s0.png", "montage/s0__error.png", "montage/s0__mask.png", "montage/s0__overlay.png"]
    for kind, rel, model in [("gt", gt[0], None), ("error", gt[1], mid), *[("montage", r, None) for r in gt[2:]]]:
        register(lab, task, rel, kind, model=model)
    with client(lab, lab.owner) as http:
        for rel in gt:
            response = http.get(f"/api/tasks/{task.id}/file/{rel}")
            assert response.status_code == (200 if restriction is None else 404)
    write_bundle(lab.db, task, lab.settings)
    with zipfile.ZipFile(policy(lab, task).file("bundle.zip")) as archive:
        assert set(gt).issubset(archive.namelist()) if restriction is None else not set(gt).intersection(archive.namelist())


@pytest.mark.parametrize("rel,artifact_kind", [
    ("student/m/model.py", "origin"), ("student/m/weights.pth", "log"),
    ("student/m/manifest.json", "log"), ("student/m/input.npy", "origin"),
    ("student/m/pred.npy", "pred_color"), ("student/m/result.json", "log"),
    ("student/m/error.json", "log"), ("model.py", "origin"), ("weights.pth", "bundle"),
    ("metrics.json", "log"), ("report.pdf", "montage"), ("admit.log", "log"),
    ("origin/extra.png", "origin"), ("overlay/s0.png", "origin"),
    ("origin/s0.png", "unknown"), ("origin/s0.png", "pred_color"),
    ("task.json", "origin"), ("montage/s0__arbitrary.png", "montage"),
])
@pytest.mark.parametrize("kind", ["compare", "demo"])
def test_registered_invalid_files_are_not_authority(lab, rel, artifact_kind, kind):
    task = result_task(lab, kind)
    # Remove valid registration if attacking an existing name, avoiding only testing duplicates.
    lab.db.query(Artifact).filter_by(task_id=task.id, rel_path=rel).delete()
    register(lab, task, rel, artifact_kind)
    lab.db.commit()
    with client(lab, lab.owner) as http:
        for prefix in (["/api/tasks", "/api/demo/tasks"] if kind == "demo" else ["/api/tasks"]):
            response = http.get(f"{prefix}/{task.id}/file/{rel}")
            assert response.status_code == 404
            assert str(lab.tmp) not in response.text
            payload = http.get(f"{prefix}/{task.id}").json()
            assert not any(a["url"].endswith('/file/' + rel) for a in payload["artifacts"])


@pytest.mark.parametrize("case", ["missing", "other_task", "duplicate", "conflict", "case_alias", "wrong_sample", "wrong_model"])
def test_registry_binding(lab, case):
    task = result_task(lab)
    row = lab.db.query(Artifact).filter_by(task_id=task.id, rel_path="origin/s0.png").one()
    if case == "missing": lab.db.delete(row)
    elif case == "other_task": row.task_id = result_task(lab).id
    elif case == "wrong_sample": row.sample_key = "s1"
    elif case == "wrong_model": row.model_version_id = lab.builtin.id
    else:
        lab.db.add(Artifact(id=new_id(), task_id=task.id, sample_key="s0",
                            kind="origin" if case != "conflict" else "log",
                            rel_path="ORIGIN/s0.png" if case == "case_alias" else "origin/s0.png"))
    lab.db.commit()
    with client(lab, lab.owner) as http:
        assert http.get(f"/api/tasks/{task.id}/file/origin/s0.png").status_code == 404
        assert http.get(f"/api/tasks/{task.id}/bundle").status_code == 404


@pytest.mark.parametrize("rel", ["../task.json", "/task.json", "C:/task.json", "C:task.json", "\\\\host\\task.json",
                                  "origin/../task.json", "origin\\s0.png", "origin//s0.png", "./task.json",
                                  "origin/s0.png:secret", "task.json.", "task.json ", "NUL", "task.json\x00.txt"])
def test_noncanonical_paths(lab, rel):
    task = result_task(lab)
    with pytest.raises(AppError) as error:
        policy(lab, task).file(rel)
    assert str(lab.tmp) not in error.value.message


def test_encoded_traversal_http(lab):
    task = result_task(lab)
    with client(lab, lab.owner) as http:
        for rel in ("%2e%2e%2ftask.json", "%2ftask.json", "C%3a%2ftask.json", "origin%5cs0.png"):
            assert http.get(f"/api/tasks/{task.id}/file/{rel}").status_code == 404


@pytest.mark.parametrize("target", ["file", "task_root", "folder"])
def test_symlinks_are_rejected(lab, target):
    task = result_task(lab)
    root = lab.tmp / "tasks" / task.id
    outside = lab.tmp / "outside"
    outside.mkdir()
    (outside / "s0.png").write_bytes(b"outside")
    link = root / "origin/s0.png"
    if target == "file": link.unlink()
    elif target == "folder":
        link.unlink()
        link = root / "origin"
        link.rmdir()
    else:
        # All moved files are synthetic fixtures under tmp_path.
        moved = lab.tmp / "moved-task"
        root.rename(moved)
        outside = moved
        link = root
    try:
        link.symlink_to(outside / "s0.png" if target == "file" else outside, target_is_directory=target != "file")
    except OSError:
        pytest.skip("Host does not permit creating test symlinks; no production path touched")
    with pytest.raises(AppError):
        policy(lab, task).file("origin/s0.png")


@pytest.mark.parametrize("bad", ["../escape.png", "/absolute.png", "C:/drive.png", "origin\\s0.png", "origin/unregistered.png",
                                  "student/m/model.py", "metrics.json", "report.pdf", "bundle.zip",
                                  "duplicate", "symlink", "device", "directory", "nul", "bad_zip", "header_mismatch"])
@pytest.mark.parametrize("kind", ["compare", "demo"])
def test_zip_all_download_routes_reject_unsafe_members(lab, bad, kind):
    task = result_task(lab, kind)
    root = lab.tmp / "tasks" / task.id
    if bad == "bad_zip": (root / "bundle.zip").write_bytes(b"invalid zip")
    else:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)  # deliberately duplicated ZIP name
            with zipfile.ZipFile(root / "bundle.zip", "w") as archive:
                archive.writestr("task.json", "{}")
                archive.writestr("origin/s0.png", b"fixture")
                if bad in {"symlink", "device", "directory"}:
                    info = zipfile.ZipInfo("montage/s0__mask.png")
                    info.create_system = 3
                    info.external_attr = ((stat.S_IFLNK if bad == "symlink" else stat.S_IFCHR) | 0o777) << 16
                    if bad == "directory": info.external_attr = 0x10
                    register(lab, task, "montage/s0__mask.png", "montage")
                    archive.writestr(info, "target")
                elif bad != "header_mismatch":
                    archive.writestr("origin/s0.png" if bad == "duplicate" else bad, b"bad")
        if bad == "nul":
            # Keep a NUL in the central-directory name; ZipInfo normally truncates it on creation.
            data = (root / "bundle.zip").read_bytes().replace(b"nul", b"n\x00l")
            (root / "bundle.zip").write_bytes(data)
        if bad == "header_mismatch":
            data = (root / "bundle.zip").read_bytes().replace(b"origin/s0.png", b"../escape.png", 1)
            (root / "bundle.zip").write_bytes(data)
    before = (root / "bundle.zip").read_bytes()
    with client(lab, lab.owner) as http:
        for prefix in (["/api/tasks", "/api/demo/tasks"] if kind == "demo" else ["/api/tasks"]):
            for suffix in ("/bundle", "/file/bundle.zip"):
                response = http.get(f"{prefix}/{task.id}{suffix}")
                assert response.status_code == 404
                assert str(lab.tmp) not in response.text
            payload = http.get(f"{prefix}/{task.id}").json()
            assert not payload["bundle_ready"] and payload["bundle_unavailable_reason"]
            assert not any(a["kind"] == "bundle" for a in payload["artifacts"])
    assert not records.serialize_record(lab.db, task, lab.owner)["bundle_ready"]
    assert not dashboard._task_payload(task, lab.db)["bundle_ready"]
    assert before == (root / "bundle.zip").read_bytes()  # no repair on download


@pytest.mark.parametrize("case", ["missing_record", "duplicate_record", "wrong_kind", "missing_file"])
def test_bundle_record_required(lab, case):
    task = result_task(lab)
    row = lab.db.query(Artifact).filter_by(task_id=task.id, rel_path="bundle.zip").one()
    if case == "missing_record": lab.db.delete(row)
    elif case == "wrong_kind": row.kind = "log"
    elif case == "duplicate_record":
        lab.db.add(Artifact(id=new_id(), task_id=task.id, rel_path="bundle.zip", kind="bundle"))
    else: (lab.tmp / "tasks" / task.id / "bundle.zip").unlink()
    lab.db.commit()
    with client(lab, lab.owner) as http:
        for suffix in ("/bundle", "/file/bundle.zip"):
            assert http.get(f"/api/tasks/{task.id}{suffix}").status_code == 404


def test_bundle_uses_flushed_registry_not_directory_scan(lab):
    task = result_task(lab)
    root = lab.tmp / "tasks" / task.id
    pending = register(lab, task, f"pred/{lab.builtin.id}/s0.png", "pred_color", model=lab.builtin.id, flush=False)
    for name in ("student/m/model.py", "student/m/weights.pth", "student/m/manifest.json", "student/m/input.npy",
                 "student/m/result.json", "metrics.json", "origin/unregistered.png", "montage/report.pdf"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"never publish")
    write_bundle(lab.db, task, lab.settings)
    with zipfile.ZipFile(policy(lab, task).file("bundle.zip")) as archive:
        assert set(archive.namelist()) == {"task.json", "origin/s0.png", pending.rel_path}


@pytest.mark.parametrize("corruption", ["gt_artifact", "has_gt", "student_model", "sample_mask"])
def test_demo_policy_cannot_be_bypassed_by_tasks_route(lab, corruption):
    task = result_task(lab, "demo")
    if corruption == "has_gt": task.has_gt = True
    if corruption == "student_model":
        lab.db.query(TaskModel).filter_by(task_id=task.id).one().model_version_id = lab.mine.id
    if corruption == "sample_mask":
        lab.db.query(Sample).filter_by(version_id=lab.batch.id).one().mask_uri = "data:synthetic-mask.png"
    register(lab, task, "gt/s0.png", "gt")
    lab.db.commit()
    with client(lab, lab.owner) as http:
        for prefix in ("/api/tasks", "/api/demo/tasks"):
            assert http.get(f"{prefix}/{task.id}/file/gt/s0.png").status_code == 404
            if corruption != "gt_artifact":
                assert http.get(f"{prefix}/{task.id}/file/origin/s0.png").status_code == 404
                assert http.get(f"{prefix}/{task.id}/bundle").status_code == 404
        assert http.get(f"/api/tasks/{task.id}/metrics").json()["code"] == "DEMO_NO_METRICS"
    assert lab.db.query(MetricSet).count() == 0


def test_partial_model_and_eval_preview_subset_do_not_require_all_outputs(lab):
    task = result_task(lab, "eval")
    task.status = "partial_success"
    lab.db.add(TaskModel(id=new_id(), task_id=task.id, model_version_id=lab.shared.id,
                         role="student_under_test", status="failed", sort_order=1))
    lab.db.commit()
    # 20 sample links, only s0 has preview; CAM and failed model outputs absent.
    assert len(task.samples) == 20
    write_bundle(lab.db, task, lab.settings)
    assert policy(lab, task).bundle_state()["bundle_ready"]
    assert tasks.serialize_task(lab.db, task)["preview_sample_keys"] == ["s0"]


def test_metrics_api_survives_but_metrics_file_is_never_downloadable(lab):
    task = result_task(lab)
    register(lab, task, "metrics.json", "log", sample=None)
    with client(lab, lab.owner) as http:
        assert http.get(f"/api/tasks/{task.id}/metrics").json()["available"] is False
        assert http.get(f"/api/tasks/{task.id}/file/metrics.json").status_code == 404
    pair_gt(lab, task)
    lab.db.add(MetricSet(id=new_id(), task_id=task.id, scope="batch_reference", n=1,
                         payload_json={"models": [], "n": 1}))
    lab.db.commit()
    lab.db.expire_all()
    with client(lab, lab.owner) as http:
        assert http.get(f"/api/tasks/{task.id}/metrics").json()["available"] is True
        assert http.get(f"/api/tasks/{task.id}/file/metrics.json").status_code == 404


def test_worker_demo_orchestration_never_scores(lab, monkeypatch):
    import numpy as np
    task_id = create(lab).json()["id"]
    task = lab.db.get(Task, task_id)
    task.type = "demo"
    lab.db.commit()
    frozen = lab.tmp / "tasks" / task_id / "inputs.json"
    payload = json.loads(frozen.read_text(encoding="utf-8"))
    payload["task_type"] = "demo"
    frozen.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(jobs, "read_rgb", lambda p: np.zeros((200, 200, 3), dtype=np.uint8))
    monkeypatch.setattr(jobs, "preprocess_rgb", lambda *a: object())
    monkeypatch.setattr(jobs, "get_builtin_module", lambda *a, **k: object())
    monkeypatch.setattr(jobs, "predict_mask", lambda *a, **k: np.zeros((200, 200), dtype=np.uint8))
    monkeypatch.setattr(jobs, "_try_write_cam", lambda **k: {})
    spies = []
    for name in ("read_index_mask", "empty_confmat", "add_to_confmat", "_upsert_metric_set", "infer_student_masks"):
        spy = Mock(side_effect=AssertionError("demo must not reach GT/scoring/student executor"))
        monkeypatch.setattr(jobs, name, spy)
        spies.append(spy)
    jobs.run_demo(task_id)
    lab.db.expire_all()
    task = lab.db.get(Task, task_id)
    assert task.status == "success"
    assert lab.db.query(MetricSet).count() == 0
    assert not (lab.tmp / "tasks" / task_id / "metrics.json").exists()
    with zipfile.ZipFile(policy(lab, task).file("bundle.zip")) as archive:
        assert not any(n.startswith(("gt/", "error/", "student/")) or n == "metrics.json" for n in archive.namelist())
    payload = demo.serialize_demo_task(lab.db, task)
    assert "metrics" not in payload and "has_gt" not in payload
    for spy in spies: spy.assert_not_called()


@pytest.mark.parametrize("kind", ["compare", "eval"])
@pytest.mark.parametrize("actor", ["peer", "advisor"])
@pytest.mark.parametrize("suffix", ["/bundle", "/file/bundle.zip", "/file/origin/s0.png"])
def test_task_authorization_precedes_artifact_lookup(lab, monkeypatch, kind, actor, suffix):
    task = result_task(lab, kind)
    spy = Mock(side_effect=AssertionError("unauthorized task must not examine files"))
    monkeypatch.setattr(task_artifacts.TaskArtifacts, "__init__", spy)
    with client(lab, getattr(lab, actor)) as http:
        assert http.get(f"/api/tasks/{task.id}{suffix}").status_code == 404
    spy.assert_not_called()


@pytest.mark.parametrize("target", ["file", "folder", "task_root", "tasks_root"])
def test_link_guard_without_os_link_privileges(lab, monkeypatch, target):
    task = result_task(lab)
    root = lab.tmp / "tasks" / task.id
    linked = {"file": root / "origin/s0.png", "folder": root / "origin", "task_root": root, "tasks_root": root.parent}[target]
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda p: p == linked or original(p))
    with pytest.raises(AppError):
        policy(lab, task).file("origin/s0.png")
    with pytest.raises(AppError):
        write_bundle(lab.db, task, lab.settings)


def test_root_escape_resolve_guard(lab, monkeypatch):
    task = result_task(lab)
    policy_obj = policy(lab, task)
    original = Path.resolve
    file = policy_obj.root / "origin/s0.png"
    monkeypatch.setattr(Path, "resolve", lambda p, *a, **k: lab.tmp / "outside.png" if p == file else original(p, *a, **k))
    with pytest.raises(AppError):
        policy_obj.file("origin/s0.png")


def test_fixed_gt_historical_zip_rejected_without_rewriting(lab):
    task = result_task(lab, "eval")
    register(lab, task, "montage/s0__mask.png", "montage")
    root = lab.tmp / "tasks" / task.id
    with zipfile.ZipFile(root / "bundle.zip", "a") as archive:
        archive.write(root / "montage/s0__mask.png", "montage/s0__mask.png")
    before = (root / "bundle.zip").read_bytes()
    with pytest.raises(AppError):
        policy(lab, task).file("bundle.zip")
    assert (root / "bundle.zip").read_bytes() == before
