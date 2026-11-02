"""PCB body only; the existing Worker owns claiming and terminal failures."""
from __future__ import annotations

import io
import hashlib
import json
import logging
import os
from pathlib import Path

import numpy as np
from PIL import Image
from rq.timeouts import JobTimeoutException

from app.cache import invalidate_after_write
from app.db.models import (Artifact, AuditLog, DatasetVersion, MetricSet, ModelVersion,
                           PreprocessSpecRow, Sample, Task, TaskModel, User)
from app.errors import AppError
from app.services.input_freeze import lock_version, verify_inputs
from app.services.pcb_segmentation import (TYPE, _protocol, asset, asset_root, image_bytes,
    pcb_snapshot, register_model, require_enabled, task_include_cam, MAX_IMAGE_BYTES)
from app.services.storage import resolve_uri
from app.services.task_artifacts import TaskArtifacts
from app.util_time import new_id, utcnow

logger = logging.getLogger(__name__)


def assert_pcb_execution(db, task, settings):
    require_enabled(settings)
    user = db.query(User).filter_by(id=task.creator_id).populate_existing().with_for_update().one_or_none()
    if not user or user.status != "active" or user.role not in {"student", "advisor"}:
        raise AppError("任务创建者当前不可运行任务", code="TASK_ACTOR_UNAVAILABLE", stage="auth")
    try:
        snap = pcb_snapshot(db, task)
        model = snap["models"][0]
        item = asset(model["slug"], settings)
        registered = register_model(db, item)
        expected_spec = _protocol(db, item, task_include_cam(db, task))
        base = _protocol(db, item)
        version = db.get(DatasetVersion, task.dataset_version_id)
        if (task.type != TYPE or model["id"] != registered.id or task.preprocess_id != expected_spec.id
                or version.preprocess_id != base.id or snap["dataset"].get("protocol_hash") != item["protocol_hash"]
                or snap["dataset"].get("scene") != "pcb" or snap["dataset"].get("task_kind") != "segmentation"):
            raise ValueError("PCB protocol identity")
    except (AppError, JobTimeoutException):
        raise
    except Exception as exc:
        raise AppError("PCB 输入或模型协议已变更", code="PCB_PROTOCOL_CHANGED", stage="protocol") from exc


def compute(model_id, image, include_cam, root):
    import torch
    from infer.pcb.runtime import load_model
    from infer.pcb.catalog import INTEROP
    from infer.pcb.visualize import SegmentationGradCAM, predict_layers, probability_heatmap
    threads = torch.get_num_threads()
    model = None
    try:
        if torch.get_num_interop_threads() != INTEROP or not torch.backends.mkldnn.enabled:
            raise ValueError("PCB runtime differs from the admitted CPU configuration")
        model = load_model(model_id, root=root)
        layers = predict_layers(model, image)
        cam = {"status": "not_requested"}
        if include_cam:
            try:
                raw = SegmentationGradCAM(model)(image)
                if raw["status"] == "ok":
                    values = np.asarray(raw["map"])
                    if values.shape != (220, 220) or not np.isfinite(values).all():
                        raise ValueError("invalid CAM map")
                    layers["cam"] = probability_heatmap(values)
                cam = {key: raw[key] for key in ("status", "reason", "layer", "target") if key in raw}
            except JobTimeoutException:
                # RQ's deadline belongs to the whole task, not the optional
                # explanation layer. It must reach lifecycle failure handling.
                raise
            except Exception:
                cam = {"status": "failed", "reason": "Grad-CAM 计算失败；基础分割结果仍可用"}
        return layers, cam
    finally:
        del model
        torch.set_num_threads(threads)


