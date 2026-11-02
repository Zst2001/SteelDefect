"""No schema change: version row lock + private, immutable submission manifest.

API mutations obey the version lock. Host-side replacements are detected, not repaired.
"""
import json

from app.db.models import Dataset, DatasetVersion, Model, ModelVersion, PreprocessSpecRow, Sample, Task, TaskModel, TaskSample, Weight
from app.errors import AppError
from app.services.storage import resolve_uri, sha256_file


def lock_version(db, version_id):
    return db.query(DatasetVersion).filter_by(id=version_id).populate_existing().with_for_update().one_or_none()


def current_samples(db, version_id):
    """Call after the DatasetVersion lock; refresh both DB snapshot and ORM state."""
    return db.query(Sample).filter_by(version_id=version_id).order_by(Sample.sample_key).populate_existing().with_for_update().all()


def assert_unreferenced(db, version):
    # A locking/current read is important under MySQL REPEATABLE READ.
    if db.query(Task).filter_by(dataset_version_id=version.id).with_for_update().first() is not None:
        raise AppError("批次已被任务引用，修正标注请上传新批次", code="DATASET_FROZEN", stage="file", status_code=409)


def manifest_path(settings, task_id):
    return settings.storage_path / "tasks" / task_id / "inputs.json"


def classification_snapshot(db, task):
    """Freeze classification labels/protocol/model identity without mask aliases."""
    version = db.query(DatasetVersion).filter_by(id=task.dataset_version_id).populate_existing().with_for_update().one()
    dataset = db.query(Dataset).filter_by(id=version.dataset_id).populate_existing().with_for_update().one()
    spec = db.query(PreprocessSpecRow).filter_by(id=task.preprocess_id).populate_existing().with_for_update().one()
    if version.kind != "classification_batch" or spec.dataset != "neu_cls" or version.preprocess_id != task.preprocess_id or dataset.owner_id != task.creator_id:
        raise ValueError("classification protocol changed")
    meta = version.class_map_json or {}
    if meta.get("task_kind") != "classification":
        raise ValueError("classification metadata missing")
    rows = db.query(Sample).filter_by(version_id=version.id).order_by(Sample.sample_key).populate_existing().with_for_update().all()
    labels = meta.get("labels_by_sample_key", {})
    if any(row.mask_uri is not None for row in rows) or bool(labels) != bool(task.has_gt):
        raise ValueError("classification label state changed")
    if labels and (set(labels) != {row.sample_key for row in rows} or any(type(v) is not int or not 0 <= v <= 5 for v in labels.values())):
        raise ValueError("classification labels invalid")
    models = []
    links = db.query(TaskModel).filter_by(task_id=task.id).order_by(TaskModel.sort_order).populate_existing().with_for_update().all()
    for link in links:
        mv = db.query(ModelVersion).filter_by(id=link.model_version_id).populate_existing().with_for_update().one()
        parent = db.query(Model).filter_by(id=mv.model_id).populate_existing().with_for_update().one()
        weights = db.query(Weight).filter_by(version_id=mv.id).populate_existing().with_for_update().all()
        if len(weights) != 1 or parent.source != "builtin" or parent.owner_id is not None or link.role != "baseline":
            raise ValueError("classification model changed")
        models.append({"id": mv.id, "slug": mv.slug, "role": link.role, "preprocess_id": mv.preprocess_id,
                       "classes": mv.num_classes, "input": [mv.in_channels, mv.input_h, mv.input_w],
                       "weight_sha256": weights[0].sha256, "weight_uri": weights[0].file_uri})
    return {"dataset": meta, "preprocess": spec.extra_json, "models": models,
            "sample_facts": [{"id": row.id, "sha256": row.sha256, "width": row.width, "height": row.height} for row in rows]}


def freeze_inputs(db, task, samples, settings):
    rows = []
    try:
        for sample in samples:
            origin_hash = sha256_file(resolve_uri(sample.origin_uri, settings))
            if origin_hash != sample.sha256:
                raise ValueError("origin changed")
            mask_uri = sample.mask_uri if task.has_gt and task.type != "demo" else None
            rows.append({"sample_id": sample.id, "sample_key": sample.sample_key,
                         "origin_uri": sample.origin_uri, "origin_sha256": origin_hash,
                         "mask_uri": mask_uri,
                         "mask_sha256": sha256_file(resolve_uri(mask_uri, settings)) if mask_uri else None})
        payload = {"schema": 1, "dataset_version_id": task.dataset_version_id,
                   "task_type": task.type, "has_gt": bool(task.has_gt), "samples": rows}
        if task.type == "classification":
            payload["classification"] = classification_snapshot(db, task)
        if task.type == "pcb_classify":
            from app.services.pcb_classification import snapshot
            payload["pcb_classify"] = snapshot(db, task)
        if task.type == "pcb_segmentation":
            from app.services.pcb_segmentation import pcb_snapshot
            payload["pcb_segmentation"] = pcb_snapshot(db, task)
        path = manifest_path(settings, task.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    except (OSError, ValueError) as exc:
        raise AppError("输入缺失、已变更或无法冻结；未入队", code="INPUT_FREEZE_FAILED", stage="file", status_code=409) from exc


def verify_inputs(db, task, settings):
    try:
        payload = json.loads(manifest_path(settings, task.id).read_text(encoding="utf-8"))
        if payload["dataset_version_id"] != task.dataset_version_id or payload["task_type"] != task.type or payload["has_gt"] != bool(task.has_gt):
            raise ValueError("task changed")
        if task.type == "classification" and payload.get("classification") != classification_snapshot(db, task):
            raise ValueError("classification inputs changed")
        if task.type == "pcb_classify":
            from app.services.pcb_classification import snapshot
            if payload.get("pcb_classify") != snapshot(db, task):
                raise ValueError("PCB classification inputs changed")
        if task.type == "pcb_segmentation":
            from app.services.pcb_segmentation import pcb_snapshot
            if payload.get("pcb_segmentation") != pcb_snapshot(db, task):
                raise ValueError("PCB inputs or protocol changed")
        links = db.query(TaskSample).filter_by(task_id=task.id).order_by(TaskSample.sort_order).populate_existing().with_for_update().all()
        if [s.sample_id for s in links] != [r["sample_id"] for r in payload["samples"]]:
            raise ValueError("links changed")
        for row in payload["samples"]:
            sample = db.query(Sample).filter_by(id=row["sample_id"]).populate_existing().with_for_update().one_or_none()
            if sample is None or sample.version_id != task.dataset_version_id or sample.sample_key != row["sample_key"] or sample.origin_uri != row["origin_uri"]:
                raise ValueError("sample changed")
            mask_uri = sample.mask_uri if task.has_gt and task.type != "demo" else None
            if mask_uri != row["mask_uri"]:
                raise ValueError("mask changed")
            for prefix in ("origin", "mask"):
                uri = row[prefix + "_uri"]
                if uri and sha256_file(resolve_uri(uri, settings)) != row[prefix + "_sha256"]:
                    raise ValueError("content changed")
        # Public task.json needs stable identity/hashes, never internal source paths.
        return {"dataset_version_id": payload["dataset_version_id"], "samples": [
            {k: v for k, v in row.items() if not k.endswith("_uri") and (task.type != "demo" or not k.startswith("mask"))}
            for row in payload["samples"]]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AppError("冻结输入缺失或已变更；拒绝执行/重跑，请使用新批次", code="INPUT_CHANGED", stage="file", status_code=409) from exc
