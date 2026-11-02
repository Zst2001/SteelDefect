"""PCB API and task boundaries; isolated SQLite, synthetic images, fake compute/queue."""
import io
import sys
from types import SimpleNamespace
from unittest.mock import Mock

if "app.config" not in sys.modules or sys.modules["app.config"].Settings.__name__ != "OfflineSettings":
    raise RuntimeError("Use tests/run_phase_a_tests.py with its isolation bootstrap")

import numpy as np
import pytest
from PIL import Image
from app.db.models import Artifact, DatasetVersion, MetricSet, PreprocessSpecRow, Sample, Task, TaskModel, Weight
from app.errors import AppError
from app.routers import pcb_segmentation as router
from app.services import pcb_segmentation as service
from app.services.dispatch import Delivery
from app.services.input_freeze import verify_inputs
from app.services.records import submit_to_advisor, withdraw_from_advisor, rerun_record
from apps.worker import jobs, pcb_segmentation as worker
from infer.pcb.runtime import MODELS
from test_phase_a_authorization import lab, client

_REAL_PCB_COMPUTE = worker.compute
_REAL_PCB_ASSET = service.asset


def file(mode="RGB", size=(220, 220), value=80, fmt="PNG", name="image.png", exif=None):
    stream = io.BytesIO()
    options = {"exif": exif} if exif is not None else {}
    Image.new(mode, size, value).save(stream, format=fmt, **options)
    return name, stream.getvalue()


def fake_compute(model_id, image, include_cam, root):
    pred = np.zeros((220, 220), np.uint8)
    pred[10:20, 10:20] = 1
    rgb = np.zeros((220, 220, 3), np.uint8)
    layers = {"pred_mask": pred, "probability": pred.astype(np.float32),
              "probability_heatmap": rgb, "overlay": image, "boundary": rgb}
    if include_cam:
        layers["cam"] = rgb
    return layers, {"status": "ok" if include_cam else "not_requested", "layer": MODELS[model_id][2]}


@pytest.fixture
def pcb(lab, monkeypatch):
    object.__setattr__(lab.settings, "pcb_segmentation_enabled", True)
    object.__setattr__(lab.settings, "pcb_job_timeout_sec", 120)
    def asset(slug, settings):
        if slug not in MODELS:
            raise AppError("PCB 模型不支持", code="PCB_MODEL_UNSUPPORTED", stage="protocol", status_code=400)
        return {"slug": slug, "name": slug, "available": True, "weight_sha256": MODELS[slug][0],
                "param_count": MODELS[slug][1], "protocol_hash": "a" * 64, "deployment_source_hash": "d" * 64}
    monkeypatch.setattr(service, "asset", asset)
    monkeypatch.setattr(worker, "asset", asset)
    monkeypatch.setattr(service, "get_settings", lambda: lab.settings)
    monkeypatch.setattr(service, "invalidate_after_write", lambda *a: None)
    monkeypatch.setattr(worker, "invalidate_after_write", lambda *a: None)
    monkeypatch.setattr(worker, "compute", fake_compute)
    queue = Mock(side_effect=lambda _s, _f, ident, _timeout, **kw: Delivery("confirmed", "task-" + ident))
    monkeypatch.setattr(service, "enqueue", queue)
    return SimpleNamespace(lab=lab, queue=queue)


def create(pcb, *, gt=False, model="unet", cam=False, key=None):
    lab = pcb.lab
    batch = service.create_batch(lab.db, lab.owner, file(), file(mode="L", value=255, name="gt.png") if gt else None, lab.settings)
    task = service.create_pcb_task(lab.db, lab.owner, batch_id=batch["batch_id"], model_id=model,
                                   include_cam=cam, idempotency_key=key, settings=lab.settings)
    return batch, task


@pytest.mark.parametrize("model", list(MODELS))
@pytest.mark.parametrize("gt,cam", [(False, False), (True, True)])
def test_pcb_worker_http_artifacts_metrics(pcb, model, gt, cam):
    lab = pcb.lab
    batch, task = create(pcb, gt=gt, model=model, cam=cam)
    jobs.run_pcb_segmentation(task.id)
    lab.db.expire_all()
    with client(lab, lab.owner) as http:
        data = http.get(f"/api/tasks/{task.id}").json()
        assert data["status"] == "success", data
        assert data["scene"] == "pcb" and data["task_kind"] == "segmentation"
        assert data["metrics"]["available"] is gt and data["include_cam"] is cam
        assert lab.db.query(MetricSet).filter_by(task_id=task.id).count() == int(gt)
        kinds = {a["kind"] for a in data["artifacts"]}
        assert {"origin", "pred_mask", "mask_visual", "overlay", "boundary", "probability", "pcb_result"} <= kinds
        assert ("gt" in kinds) is gt and ("error" in kinds) is gt and ("cam" in kinds) is cam
        for row in data["artifacts"]:
            assert http.get(row["url"]).status_code == 200
        assert http.get(data["result_download_url"]).json()["weight_sha256"] == MODELS[model][0]
        assert http.get(f"/api/tasks/{task.id}/file/inputs.json").status_code == 404
        assert http.get(f"/api/tasks/{task.id}/bundle").status_code == 404
        assert any(r["id"] == task.id for r in http.get("/api/records?type=pcb_segmentation").json()["items"])
    count = lab.db.query(Artifact).filter_by(task_id=task.id).count()
    jobs.run_pcb_segmentation(task.id)
    assert lab.db.query(Artifact).filter_by(task_id=task.id).count() == count


