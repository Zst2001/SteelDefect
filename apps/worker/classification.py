"""Trusted built-in classification body; lifecycle/claim remain in jobs._run_task."""
from __future__ import annotations

import json
import math
from PIL import Image

from app.cache import invalidate_after_write
from app.db.models import (Artifact, AuditLog, Dataset, DatasetVersion, MetricSet, Model,
                           ModelVersion, PreprocessSpecRow, Sample, Task, TaskModel, TaskSample, Weight)
from app.errors import AppError
from app.services.classification import asset, asset_root
from app.services.input_freeze import verify_inputs, lock_version
from app.services.storage import resolve_uri
from app.services.task_artifacts import TaskArtifacts
from app.util_time import new_id, utcnow
from infer.classification import classification_metrics, predict_images


def assert_classification_execution(db, task, settings):
    version = db.query(DatasetVersion).filter_by(id=task.dataset_version_id).populate_existing().with_for_update().one_or_none()
    dataset = db.get(Dataset, version.dataset_id) if version else None
    protocol = db.query(PreprocessSpecRow).filter_by(id=task.preprocess_id).populate_existing().with_for_update().one_or_none()
    if task.type != "classification" or not version or version.kind != "classification_batch" or version.is_fixed_test or not dataset or dataset.owner_id != task.creator_id or not protocol or protocol.dataset != "neu_cls" or version.preprocess_id != protocol.id:
        raise AppError("分类任务协议或批次归属无效", code="CLASSIFICATION_PROTOCOL_MISMATCH", stage="protocol")
    links = db.query(TaskModel).filter_by(task_id=task.id).order_by(TaskModel.sort_order).populate_existing().with_for_update().all()
    if not 1 <= len(links) <= 3 or len({link.model_version_id for link in links}) != len(links):
        raise AppError("分类任务模型数量无效", code="CLASSIFICATION_MODEL_COUNT", stage="protocol")
    for link in links:
        mv = db.get(ModelVersion, link.model_version_id)
        parent = db.query(Model).filter_by(id=mv.model_id).populate_existing().with_for_update().one_or_none() if mv else None
        mv = db.query(ModelVersion).filter_by(id=link.model_version_id).populate_existing().with_for_update().one_or_none()
        if not mv or not parent or parent.source != "builtin" or parent.owner_id is not None or link.role != "baseline" or mv.num_classes != 6 or mv.in_channels != 3 or mv.preprocess_id != protocol.id or mv.status != "runnable" or mv.requires_cuda:
            raise AppError("分类任务只接受已审定的 CPU 内置六类模型", code="CLASSIFICATION_MODEL_UNAVAILABLE", stage="protocol")
        item = asset(mv.slug, settings)
        weights = db.query(Weight).filter_by(version_id=mv.id).populate_existing().with_for_update().all()
        if len(weights) != 1 or weights[0].sha256 != item.weight_sha256 or weights[0].file_uri != f"asset:classification/neu_cls_v1/{mv.slug}/weights.pth" or item.protocol_hash != (version.class_map_json or {}).get("protocol_hash"):
            raise AppError("分类模型或协议指纹已变更", code="CLASSIFICATION_ASSET_CHANGED", stage="load")


def _prediction_valid(row):
    if type(row.get("class_id")) is not int or not 0 <= row["class_id"] <= 5:
        return False
    scores = row.get("scores", [])
    return len(scores) == 6 and all(isinstance(x, (int, float)) and math.isfinite(x) and 0 <= x <= 1 for x in scores) and abs(sum(scores) - 1) < 1e-4 and math.isfinite(row.get("score", float("nan")))


def run_classification_body(db, task, settings):
    try:
        _run(db, task, settings)
    except AppError:
        raise
    except Exception as exc:
        raise AppError("分类任务执行或结果保存失败，请联系管理员核查", code="CLASSIFICATION_EXECUTION_FAILED", stage="forward") from exc


