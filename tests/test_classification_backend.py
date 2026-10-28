"""Classification integration with synthetic images, assets, queue and predictor only."""
from __future__ import annotations

import io
import json
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import Mock

if "app.config" not in sys.modules or sys.modules["app.config"].Settings.__name__ != "OfflineSettings":
    raise RuntimeError("Use the reviewed offline runner")

import pytest
from PIL import Image
from app.db.models import Artifact, DatasetVersion, MetricSet, ModelVersion, Sample, Task, TaskModel
from app.errors import AppError
from app.services import classification as service
from app.services.dispatch import Delivery
from app.services.input_freeze import verify_inputs
from app.services.records import rerun_record, submit_to_advisor
from app.services.tasks import get_visible_task
from app.services.task_artifacts import TaskArtifacts
from apps.worker import classification as worker
from apps.worker import jobs
from test_phase_a_authorization import lab, client


@pytest.fixture
def cls(lab, monkeypatch):
    classes = [{"id": i, "key": f"c{i}", "display_zh": f"类别{i}"} for i in range(6)]
    def asset(slug, settings):
        if slug not in ("mobilenet_v3_small", "resnet18"):
            raise AppError("模型不可用", code="CLASSIFICATION_MODEL_UNAVAILABLE", stage="load")
        return SimpleNamespace(slug=slug, name=slug, classes=classes, preprocess={"resize": 224},
                               protocol_hash="p" * 64, weight_sha256=("a" if slug == "resnet18" else "b") * 64,
                               classes_hash="c" * 64, preprocess_hash="d" * 64, param_count=10)
    monkeypatch.setattr(service, "asset", asset)
    monkeypatch.setattr(worker, "asset", asset)
    monkeypatch.setattr(service, "get_settings", lambda: lab.settings)
    monkeypatch.setattr(service, "invalidate_after_write", lambda *args: None)
    monkeypatch.setattr(worker, "invalidate_after_write", lambda *args: None)
    queue = Mock(side_effect=lambda _settings, _function, task_id, _timeout, **kwargs: Delivery("confirmed", f"task-{task_id}"))
    monkeypatch.setattr(service, "enqueue", queue)
    def predict(slug, paths, root=None):
        return [{"class_id": 0, "key": "c0", "display_zh": "类别0", "score": .5,
                 "scores": [.5, .1, .1, .1, .1, .1], "topk": [{"class_id": 0, "score": .5}]} for _ in paths]
    monkeypatch.setattr(worker, "predict_images", predict)
    return SimpleNamespace(lab=lab, queue=queue, predict=predict)


def files():
    result = []
    for index in range(2):
        stream = io.BytesIO()
        Image.new("RGB", (20, 20), (index * 100, 20, 30)).save(stream, format="PNG")
        result.append((f"image #{index}.png", stream.getvalue()))
    return result


def create(cls, labels=None, models=None, key=None):
    lab = cls.lab
    batch = service.create_batch(lab.db, lab.owner, files(), labels, lab.settings)
    task = service.create_classification_task(lab.db, lab.owner, batch_id=batch["batch_id"],
                                             model_slugs=models or ["mobilenet_v3_small"],
                                             idempotency_key=key, settings=lab.settings)
    return batch, task


@pytest.mark.parametrize("labels", [None, [0, 1]])
def test_classification_worker_results_metrics_and_download(cls, labels):
    lab = cls.lab
    batch, task = create(cls, labels)
    jobs.run_classification(task.id)
    lab.db.expire_all()
    task = lab.db.get(Task, task.id)
    assert task.status == "success"
    result = service.serialize_classification_task(lab.db, task, lab.settings)
    assert len(result["predictions"]) == 2 and result["classes"][0]["id"] == 0
    assert len(result["samples"]) == 2 and all(row["preview_url"] for row in result["samples"])
    assert all("mask" not in row for row in result["samples"])
    assert result["metrics"]["available"] is bool(labels)
    assert lab.db.query(MetricSet).filter_by(task_id=task.id).count() == int(bool(labels))
    if labels:
        assert result["metrics"]["models"][0]["accuracy"] == .5
    else:
        assert result["metrics"] == {"available": False}
    document = json.loads(TaskArtifacts(lab.db, task, lab.settings).file("classification.json").read_text(encoding="utf-8"))
    assert document["has_gt"] is bool(labels)
    assert "mIoU" not in json.dumps(document)
    with pytest.raises(AppError):
        TaskArtifacts(lab.db, task, lab.settings).file("bundle.zip")
    # Existing completed-job claim is idempotent.
    jobs.run_classification(task.id)
    assert lab.db.query(Artifact).filter_by(task_id=task.id, kind="classification_result").count() == 1