@pytest.mark.parametrize("image", [file(size=(219, 220)), file(mode="L"), file(mode="RGBA"),
    file(name="image.jpg"), file(fmt="JPEG", name="image.png"), file(fmt="JPEG", name="image.jpg", mode="L"),
    file(fmt="JPEG", name="image.jpg", mode="CMYK"), file(fmt="JPEG", name="image.jpg", size=(220, 219)),
    file(fmt="BMP", name="image.bmp"), ("image.png", b""),
    ("image.png", b"x" * (service.MAX_IMAGE_BYTES + 1))])
def test_pcb_bad_inputs_leave_no_batch(pcb, image):
    count = pcb.lab.db.query(DatasetVersion).count()
    with pytest.raises(AppError):
        service.create_batch(pcb.lab.db, pcb.lab.owner, image, settings=pcb.lab.settings)
    assert pcb.lab.db.query(DatasetVersion).count() == count
    pcb.queue.assert_not_called()


@pytest.mark.parametrize("fmt,name", [("PNG", "image.png"), ("JPEG", "image.jpg")])
def test_pcb_exif_is_explicit(pcb, fmt, name):
    exif = Image.Exif()
    exif[274] = 6
    with pytest.raises(AppError, match="EXIF"):
        service.create_batch(pcb.lab.db, pcb.lab.owner, file(fmt=fmt, name=name, exif=exif), settings=pcb.lab.settings)
    exif[274] = 1
    batch = service.create_batch(pcb.lab.db, pcb.lab.owner, file(fmt=fmt, name=name, exif=exif), settings=pcb.lab.settings)
    assert batch["sample_count"] == 1


@pytest.mark.parametrize("gt", [file(mode="L", value=2), file(mode="RGB"), file(mode="L", size=(221, 220)),
                                file(mode="L", fmt="JPEG", name="gt.jpg")])
def test_pcb_invalid_gt(pcb, gt):
    with pytest.raises(AppError) as exc:
        service.create_batch(pcb.lab.db, pcb.lab.owner, file(), gt, pcb.lab.settings)
    assert exc.value.code == "PCB_BAD_GT"


def test_pcb_gt_normalization_and_original_bytes(pcb):
    lab = pcb.lab
    original = file()
    batch = service.create_batch(lab.db, lab.owner, original, file(mode="L", value=255), lab.settings)
    sample = lab.db.query(Sample).filter_by(version_id=batch["batch_id"]).one()
    from app.services.storage import resolve_uri
    assert resolve_uri(sample.origin_uri, lab.settings).read_bytes() == original[1]
    with Image.open(resolve_uri(sample.mask_uri, lab.settings)) as gt:
        assert set(np.unique(gt).tolist()) == {1}


def test_pcb_scope_and_idempotency_cam_conflict(pcb):
    lab = pcb.lab
    batch, task = create(pcb, key="same")
    kwargs = {"batch_id": batch["batch_id"], "model_id": "unet", "idempotency_key": "same", "settings": lab.settings}
    assert service.create_pcb_task(lab.db, lab.owner, **kwargs).id == task.id
    assert pcb.queue.call_count == 1
    with pytest.raises(AppError) as exc:
        service.create_pcb_task(lab.db, lab.owner, **kwargs, include_cam=True)
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"
    for user, batch_id, model in [(lab.peer, batch["batch_id"], "unet"), (lab.owner, lab.batch.id, "unet"),
                                   (lab.owner, batch["batch_id"], "mobilenet_v3_small")]:
        with pytest.raises(AppError):
            service.create_pcb_task(lab.db, user, batch_id=batch_id, model_id=model, settings=lab.settings)


@pytest.mark.parametrize("change", ["origin", "gt", "options", "model_hash", "protocol", "sample_shape"])
def test_pcb_frozen_inputs(pcb, change):
    lab = pcb.lab
    batch, task = create(pcb, gt=True)
    sample = lab.db.query(Sample).filter_by(version_id=batch["batch_id"]).one()
    if change in {"origin", "gt"}:
        from app.services.storage import resolve_uri
        resolve_uri(sample.origin_uri if change == "origin" else sample.mask_uri, lab.settings).write_bytes(b"changed")
    elif change == "options":
        row = lab.db.get(PreprocessSpecRow, task.preprocess_id)
        row.extra_json = {**row.extra_json, "include_cam": True}
    elif change == "model_hash":
        link = lab.db.query(TaskModel).filter_by(task_id=task.id).one()
        lab.db.query(Weight).filter_by(version_id=link.model_version_id).one().sha256 = "b" * 64
    elif change == "protocol":
        version = lab.db.get(DatasetVersion, batch["batch_id"])
        version.class_map_json = {**version.class_map_json, "scene": "steel"}
    else:
        sample.width = 200
    lab.db.commit()
    with pytest.raises(AppError):
        verify_inputs(lab.db, task, lab.settings)


