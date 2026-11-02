"""Trusted CPU ROI body with pre-publication authorization and frozen-byte checks."""
import hashlib
import json
import logging
import os

from rq.timeouts import JobTimeoutException

from app.cache import invalidate_after_write
from app.db.models import Artifact, AuditLog, Sample, Task, TaskModel, User
from app.errors import AppError
from app.services.input_freeze import lock_version, verify_inputs
from app.services.pcb_classification import (TYPE, MAX_BYTES, asset, asset_root, image_bytes,
    register_model, require_enabled, snapshot)
from app.services.storage import resolve_uri
from app.services.task_artifacts import TaskArtifacts
from app.util_time import new_id, utcnow

logger = logging.getLogger(__name__)


def assert_execution(db, task, settings):
    try:
        require_enabled(settings)
    except AppError:
        from infer.pcb_classification.runtime import clear_cache
        clear_cache()
        raise
    actor = db.query(User).filter_by(id=task.creator_id).populate_existing().with_for_update().one_or_none()
    if not actor or actor.status != "active" or actor.role not in {"student", "advisor"}:
        raise AppError("任务创建者当前不可运行任务", code="TASK_ACTOR_UNAVAILABLE", stage="auth")
    try:
        snap = snapshot(db, task)
        item = asset(snap["model"]["slug"], settings)
        model = register_model(db, item)
        if task.type != TYPE or snap["model"]["id"] != model.id or task.preprocess_id != model.preprocess_id:
            raise ValueError("classification identity changed")
    except (AppError, JobTimeoutException):
        raise
    except Exception as exc:
        raise AppError("PCB 分类协议已变更", code="PCB_CLS_PROTOCOL_CHANGED", stage="protocol") from exc


def compute(root, model_id, content, filename):
    from infer.pcb_classification.runtime import predict
    return predict(root, model_id, content, filename)


def run_body(db, task, settings):
    staged, published = [], []
    staging = None
    try:
        assert_execution(db, task, settings)
        frozen = verify_inputs(db, task, settings)["samples"][0]
        snap = snapshot(db, task)
        sample = db.query(Sample).filter_by(version_id=task.dataset_version_id).one()
        path = resolve_uri(sample.origin_uri, settings)
        with path.open("rb") as stream:
            content = stream.read(MAX_BYTES + 1)
        if hashlib.sha256(content).hexdigest() != frozen["origin_sha256"]:
            raise AppError("ROI 实际字节与冻结输入不一致", code="INPUT_CHANGED", stage="file")
        _, facts = image_bytes(path.name, content)
        if facts != snap["dataset"]["image"]:
            raise AppError("ROI 解码信息与上传不一致", code="INPUT_CHANGED", stage="file")
        db.commit()  # Release locks during CPU work so revocation remains possible.
        result, preview = compute(asset_root(settings), snap["model"]["slug"], content, path.name)
        result.update({"task_id": task.id, "sample_sha256": frozen["origin_sha256"],
                       "weight_sha256": snap["model"]["weight_sha256"], "source_hash": snap["preprocess"]["source_hash"]})
        guard = TaskArtifacts(db, task, settings)
        staging = guard.locate("pcb-cls-stage-" + new_id(), must_exist=False)
        staging.mkdir(exist_ok=False)
        for kind, rel, data, key in (
            ("pcb_cls_result", "pcb_classification.json", json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8"), None),
            ("origin", "origin/image.png", preview, "image"),
        ):
            temp = staging / ("result.json" if key is None else "preview.png")
            staged.append((temp, kind, rel, key))
            temp.write_bytes(data)
        db.query(User).filter_by(id=task.creator_id).populate_existing().with_for_update().one_or_none()
        lock_version(db, task.dataset_version_id)
        current = db.query(Task).filter_by(id=task.id).populate_existing().with_for_update().one()
        if current.status != "running":
            raise AppError("任务状态已改变，拒绝发布", code="PCB_CLS_STATE_CHANGED", stage="protocol")
        verify_inputs(db, current, settings)
        assert_execution(db, current, settings)
        for source, kind, rel, key in staged:
            target = guard.locate(rel, must_exist=False)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise ValueError("never overwrite published results")
            os.replace(source, target)
            published.append(target)
            db.add(Artifact(id=new_id(), task_id=current.id, kind=kind, rel_path=rel, sample_key=key, model_version_id=None))
        link = db.query(TaskModel).filter_by(task_id=current.id).one()
        link.status, link.fail_stage, link.fail_message = "success", None, None
        current.status, current.error_summary, current.updated_at = "success", None, utcnow()
        db.add(AuditLog(id=new_id(), actor_id=current.creator_id, action="pcb_cls.finish", target_type="task", target_id=current.id,
                        reason="单张 ROI 六分类成功；未生成准确率指标"))
        db.commit()
        published.clear()
        invalidate_after_write(current.id, current.creator_id)
    except Exception as exc:
        db.rollback()
        for path in published:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("PCB classification unpublished output cleanup incomplete")
        if isinstance(exc, JobTimeoutException):
            raise AppError("PCB 分类任务超过执行时限，请再跑", code="PCB_CLS_JOB_TIMEOUT", stage="resource") from exc
        if isinstance(exc, AppError):
            raise
        raise AppError("PCB 分类推理或结果保存失败", code="PCB_CLS_EXECUTION_FAILED", stage="forward") from exc
    finally:
        for path, *_ in staged:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("PCB classification staging cleanup incomplete")
        if staging and staging.exists():
            try:
                staging.rmdir()
            except OSError:
                logger.warning("PCB classification staging directory cleanup incomplete")