@pytest.mark.parametrize("labels", [[0], [0, 6], [True, 1], [0, None], "garbage", {"x": 0}])
def test_classification_partial_or_invalid_labels_rejected(cls, labels):
    with pytest.raises(AppError) as error:
        service.create_batch(cls.lab.db, cls.lab.owner, files(), labels, cls.lab.settings)
    assert error.value.code == "BAD_CLASS_LABELS"


def test_classification_invalid_images_duplicates_limits(cls):
    lab = cls.lab
    for rows in ([], [("bad.png", b"bad")], [files()[0], files()[0]], files() * 26):
        with pytest.raises(AppError):
            service.create_batch(lab.db, lab.owner, rows, settings=lab.settings)


def test_classification_idempotency_and_scope(cls):
    lab = cls.lab
    batch, task = create(cls, key="same-key")
    again = service.create_classification_task(lab.db, lab.owner, batch_id=batch["batch_id"], model_slugs=["mobilenet_v3_small"], idempotency_key="same-key", settings=lab.settings)
    assert again.id == task.id and cls.queue.call_count == 1
    with pytest.raises(AppError) as error:
        service.create_classification_task(lab.db, lab.owner, batch_id=batch["batch_id"], model_slugs=["resnet18"], idempotency_key="same-key", settings=lab.settings)
    assert error.value.code == "IDEMPOTENCY_CONFLICT"
    for user in (lab.peer, lab.advisor):
        with pytest.raises(AppError):
            service.create_classification_task(lab.db, user, batch_id=batch["batch_id"], model_slugs=["mobilenet_v3_small"], settings=lab.settings)
        lab.db.rollback()
        with pytest.raises(AppError):
            get_visible_task(lab.db, task.id, user)


@pytest.mark.parametrize("change", ["labels", "mask", "bytes", "protocol", "model_links", "declared_hash"])
def test_classification_frozen_inputs_reject_changes(cls, change):
    lab = cls.lab
    batch, task = create(cls, labels=[0, 1])
    version = lab.db.get(DatasetVersion, batch["batch_id"])
    sample = lab.db.query(Sample).filter_by(version_id=version.id).first()
    if change == "labels":
        meta = dict(version.class_map_json)
        meta["labels_by_sample_key"] = {sample.sample_key: 2}
        version.class_map_json = meta
    elif change == "mask":
        sample.mask_uri = "data:fake-gt.png"
    elif change == "bytes":
        from app.services.storage import resolve_uri
        resolve_uri(sample.origin_uri, lab.settings).write_bytes(b"changed")
    elif change == "protocol":
        meta = dict(version.class_map_json); meta["classes"] = list(reversed(meta["classes"])); version.class_map_json = meta
    elif change == "declared_hash":
        sample.sha256 = "changed-db-hash"
    else:
        lab.db.query(TaskModel).filter_by(task_id=task.id).first().role = "student_under_test"
    lab.db.commit()
    with pytest.raises(AppError):
        jobs.run_classification(task.id)
    lab.db.expire_all()
    assert lab.db.get(Task, task.id).status == "failed"
    assert lab.db.query(MetricSet).filter_by(task_id=task.id).count() == 0


def test_classification_partial_failure_is_not_success(cls, monkeypatch):
    batch, task = create(cls, models=["mobilenet_v3_small", "resnet18"])
    def predict(slug, paths, root=None):
        if slug == "resnet18": raise RuntimeError("private-secret-path")
        return cls.predict(slug, paths)
    monkeypatch.setattr(worker, "predict_images", predict)
    jobs.run_classification(task.id)
    cls.lab.db.expire_all()
    task = cls.lab.db.get(Task, task.id)
    assert task.status == "partial_success"
    result = service.serialize_classification_task(cls.lab.db, task, cls.lab.settings)
    assert len(result["predictions"]) == 2
    assert "private-secret-path" not in json.dumps(result)


@pytest.mark.parametrize("state", ["rejected", "unknown"])
def test_classification_queue_delivery_states(cls, state):
    cls.queue.side_effect = lambda _s, _f, task_id, _t, **kw: Delivery(state, f"task-{task_id}")
    _, task = create(cls)
    assert task.status == ("failed" if state == "rejected" else "queued")
    assert ("QUEUE_REJECTED" if state == "rejected" else "QUEUE_UNKNOWN") in task.error_summary


def test_classification_upload_api_contract(cls):
    from app.routers import classification as router
    with client(cls.lab, cls.lab.owner) as http:
        http.app.include_router(router.router, prefix="/api")
        response = http.post("/api/classification/uploads", files=[("files", (name, content, "image/png")) for name, content in files()], data={"labels_json": "[0, 1]"})
        assert response.status_code == 200, response.text
        result = http.post("/api/classification/tasks", json={"batch_id": response.json()["batch_id"], "model_slugs": ["mobilenet_v3_small"]})
        assert result.status_code == 200, result.text
        assert result.json()["type"] == "classification" and result.json()["has_gt"] is True
        assert result.json()["metrics"] == {"available": False}