@pytest.mark.parametrize("status", ["unavailable", "failed"])
def test_pcb_cam_optional_failure_does_not_fail_task(pcb, monkeypatch, status):
    def compute(*args):
        layers, _ = fake_compute(*args)
        layers.pop("cam", None)
        return layers, {"status": status, "reason": "预测前景为空" if status == "unavailable" else "测试 CAM 故障"}
    monkeypatch.setattr(worker, "compute", compute)
    _, task = create(pcb, cam=True)
    jobs.run_pcb_segmentation(task.id)
    pcb.lab.db.expire_all()
    data = service.serialize_pcb_task(pcb.lab.db, pcb.lab.db.get(Task, task.id), pcb.lab.settings)
    assert data["status"] == "success" and data["cam"]["status"] == status
    assert not any(a["kind"] == "cam" for a in data["artifacts"])


@pytest.mark.parametrize("timeout", [False, True])
def test_pcb_cam_exception_respects_whole_task_deadline(pcb, monkeypatch, timeout):
    import torch
    from rq.timeouts import JobTimeoutException
    from infer.pcb import runtime, visualize
    from infer.pcb.catalog import INTEROP
    lab = pcb.lab
    monkeypatch.setattr(worker, "compute", _REAL_PCB_COMPUTE)
    monkeypatch.setattr(torch, "get_num_interop_threads", lambda: INTEROP)
    monkeypatch.setattr(runtime, "load_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(visualize, "predict_layers", lambda _model, image: fake_compute("unet", image, False, None)[0])
    class FailingCAM:
        def __init__(self, _model): pass
        def __call__(self, _image):
            if timeout:
                raise JobTimeoutException("synthetic whole-job deadline during CAM")
            raise RuntimeError("synthetic optional CAM failure")
    monkeypatch.setattr(visualize, "SegmentationGradCAM", FailingCAM)
    _, task = create(pcb, gt=True, cam=True)
    if timeout:
        with pytest.raises(AppError) as exc:
            jobs.run_pcb_segmentation(task.id)
        assert exc.value.code == "PCB_JOB_TIMEOUT" and exc.value.stage == "resource"
    else:
        jobs.run_pcb_segmentation(task.id)
    lab.db.expire_all()
    current = lab.db.get(Task, task.id)
    if timeout:
        assert current.status == "failed" and "PCB_JOB_TIMEOUT" in current.error_summary
        assert all(link.status == "failed" and link.fail_stage == "resource" for link in current.models)
        assert lab.db.query(Artifact).filter_by(task_id=task.id).count() == 0
        assert lab.db.query(MetricSet).filter_by(task_id=task.id).count() == 0
        task_root = lab.settings.storage_path / "tasks" / task.id
        assert sorted(p.name for p in task_root.iterdir()) == ["inputs.json"]
    else:
        assert current.status == "success"
        assert lab.db.query(MetricSet).filter_by(task_id=task.id).count() == 1
        assert lab.db.query(Artifact).filter_by(task_id=task.id, kind="cam").count() == 0
        result = service.serialize_pcb_task(lab.db, current, lab.settings)
        assert result["cam"]["status"] == "failed" and result["metrics"]["available"]


def test_pcb_admission_deadline_is_not_an_asset_failure(pcb, monkeypatch):
    from rq.timeouts import JobTimeoutException
    from infer.pcb import catalog
    deadline = JobTimeoutException("synthetic deadline during staging digest")
    staging = Mock(side_effect=deadline)
    monkeypatch.setattr(catalog, "verify_staging", staging)
    with pytest.raises(JobTimeoutException) as exc:
        _REAL_PCB_ASSET("unet", pcb.lab.settings)
    assert exc.value is deadline
    staging.assert_called_once_with(service.asset_root(pcb.lab.settings))


@pytest.mark.parametrize("admission_error", [False, True])
def test_pcb_real_asset_failures_remain_closed_over_http(pcb, monkeypatch, admission_error):
    from infer.pcb import catalog
    lab = pcb.lab
    batch = service.create_batch(lab.db, lab.owner, file(), settings=lab.settings)
    private_message = "synthetic-private-staging-path-must-not-be-returned"
    error = catalog.PcbAdmissionError(private_message) if admission_error else RuntimeError(private_message)
    monkeypatch.setattr(catalog, "verify_staging", Mock(side_effect=error))
    monkeypatch.setattr(service, "asset", _REAL_PCB_ASSET)
    with client(lab, lab.owner) as http:
        http.app.include_router(router.router, prefix="/api")
        response = http.post("/api/scenes/pcb/segmentation/tasks", json={"batch_id": batch["batch_id"], "model_id": "unet"})
        assert response.status_code == 409
        assert response.json() == {"stage": "load", "code": "PCB_ASSET_UNAVAILABLE", "message": "PCB 三模型准入或资产校验未通过"}
        assert private_message not in response.text
    assert lab.db.query(Task).filter_by(type="pcb_segmentation").count() == 0
    pcb.queue.assert_not_called()


@pytest.mark.parametrize("gate", [1, 2, 3], ids=["before-running", "body-entry", "before-publish"])
def test_pcb_admission_deadline_records_timeout_and_cleans_outputs(pcb, monkeypatch, gate):
    from rq.timeouts import JobTimeoutException
    from infer.pcb import catalog
    lab = pcb.lab
    _, task = create(pcb, gt=True, cam=True)
    allowed_asset = worker.asset
    calls = 0
    deadline = JobTimeoutException("synthetic deadline during staging digest")
    staging = Mock(side_effect=deadline)
    monkeypatch.setattr(catalog, "verify_staging", staging)
    def gated_asset(*args):
        nonlocal calls
        calls += 1
        # Earlier gates use the isolated registered fixture. At the target gate,
        # exercise the real asset -> catalog -> require_admitted -> staging path.
        return _REAL_PCB_ASSET(*args) if calls == gate else allowed_asset(*args)
    monkeypatch.setattr(worker, "asset", gated_asset)
    with pytest.raises(AppError) as exc:
        jobs.run_pcb_segmentation(task.id)
    assert exc.value.code == "PCB_JOB_TIMEOUT" and exc.value.stage == "resource"
    assert exc.value.__cause__ is deadline
    assert calls == gate
    staging.assert_called_once_with(service.asset_root(lab.settings))
    lab.db.expire_all()
    current = lab.db.get(Task, task.id)
    assert current.status == "failed" and current.error_summary.startswith("PCB_JOB_TIMEOUT:")
    assert "PCB_ASSET_UNAVAILABLE" not in current.error_summary
    assert all(link.status == "failed" and link.fail_stage == "resource" for link in current.models)
    assert lab.db.query(Artifact).filter_by(task_id=task.id).count() == 0
    assert lab.db.query(MetricSet).filter_by(task_id=task.id).count() == 0
    assert sorted(p.name for p in (lab.settings.storage_path / "tasks" / task.id).iterdir()) == ["inputs.json"]
    with client(lab, lab.owner) as http:
        response = http.get(f"/api/tasks/{task.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed" and "PCB_JOB_TIMEOUT" in data["error_summary"]
        assert data["metrics"] == {"available": False} and data["artifacts"] == []


def test_pcb_revoke_during_compute_never_publishes(pcb, monkeypatch):
    lab = pcb.lab
    def compute(*args):
        lab.owner.status = "disabled"
        lab.db.commit()
        return fake_compute(*args)
    monkeypatch.setattr(worker, "compute", compute)
    _, task = create(pcb)
    with pytest.raises(AppError):
        jobs.run_pcb_segmentation(task.id)
    lab.db.expire_all()
    assert lab.db.get(Task, task.id).status == "failed"
    assert lab.db.query(Artifact).filter_by(task_id=task.id).count() == 0
    assert list((lab.settings.storage_path / "tasks" / task.id).iterdir()) == [lab.settings.storage_path / "tasks" / task.id / "inputs.json"]


def test_pcb_publication_failure_cleans_files(pcb, monkeypatch):
    lab = pcb.lab
    original = worker.os.replace
    count = 0
    def replace(*args):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("synthetic disk failure")
        return original(*args)
    monkeypatch.setattr(worker.os, "replace", replace)
    _, task = create(pcb)
    with pytest.raises(AppError):
        jobs.run_pcb_segmentation(task.id)
    lab.db.expire_all()
    assert lab.db.get(Task, task.id).status == "failed"
    assert lab.db.query(Artifact).filter_by(task_id=task.id).count() == 0
    assert not list((lab.settings.storage_path / "tasks" / task.id).rglob("*.png"))
    assert not list((lab.settings.storage_path / "tasks" / task.id).glob("pcb-stage-*"))


def test_pcb_partial_staging_write_is_removed(pcb, monkeypatch):
    lab = pcb.lab
    _, task = create(pcb)
    save = Image.Image.save
    def failed_save(self, target, *args, **kwargs):
        if "pcb-stage-" in str(target):
            from pathlib import Path
            Path(target).write_bytes(b"partial")
            raise OSError("synthetic partial write")
        return save(self, target, *args, **kwargs)
    monkeypatch.setattr(Image.Image, "save", failed_save)
    with pytest.raises(AppError):
        jobs.run_pcb_segmentation(task.id)
    lab.db.expire_all()
    assert lab.db.get(Task, task.id).status == "failed"
    assert not list((lab.settings.storage_path / "tasks" / task.id).rglob("*.png"))
    assert not list((lab.settings.storage_path / "tasks" / task.id).glob("pcb-stage-*"))


def test_pcb_compute_does_not_hold_authorization_transaction(pcb, monkeypatch):
    _, task = create(pcb)
    def compute(*args):
        # _run_task uses a separate Session from the test's API fixture.
        active = current_session[0]
        assert not active.in_transaction()
        return fake_compute(*args)
    current_session = []
    factory = jobs.SessionLocal
    def session():
        db = factory()
        current_session.append(db)
        return db
    monkeypatch.setattr(jobs, "SessionLocal", session)
    monkeypatch.setattr(worker, "compute", compute)
    jobs.run_pcb_segmentation(task.id)


@pytest.mark.parametrize("which", ["origin", "gt"])
def test_pcb_consumed_bytes_match_frozen_hash(pcb, monkeypatch, which):
    from pathlib import Path
    from app.services.storage import resolve_uri
    lab = pcb.lab
    batch, task = create(pcb, gt=True)
    sample = lab.db.query(Sample).filter_by(version_id=batch["batch_id"]).one()
    target = resolve_uri(sample.origin_uri if which == "origin" else sample.mask_uri, lab.settings)
    armed = [False]
    original_verify = worker.verify_inputs
    def verify(*args):
        result = original_verify(*args)
        armed[0] = True
        return result
    original_open = Path.open
    def transient_read(path, *args, **kwargs):
        if path == target and armed[0] and args and args[0] == "rb":
            armed[0] = False
            return io.BytesIO(file(mode="RGB" if which == "origin" else "L", value=0)[1])
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(worker, "verify_inputs", verify)
    monkeypatch.setattr(Path, "open", transient_read)
    with pytest.raises(AppError) as exc:
        jobs.run_pcb_segmentation(task.id)
    assert exc.value.code == "INPUT_CHANGED"
    assert lab.db.query(Artifact).filter_by(task_id=task.id).count() == 0


def test_pcb_permissions_sharing_rerun(pcb):
    lab = pcb.lab
    _, task = create(pcb, gt=True, cam=True)
    jobs.run_pcb_segmentation(task.id)
    lab.db.expire_all()
    task = lab.db.get(Task, task.id)
    for actor in (lab.peer, lab.advisor):
        with client(lab, actor) as http:
            for suffix in ("", "/metrics", "/file/gt/image.png", "/file/pcb.json"):
                assert http.get(f"/api/tasks/{task.id}{suffix}").status_code == 404
    submit_to_advisor(lab.db, lab.owner, task.id)
    with client(lab, lab.advisor) as http:
        assert http.get(f"/api/tasks/{task.id}/file/gt/image.png").status_code == 200
    withdraw_from_advisor(lab.db, lab.owner, task.id)
    with client(lab, lab.advisor) as http:
        assert http.get(f"/api/tasks/{task.id}/file/gt/image.png").status_code == 404
    new = rerun_record(lab.db, lab.owner, task.id)
    assert new.id != task.id and service.task_include_cam(lab.db, new) is True


def test_pcb_legacy_dataset_paths_cannot_bypass_task_permissions(pcb):
    from app.routers import datasets as datasets_router
    lab = pcb.lab
    batch, task = create(pcb, gt=True)
    jobs.run_pcb_segmentation(task.id)
    version = lab.db.get(DatasetVersion, batch["batch_id"])
    for actor in (lab.owner, lab.peer, lab.advisor):
        with client(lab, actor) as http:
            http.app.include_router(datasets_router.router, prefix="/api")
            for path in (f"/api/datasets/{version.dataset_id}",
                         f"/api/datasets/{version.dataset_id}/gt/image",
                         f"/api/datasets/{version.dataset_id}/versions/{version.id}/samples/image/preview"):
                assert http.get(path).status_code == 404, path
            response = http.get("/api/datasets").json()
            assert version.dataset_id not in {row["id"] for row in response["items"]}


def test_pcb_cannot_enter_steel_selector_perf_assistant_or_worker(pcb):
    from app.db.models import Model, ModelVersion
    from app.services import assistant, models, perf, tasks
    lab = pcb.lab
    _, task = create(pcb)
    link = lab.db.query(TaskModel).filter_by(task_id=task.id).one()
    mv = lab.db.get(ModelVersion, link.model_version_id)
    assert mv.id not in {row["id"] for row in models.list_visible_versions(lab.db, lab.owner)}
    for action in (
        lambda: perf.request_measure(lab.db, mv, lab.db.get(Model, mv.model_id)),
        lambda: assistant._visible_version(lab.db, mv.id, lab.owner),
        lambda: tasks.create_compare_task(lab.db, lab.owner, batch_id=lab.batch.id,
                                         baseline_version_ids=[mv.id], student_version_id=None),
        lambda: tasks.create_eval_task(lab.db, lab.owner, dataset_version_id=lab.evaluation.id,
                                      baseline_version_ids=[mv.id], student_version_id=None),
    ):
        with pytest.raises(AppError):
            action()
        lab.db.rollback()
    # Even manually corrupted rows are rejected at Worker claim before execution.
    task = lab.db.get(Task, task.id)
    task.type = "compare"
    lab.db.commit()
    with pytest.raises(AppError) as exc:
        jobs.run_compare(task.id)
    assert exc.value.code == "TASK_KIND_MISMATCH"


def test_pcb_upload_http_disabled_and_contract(pcb):
    lab = pcb.lab
    with client(lab, lab.owner) as http:
        http.app.include_router(router.router, prefix="/api")
        response = http.post("/api/scenes/pcb/segmentation/uploads", files={"file": (*file(), "image/png")})
        assert response.status_code == 200, response.text
        batch = response.json()
        duplicate = http.post("/api/scenes/pcb/segmentation/uploads", files=[("file", (*file(), "image/png")), ("file", (*file(), "image/png"))])
        assert duplicate.status_code == 400 and duplicate.json()["code"] == "PCB_IMAGE_COUNT"
        response = http.post("/api/scenes/pcb/segmentation/tasks", json={"batch_id": batch["batch_id"], "model_id": "unet", "include_cam": "true"})
        assert response.status_code == 422
        object.__setattr__(lab.settings, "pcb_segmentation_enabled", False)
        response = http.post("/api/scenes/pcb/segmentation/uploads", files={"file": (*file(), "image/png")})
        assert response.status_code == 409 and response.json()["code"] == "PCB_DISABLED"


def test_pcb_routes_require_real_auth_dependency(pcb):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.deps import get_db
    from app.errors import app_error_handler
    app = FastAPI()
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(router.router, prefix="/api")
    def database():
        yield pcb.lab.db
    app.dependency_overrides[get_db] = database
    with TestClient(app) as http:
        for response in (
            http.get("/api/scenes/pcb/segmentation/models"),
            http.post("/api/scenes/pcb/segmentation/uploads", files={"file": (*file(), "image/png")}),
            http.post("/api/scenes/pcb/segmentation/tasks", json={"batch_id": "unknown", "model_id": "unet"}),
        ):
            assert response.status_code == 401 and response.json()["code"] == "UNAUTHENTICATED"


def test_pcb_corrupt_registry_rejects_submission(pcb):
    lab = pcb.lab
    batch, task = create(pcb)
    link = lab.db.query(TaskModel).filter_by(task_id=task.id).one()
    lab.db.query(Weight).filter_by(version_id=link.model_version_id).one().sha256 = "f" * 64
    lab.db.commit()
    with pytest.raises(AppError) as exc:
        service.create_pcb_task(lab.db, lab.owner, batch_id=batch["batch_id"], model_id="unet", settings=lab.settings)
    assert exc.value.code == "PCB_MODEL_CHANGED"
    assert pcb.queue.call_count == 1


@pytest.mark.parametrize("state", ["rejected", "unknown"])
def test_pcb_delivery_states(pcb, state):
    pcb.queue.side_effect = lambda _s, _f, ident, _timeout, **kw: Delivery(state, "task-" + ident)
    _, task = create(pcb)
    assert task.status == ("failed" if state == "rejected" else "queued")
    assert ("QUEUE_REJECTED" if state == "rejected" else "QUEUE_UNKNOWN") in task.error_summary


def test_pcb_metrics_zero_denominator_is_not_fake_accuracy():
    zero = np.zeros((220, 220), np.uint8)
    data = worker.metrics(zero, zero)
    assert data["available"] and all(data[key] is None for key in ("defect_dice", "iou", "precision", "recall"))


@pytest.mark.parametrize("timeout", [True, False])
def test_pcb_unclaimed_failure_reconciles_safely(pcb, monkeypatch, timeout):
    from app.db.models import AuditLog
    from app.services import pcb_delivery
    from rq.timeouts import JobTimeoutException
    lab = pcb.lab
    _, task = create(pcb)
    monkeypatch.setattr(pcb_delivery, "SessionLocal", lab.factory)
    monkeypatch.setattr(pcb_delivery, "invalidate_after_write", lambda *args: None)
    job = SimpleNamespace(id="task-" + task.id, func_name=pcb_delivery.FUNCTION, args=(task.id,), kwargs={})
    exc_type = JobTimeoutException if timeout else RuntimeError
    pcb_delivery.reconcile_unclaimed_failure(job, None, exc_type, exc_type("sensitive path must not be exposed"), None)
    lab.db.expire_all()
    current = lab.db.get(Task, task.id)
    assert current.status == "failed"
    assert ("PCB_JOB_TIMEOUT" if timeout else "PCB_JOB_START_FAILED") in current.error_summary
    assert "sensitive" not in current.error_summary
    assert all(link.status == "failed" for link in current.models)
    assert lab.db.query(AuditLog).filter_by(action="pcb.dispatch_failure", target_id=task.id).count() == 1
    pcb_delivery.reconcile_unclaimed_failure(job, None, exc_type, None, None)
    assert lab.db.query(AuditLog).filter_by(action="pcb.dispatch_failure", target_id=task.id).count() == 1


@pytest.mark.parametrize("change", ["wrong_function", "wrong_job_id", "wrong_args", "kwargs", "bad_uuid", "wrong_task_type",
                                    "running", "success", "partial_success", "failed"])
def test_pcb_failure_callback_cannot_overwrite_other_attempt(pcb, monkeypatch, change):
    from app.services import pcb_delivery
    from rq.timeouts import JobTimeoutException
    lab = pcb.lab
    _, task = create(pcb)
    monkeypatch.setattr(pcb_delivery, "SessionLocal", lab.factory)
    monkeypatch.setattr(pcb_delivery, "invalidate_after_write", lambda *args: None)
    job = SimpleNamespace(id="task-" + task.id, func_name=pcb_delivery.FUNCTION, args=(task.id,), kwargs={})
    if change == "wrong_function": job.func_name = "apps.worker.jobs.run_compare"
    elif change == "wrong_job_id": job.id = "redelivery-" + task.id
    elif change == "wrong_args": job.args = (task.id, "extra")
    elif change == "kwargs": job.kwargs = {"extra": True}
    elif change == "bad_uuid": job.args = ("../other",); job.id = "task-../other"
    elif change == "wrong_task_type": task.type = "compare"
    else: task.status = change
    task.error_summary = "keep existing diagnostic"
    lab.db.commit()
    expected = task.status
    pcb_delivery.reconcile_unclaimed_failure(job, None, JobTimeoutException, None, None)
    lab.db.expire_all()
    current = lab.db.get(Task, task.id)
    assert current.status == expected and current.error_summary == "keep existing diagnostic"


@pytest.mark.parametrize("with_callback", [False, True])
def test_pcb_dispatch_callback_is_opt_in_and_lazy(pcb, monkeypatch, with_callback):
    from app.services import dispatch, pcb_delivery
    from rq.job import Callback
    calls = []
    class Queue:
        def __init__(self, *args, **kwargs): pass
        def enqueue_call(self, *, unique=False): pass
        def enqueue(self, function, ident, **kwargs): calls.append(kwargs)
    monkeypatch.setattr(dispatch, "Queue", Queue)
    monkeypatch.setattr(dispatch, "rq_connection", lambda: SimpleNamespace(ping=lambda: True))
    options = {"on_failure": pcb_delivery.CALLBACK} if with_callback else {}
    outcome = dispatch.enqueue(pcb.lab.settings, "worker", "test", 120, job_id="task-test", **options)
    assert outcome.state == "confirmed" and len(calls) == 1
    assert ("on_failure" in calls[0]) is with_callback
    if with_callback:
        callback = calls[0]["on_failure"]
        assert isinstance(callback, Callback) and callback.name == pcb_delivery.CALLBACK and callback.timeout == 20


def test_pcb_submissions_bind_failure_callback(pcb):
    from app.services.pcb_delivery import CALLBACK
    create(pcb)
    assert pcb.queue.call_args.kwargs["on_failure"] == CALLBACK


@pytest.mark.parametrize("fmt,name,mime", [("PNG", "synthetic.png", "image/png"),
                                         ("JPEG", "synthetic.jpeg", "image/jpeg")])
def test_pcb_origin_format_bytes_mime_and_consumed_pixels(pcb, monkeypatch, fmt, name, mime):
    """Real image encoders and HTTP routes; compute/queue remain isolated fakes."""
    from app.services.storage import resolve_uri
    lab = pcb.lab
    yy, xx = np.indices((220, 220))
    pixels = np.stack((xx % 256, yy % 256, (xx + yy) % 256), axis=-1).astype(np.uint8)
    stream = io.BytesIO()
    exif = Image.Exif()
    exif[274] = 1
    Image.fromarray(pixels).save(stream, format=fmt, exif=exif)
    content = stream.getvalue()
    assert content.startswith(b"\xff\xd8\xff" if fmt == "JPEG" else b"\x89PNG\r\n\x1a\n")
    with Image.open(io.BytesIO(content)) as uploaded:
        assert uploaded.format == fmt and uploaded.mode == "RGB" and uploaded.size == (220, 220)
        expected = np.asarray(uploaded).copy()
    consumed = []
    def compute(model_id, image, include_cam, root):
        consumed.append(image.copy())
        return fake_compute(model_id, image, include_cam, root)
    monkeypatch.setattr(worker, "compute", compute)
    with client(lab, lab.owner) as http:
        http.app.include_router(router.router, prefix="/api")
        response = http.post("/api/scenes/pcb/segmentation/uploads", files={"file": (name, content, mime)})
        assert response.status_code == 200, response.text
        batch_id = response.json()["batch_id"]
        sample = lab.db.query(Sample).filter_by(version_id=batch_id).one()
        original = resolve_uri(sample.origin_uri, lab.settings)
        assert original.suffix == (".jpg" if fmt == "JPEG" else ".png")
        assert original.read_bytes() == content
        task = service.create_pcb_task(lab.db, lab.owner, batch_id=batch_id, model_id="unet", settings=lab.settings)
        jobs.run_pcb_segmentation(task.id)
        lab.db.expire_all()
        data = http.get(f"/api/tasks/{task.id}").json()
        row = next(a for a in data["artifacts"] if a["kind"] == "origin")
        assert row["rel_path"] == "origin/image.png" and row["url"].endswith("/origin/image.png")
        download = http.get(row["url"])
        assert download.status_code == 200 and download.headers["content-type"] == "image/png"
        assert download.content.startswith(b"\x89PNG\r\n\x1a\n")
        with Image.open(io.BytesIO(download.content)) as displayed:
            assert displayed.format == "PNG" and displayed.mode == "RGB" and displayed.size == (220, 220)
            np.testing.assert_array_equal(np.asarray(displayed), expected)
        assert len(consumed) == 1
        np.testing.assert_array_equal(consumed[0], expected)
        assert original.read_bytes() == content
    with client(lab, lab.peer) as http:
        assert http.get(row["url"]).status_code == 404


@pytest.mark.parametrize("foreground", [True, False])
def test_pcb_dual_mask_download_geometry_values_and_metrics(pcb, monkeypatch, foreground):
    lab = pcb.lab
    def compute(*args):
        layers, cam = fake_compute(*args)
        if not foreground:
            layers["pred_mask"][:] = 0
            layers["probability"][:] = 0
        return layers, cam
    monkeypatch.setattr(worker, "compute", compute)
    # Nonempty pair tests values and geometry; empty pair tests all null denominators.
    truth = np.zeros((220, 220), np.uint8)
    if foreground:
        truth[15:25, 15:25] = 255
    stream = io.BytesIO()
    Image.fromarray(truth).save(stream, format="PNG")
    batch = service.create_batch(lab.db, lab.owner, file(), ("gt.png", stream.getvalue()), lab.settings)
    task = service.create_pcb_task(lab.db, lab.owner, batch_id=batch["batch_id"], model_id="unet", settings=lab.settings)
    jobs.run_pcb_segmentation(task.id)
    lab.db.expire_all()
    with client(lab, lab.owner) as http:
        data = http.get(f"/api/tasks/{task.id}").json()
        rows = {row["kind"]: row for row in data["artifacts"]}
        arrays = {}
        for kind in ("pred_mask", "mask_visual", "gt"):
            response = http.get(rows[kind]["url"])
            assert response.status_code == 200 and response.headers["content-type"] == "image/png"
            assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
            with Image.open(io.BytesIO(response.content)) as mask:
                assert mask.format == "PNG" and mask.mode == "L" and mask.size == (220, 220)
                arrays[kind] = np.asarray(mask).copy()
        raw, visual, gt = (arrays[k] for k in ("pred_mask", "mask_visual", "gt"))
        assert raw.dtype == visual.dtype == np.uint8
        assert set(np.unique(raw)) == ({0, 1} if foreground else {0})
        assert set(np.unique(visual)) == ({0, 255} if foreground else {0})
        np.testing.assert_array_equal(raw == 1, visual == 255)
        positive, truth = raw == 1, gt == 1
        tp, fp = int((positive & truth).sum()), int((positive & ~truth).sum())
        fn, tn = int((~positive & truth).sum()), int((~positive & ~truth).sum())
        divide = lambda n, d: n / d if d else None
        expected = {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
                    "defect_dice": divide(2 * tp, 2 * tp + fp + fn), "iou": divide(tp, tp + fp + fn),
                    "precision": divide(tp, tp + fp), "recall": divide(tp, tp + fn)}
        result = http.get(data["result_download_url"]).json()
        stored = lab.db.query(MetricSet).filter_by(task_id=task.id).one().payload_json
        for key, value in expected.items():
            assert data["metrics"][key] == stored[key] == result["metrics"][key] == value
        assert result["foreground_pixels"] == int(positive.sum()) == (100 if foreground else 0)
        assert "255" in result["legend"]["mask_visual"]
    for actor in (lab.peer, lab.advisor):
        with client(lab, actor) as http:
            for kind in ("pred_mask", "mask_visual"):
                assert http.get(rows[kind]["url"]).status_code == 404


@pytest.mark.parametrize("change", ["model", "sample", "kind", "folder", "extension", "traversal", "unregistered"])
def test_pcb_visual_mask_allowlist_cannot_escape_contract(pcb, change):
    from app.services.task_artifacts import TaskArtifacts
    from app.util_time import new_id
    lab = pcb.lab
    _, task = create(pcb)
    jobs.run_pcb_segmentation(task.id)
    lab.db.expire_all()
    task = lab.db.get(Task, task.id)
    original = lab.db.query(Artifact).filter_by(task_id=task.id, kind="mask_visual").one()
    rel, mid, kind, key = original.rel_path, original.model_version_id, original.kind, original.sample_key
    if change == "model": mid = "other-model"; rel = f"mask_visual/{mid}/image.png"
    elif change == "sample": key = "other-image"
    elif change == "kind": kind = "pred_mask"
    elif change == "folder": rel = f"private/{mid}/image.png"
    elif change == "extension": rel = f"mask_visual/{mid}/image.jpg"
    elif change == "traversal": rel = f"mask_visual/{mid}/../../inputs.json"
    if change != "unregistered":
        lab.db.delete(original)
        lab.db.flush()
        row = Artifact(id=new_id(), task_id=task.id, kind=kind, rel_path=rel, sample_key=key, model_version_id=mid)
        lab.db.add(row)
    else:
        lab.db.delete(original)  # Real file remains, but registration is required.
    lab.db.commit()
    guard = TaskArtifacts(lab.db, task, lab.settings)
    with pytest.raises(AppError) as exc:
        guard.file(rel)
    assert exc.value.code == "ARTIFACT_UNAVAILABLE"
    with client(lab, lab.owner) as http:
        encoded = rel.replace("..", "%2e%2e")
        assert http.get(f"/api/tasks/{task.id}/file/{encoded}").status_code == 404


def test_pcb_history_without_visual_mask_stays_readable(pcb):
    lab = pcb.lab
    _, task = create(pcb, gt=True)
    jobs.run_pcb_segmentation(task.id)
    lab.db.expire_all()
    row = lab.db.query(Artifact).filter_by(task_id=task.id, kind="mask_visual").one()
    (lab.settings.storage_path / "tasks" / task.id / row.rel_path).unlink()
    lab.db.delete(row)
    lab.db.commit()
    with client(lab, lab.owner) as http:
        data = http.get(f"/api/tasks/{task.id}").json()
        assert data["status"] == "success" and data["metrics"]["available"]
        assert "mask_visual" not in {a["kind"] for a in data["artifacts"]}
        for row in data["artifacts"]:
            assert http.get(row["url"]).status_code == 200


def test_pcb_cancel_api_is_absent_and_requests_cannot_mutate_task(pcb):
    lab = pcb.lab
    _, task = create(pcb)
    with client(lab, lab.owner) as http:
        http.app.include_router(router.router, prefix="/api")
        paths = http.get("/openapi.json").json()["paths"]
        assert not any("cancel" in path for path in paths)
        for prefix in ("/api/tasks", "/api/scenes/pcb/segmentation/tasks"):
            response = http.post(f"{prefix}/{task.id}/cancel")
            assert response.status_code == 404 and response.json() == {"detail": "Not Found"}
        response = http.delete(f"/api/tasks/{task.id}")
        assert response.status_code == 405 and response.json() == {"detail": "Method Not Allowed"}
    lab.db.expire_all()
    assert lab.db.get(Task, task.id).status == "queued"
    assert lab.db.query(Artifact).filter_by(task_id=task.id).count() == 0
    assert pcb.queue.call_count == 1