def _run(db, task, settings):
    version = db.get(DatasetVersion, task.dataset_version_id)
    meta = version.class_map_json or {}
    sample_links = db.query(TaskSample).filter_by(task_id=task.id).order_by(TaskSample.sort_order).all()
    samples = [db.get(Sample, link.sample_id) for link in sample_links]
    if not 1 <= len(samples) <= 50 or any(s is None or s.mask_uri is not None for s in samples):
        raise AppError("分类批次已变更", code="INPUT_CHANGED", stage="file")
    paths = [resolve_uri(sample.origin_uri, settings) for sample in samples]
    guard = TaskArtifacts(db, task, settings)
    task_dir = guard.locate("classification.json", must_exist=False).parent
    task_dir.mkdir(parents=True, exist_ok=True)
    for sample, path in zip(samples, paths):
        target = guard.locate(f"origin/{sample.sample_key}.png", must_exist=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(path) as image:
            image.convert("RGB").save(target, format="PNG")
        db.add(Artifact(id=new_id(), task_id=task.id, kind="origin", rel_path=f"origin/{sample.sample_key}.png", sample_key=sample.sample_key, model_version_id=None))
    links = db.query(TaskModel).filter_by(task_id=task.id).order_by(TaskModel.sort_order).all()
    predictions, model_info, metric_models = [], [], []
    outcomes = []
    for link in links:
        mv = db.get(ModelVersion, link.model_version_id)
        try:
            item = asset(mv.slug, settings)
            output = predict_images(mv.slug, paths, root=asset_root(settings))
            if len(output) != len(samples) or not all(_prediction_valid(row) for row in output):
                raise ValueError("invalid classification result")
            for sample, row in zip(samples, output):
                predictions.append({"sample_key": sample.sample_key, "model_version_id": mv.id, "model_slug": mv.slug, **row})
            labels = [meta["labels_by_sample_key"][s.sample_key] for s in samples] if task.has_gt else None
            if labels is not None:
                metric_models.append({"model_version_id": mv.id, "model_slug": mv.slug, "name": item.name,
                                      **classification_metrics(labels, [row["class_id"] for row in output])})
            outcomes.append((link.id, "success", None))
            model_info.append({"model_version_id": mv.id, "slug": mv.slug, "name": item.name,
                               "status": "success", "weight_sha256": item.weight_sha256,
                               "classes_hash": item.classes_hash, "preprocess_hash": item.preprocess_hash,
                               "protocol_hash": item.protocol_hash})
        except Exception:
            outcomes.append((link.id, "failed", "内置分类模型执行失败，请联系管理员核查"))
            model_info.append({"model_version_id": mv.id, "slug": mv.slug, "status": "failed",
                               "fail_message": "内置分类模型执行失败，请联系管理员核查"})
    # Refresh immutable inputs and current execution authority before publishing.
    from app.db.models import User
    db.query(User).filter_by(id=task.creator_id).populate_existing().with_for_update().one_or_none()
    lock_version(db, task.dataset_version_id)
    current = db.query(Task).filter_by(id=task.id).populate_existing().with_for_update().one()
    if current.status != "running":
        db.rollback()
        return
    verify_inputs(db, current, settings)
    from apps.worker.jobs import _assert_lab_execution_authorized
    _assert_lab_execution_authorized(db, current)
    assert_classification_execution(db, current, settings)
    for link_id, status, failure in outcomes:
        link = db.get(TaskModel, link_id)
        link.status, link.fail_stage, link.fail_message = status, "forward" if failure else None, failure
    successes = sum(status == "success" for _, status, _ in outcomes)
    current.status = "success" if successes == len(outcomes) else "partial_success" if successes else "failed"
    current.error_summary = None if successes == len(outcomes) else "部分分类模型失败，请查看模型状态" if successes else "所有分类模型执行失败"
    current.updated_at = utcnow()
    metrics = {"available": bool(metric_models), "n": len(samples), "models": metric_models} if metric_models else {"available": False}
    if metric_models:
        db.add(MetricSet(id=new_id(), task_id=current.id, scope="classification_batch", n=len(samples), payload_json=metrics))
    result = {"schema": 1, "task_id": current.id, "type": "classification", "status": current.status,
              "has_gt": current.has_gt, "classes": meta["classes"], "protocol_hash": meta["protocol_hash"],
              "models": model_info, "predictions": predictions, "metrics": metrics,
              "samples": [{"sample_key": s.sample_key, "sha256": s.sha256,
                           **({"class_id": meta["labels_by_sample_key"][s.sample_key]} if current.has_gt else {})} for s in samples],
              "disclaimer": "仅六类已知缺陷；softmax 得分不是经过校准的正确概率。无完整图级标签不计算精度。"}
    if successes:
        result_path = guard.locate("classification.json", must_exist=False)
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        db.add(Artifact(id=new_id(), task_id=current.id, kind="classification_result", rel_path="classification.json", sample_key=None, model_version_id=None))
    db.add(AuditLog(id=new_id(), actor_id=current.creator_id, action="classification.finish", target_type="task", target_id=current.id, reason="分类任务完成：" + current.status))
    db.commit()
    invalidate_after_write(current.id, current.creator_id)