def test_classification_actor_revoked_blocks_worker(cls, monkeypatch):
    _, task = create(cls)
    cls.lab.owner.status = "disabled"
    cls.lab.db.commit()
    predictor = Mock()
    monkeypatch.setattr(worker, "predict_images", predictor)
    with pytest.raises(AppError): jobs.run_classification(task.id)
    assert predictor.call_count == 0


def test_classification_preserves_uploaded_bytes(cls):
    import hashlib
    from app.services.storage import resolve_uri
    batch = service.create_batch(cls.lab.db, cls.lab.owner, files(), settings=cls.lab.settings)
    samples = cls.lab.db.query(Sample).filter_by(version_id=batch["batch_id"]).order_by(Sample.sample_key).all()
    for (_, original), sample in zip(files(), samples):
        assert resolve_uri(sample.origin_uri, cls.lab.settings).read_bytes() == original
        assert sample.sha256 == hashlib.sha256(original).hexdigest()


@pytest.mark.parametrize("change", ["role", "source", "shape"])
def test_classification_worker_rejects_invalid_model_contract(cls, monkeypatch, change):
    from app.db.models import Model
    _, task = create(cls)
    link = cls.lab.db.query(TaskModel).filter_by(task_id=task.id).one()
    mv = cls.lab.db.get(ModelVersion, link.model_version_id)
    if change == "role": link.role = "student_under_test"
    elif change == "source": cls.lab.db.get(Model, mv.model_id).source = "student"
    else: mv.num_classes = 4
    cls.lab.db.commit()
    predictor = Mock()
    monkeypatch.setattr(worker, "predict_images", predictor)
    with pytest.raises(AppError): jobs.run_classification(task.id)
    assert predictor.call_count == 0


def test_classification_sharing_history_rerun_and_artifact_policy(cls):
    lab = cls.lab
    _, task = create(cls)
    jobs.run_classification(task.id)
    lab.db.expire_all()
    task = lab.db.get(Task, task.id)
    with pytest.raises(AppError): get_visible_task(lab.db, task.id, lab.advisor)
    submit_to_advisor(lab.db, lab.owner, task.id)
    assert get_visible_task(lab.db, task.id, lab.advisor).id == task.id
    with pytest.raises(AppError): get_visible_task(lab.db, task.id, lab.peer)
    replacement = rerun_record(lab.db, lab.owner, task.id)
    assert replacement.type == "classification" and replacement.id != task.id
    for rel, kind in [("bundle.zip", "bundle"), ("task.json", "log"), ("gt/image_0001.png", "gt"), ("overlay/image_0001.png", "overlay")]:
        path = lab.settings.storage_path / "tasks" / task.id / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"forbidden fixture")
        lab.db.add(Artifact(id=__import__('uuid').uuid4().hex, task_id=task.id, sample_key="image_0001" if '/' in rel else None, model_version_id=None, kind=kind, rel_path=rel))
    lab.db.commit()
    for rel in ["bundle.zip", "task.json", "gt/image_0001.png", "overlay/image_0001.png"]:
        with pytest.raises(AppError): TaskArtifacts(lab.db, task, lab.settings).file(rel)


def test_classification_input_changed_during_execution_is_not_published(cls, monkeypatch):
    from app.services.storage import resolve_uri
    _, task = create(cls)
    def mutate(slug, paths, root=None):
        result = cls.predict(slug, paths)
        paths[0].write_bytes(b"changed during execution")
        return result
    monkeypatch.setattr(worker, "predict_images", mutate)
    with pytest.raises(AppError) as error: jobs.run_classification(task.id)
    assert error.value.code == "INPUT_CHANGED"
    cls.lab.db.expire_all()
    assert cls.lab.db.get(Task, task.id).status == "failed"
    assert cls.lab.db.query(Artifact).filter_by(task_id=task.id, kind="classification_result").count() == 0


def test_classification_registry_existing_weight_mismatch_rejected(cls):
    from app.db.models import Weight
    _, task = create(cls)
    link = cls.lab.db.query(TaskModel).filter_by(task_id=task.id).one()
    cls.lab.db.query(Weight).filter_by(version_id=link.model_version_id).one().sha256 = "wrong"
    cls.lab.db.commit()
    with pytest.raises(AppError): create(cls)


def test_classification_missing_default_does_not_disable_available_model(cls, monkeypatch):
    original = service.asset
    def without_default(slug, settings):
        if slug == "mobilenet_v3_small":
            raise AppError("缺少默认模型", code="CLASSIFICATION_MODEL_UNAVAILABLE", stage="load")
        return original(slug, settings)
    monkeypatch.setattr(service, "asset", without_default)
    batch, task = create(cls, models=["resnet18"])
    assert task.status == "queued" and batch["sample_count"] == 2