def metrics(gt, pred):
    positive, truth = pred == 1, gt == 1
    tp, fp = int((positive & truth).sum()), int((positive & ~truth).sum())
    fn, tn = int((~positive & truth).sum()), int((~positive & ~truth).sum())
    divide = lambda numerator, denominator: numerator / denominator if denominator else None
    return {"available": True, "n": 1, "scope": "pcb_uploaded_pair", "class": "defect",
            "defect_dice": divide(2 * tp, 2 * tp + fp + fn), "iou": divide(tp, tp + fp + fn),
            "precision": divide(tp, tp + fp), "recall": divide(tp, tp + fn),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "undefined_policy": "分母为 0 的指标为 null；不以置信度替代精度"}


def run_pcb_body(db, task, settings):
    staged, published = [], []
    staging = None
    try:
        assert_pcb_execution(db, task, settings)
        frozen = verify_inputs(db, task, settings)["samples"][0]
        snap = pcb_snapshot(db, task)
        slug = snap["models"][0]["slug"]
        mid = snap["models"][0]["id"]
        sample = db.query(Sample).filter_by(version_id=task.dataset_version_id).one()
        original_path = resolve_uri(sample.origin_uri, settings)
        with original_path.open("rb") as stream:
            original = stream.read(MAX_IMAGE_BYTES + 1)
        if hashlib.sha256(original).hexdigest() != frozen["origin_sha256"]:
            raise AppError("实际读取的图像与冻结输入不一致", code="INPUT_CHANGED", stage="file")
        original, _ = image_bytes(original_path.name, original)
        with Image.open(io.BytesIO(original)) as image:
            image_rgb = np.asarray(image).copy()
        gt = None
        if task.has_gt:
            mask_path = resolve_uri(sample.mask_uri, settings)
            with mask_path.open("rb") as stream:
                mask_content = stream.read(MAX_IMAGE_BYTES + 1)
            if hashlib.sha256(mask_content).hexdigest() != frozen["mask_sha256"]:
                raise AppError("实际读取的 GT 与冻结输入不一致", code="INPUT_CHANGED", stage="file")
            normalized, _ = image_bytes("gt.png", mask_content, gt=True)
            with Image.open(io.BytesIO(normalized)) as mask_image:
                gt = np.asarray(mask_image).copy()
        include_cam = task_include_cam(db, task)
        # CPU work must not keep the read-only authorization locks: revocation
        # is allowed while computing and checked again before publication.
        db.commit()
        layers, cam = compute(slug, image_rgb, include_cam, asset_root(settings))
        pred = np.asarray(layers["pred_mask"])
        prob = np.asarray(layers["probability"])
        if (pred.shape != (220, 220) or pred.dtype != np.uint8 or not set(np.unique(pred).tolist()) <= {0, 1}
                or prob.shape != (220, 220) or not np.isfinite(prob).all() or np.any(prob < 0) or np.any(prob > 1)):
            raise ValueError("invalid PCB output")
        metrics_payload = metrics(gt, pred) if gt is not None else {"available": False}
        # Display-only derivative: retain the frozen 0/1 prediction for metrics
        # and machine downloads, and never feed this asset back into inference.
        outputs = [("origin", "origin/image.png", image_rgb, None),
                   ("pred_mask", f"pred_mask/{mid}/image.png", pred, mid),
                   ("mask_visual", f"mask_visual/{mid}/image.png", pred * np.uint8(255), mid)]
        for kind, key in (("overlay", "overlay"), ("boundary", "boundary"), ("probability", "probability_heatmap")):
            value = np.asarray(layers[key])
            if value.shape != (220, 220, 3) or value.dtype != np.uint8:
                raise ValueError("invalid PCB layer")
            outputs.append((kind, f"{kind}/{mid}/image.png", value, mid))
        if cam.get("status") == "ok":
            value = np.asarray(layers.get("cam"))
            if value.shape != (220, 220, 3) or value.dtype != np.uint8:
                # An optional interpretation cannot invalidate base segmentation.
                cam = {"status": "failed", "reason": "Grad-CAM 输出格式无效；基础分割结果仍可用"}
            else:
                outputs.append(("cam", f"cam/{mid}/image.png", value, mid))
        if gt is not None:
            from infer.pcb.visualize import error_map
            outputs.extend([("gt", "gt/image.png", gt, None), ("error", f"error/{mid}/image.png", error_map(gt, pred), mid)])
        guard = TaskArtifacts(db, task, settings)
        staging = guard.locate("pcb-stage-" + new_id(), must_exist=False)
        staging.mkdir(exist_ok=False)
        for index, (kind, rel, array, model) in enumerate(outputs):
            path = staging / f"{index}.png"
            staged.append((path, kind, rel, "image", model))
            Image.fromarray(array).save(path, format="PNG")
        result = {"schema": 1, "task_id": task.id, "scene": "pcb", "task_kind": "segmentation",
                  "model_id": slug, "model_version_id": mid, "weight_sha256": snap["models"][0]["weight_sha256"],
                  "protocol_hash": snap["preprocess"]["protocol_hash"], "include_cam": include_cam,
                  "deployment_source_hash": snap["preprocess"]["deployment_source_hash"],
                  "sample_sha256": sample.sha256, "has_gt": bool(gt is not None), "metrics": metrics_payload,
                  "foreground_pixels": int((pred == 1).sum()), "cam": cam,
                  "legend": {"mask": "原始二值掩码：0 背景 / 1 缺陷", "mask_visual": "可视化掩码：0 背景 / 255 缺陷",
                             "probability": "缺陷 softmax 分数，非精度", "error": "绿 TP / 红 FP / 蓝 FN"}}
        result_path = staging / "result.json"
        staged.append((result_path, "pcb_result", "pcb.json", None, None))
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        # Obtain current locks in the same actor -> version -> task order before publication.
        db.query(User).filter_by(id=task.creator_id).populate_existing().with_for_update().one_or_none()
        lock_version(db, task.dataset_version_id)
        current = db.query(Task).filter_by(id=task.id).populate_existing().with_for_update().one()
        if current.status != "running":
            raise AppError("任务状态已变更，未发布结果", code="PCB_TASK_STATE_CHANGED", stage="protocol")
        verify_inputs(db, current, settings)
        assert_pcb_execution(db, current, settings)
        for source, kind, rel, key, model in staged:
            target = guard.locate(rel, must_exist=False)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise ValueError("existing PCB result is never overwritten")
            os.replace(source, target)
            published.append(target)
            db.add(Artifact(id=new_id(), task_id=current.id, kind=kind, rel_path=rel, sample_key=key, model_version_id=model))
        link = db.query(TaskModel).filter_by(task_id=current.id).one()
        link.status, link.fail_stage, link.fail_message = "success", None, None
        if gt is not None:
            db.add(MetricSet(id=new_id(), task_id=current.id, scope="pcb_uploaded_pair", n=1, payload_json=metrics_payload))
        current.status, current.error_summary, current.updated_at = "success", None, utcnow()
        db.add(AuditLog(id=new_id(), actor_id=current.creator_id, action="pcb.finish", target_type="task", target_id=current.id,
                        reason="PCB 分割成功；CAM=" + str(cam.get("status"))))
        db.commit()
        published.clear()  # Committed files belong to the task and must survive cache failures.
        invalidate_after_write(current.id, current.creator_id)
    except Exception as exc:
        db.rollback()
        for path in published:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("PCB unpublished output cleanup incomplete task=%s", task.id)
        if isinstance(exc, JobTimeoutException):
            raise AppError("PCB 任务超过执行时限，请通过再跑创建新任务", code="PCB_JOB_TIMEOUT", stage="resource") from exc
        if isinstance(exc, AppError):
            raise
        raise AppError("PCB 推理或结果保存失败，请联系管理员核查", code="PCB_EXECUTION_FAILED", stage="forward") from exc
    finally:
        for path, *_ in staged:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("PCB staging file cleanup incomplete task=%s", task.id)
        if staging is not None and staging.exists():
            # Only files created by this attempt; never recursively delete task roots.
            try:
                staging.rmdir()
            except OSError:
                logger.warning("PCB staging directory cleanup incomplete task=%s", task.id)
