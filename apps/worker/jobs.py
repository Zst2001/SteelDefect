from __future__ import annotations

import platform
from pathlib import Path

import cv2
import numpy as np
from sqlalchemy.orm import Session

from app.bootstrap import ROOT  # noqa: F401
from app.cache import invalidate_after_write, invalidate_models_lists
from app.config import get_settings
from app.db.models import (
    Artifact,
    MetricSet,
    Model,
    ModelVersion,
    PreprocessSpecRow,
    Sample,
    Task,
    TaskModel,
    TaskSample,
    User,
    Weight,
)
from app.db.session import SessionLocal
from app.errors import AppError
from app.services.demo import assert_demo_worker_contract
from app.services.models import assert_model_role_access
from app.services.input_freeze import verify_inputs, lock_version
from rq import get_current_job
from rq.timeouts import JobTimeoutException
from app.services.storage import resolve_uri
from app.services.task_artifacts import write_bundle
from app.util_time import new_id, utcnow
from infer.dataset_images import preprocess_rgb, read_rgb
from infer.engine import count_parameters, get_builtin_module, predict_mask
from infer.masks import read_index_mask
from infer.metrics import add_to_confmat, build_metric_payload, empty_confmat, metrics_dict_from_confmat
from infer.montage import build_row
from infer.spec import (
    BATCH_REFERENCE_SCOPE,
    BUILTIN_DISPLAY_NAMES,
    BUILTIN_SLUGS,
    CAM_DISCLAIMER,
    DEMO_DISCLAIMER,
    NEU_CLASS_MAP,
    OFFICIAL_SPLIT_SCOPE,
    PreprocessSpec,
)
from infer.gradcam import (
    cam_artifact_rel,
    cam_class_ids,
    cam_montage_rel,
    compute_gradcam,
    overlay_cam_rgb,
    resolve_target_layer,
)
from infer.task_io import prepare_task_dirs, select_preview_keys, write_json, write_task_json
from infer.viz import align_mask, boundary_bgr, colorize_bgr, error_map_bgr, overlay_rgb, save_bgr_png, save_rgb_png

from apps.worker.student_exec import admit_version, infer_student_masks, measure_student_version

def _classify_fail(exc: BaseException) -> str:
    text = str(exc).lower()
    if isinstance(exc, FileNotFoundError):
        return "file"
    if isinstance(exc, MemoryError) or "out of memory" in text:
        return "resource"
    if "shape" in text or "size" in text or "channel" in text:
        return "shape"
    if "state_dict" in text or "load" in text:
        return "load"
    return "forward"


def _add_artifact(db: Session, task_id: str, rel_path: str, kind: str, sample_key: str | None, model_version_id: str | None) -> None:
    db.add(
        Artifact(
            id=new_id(),
            task_id=task_id,
            sample_key=sample_key,
            model_version_id=model_version_id,
            kind=kind,
            rel_path=rel_path.replace("\\", "/"),
        )
    )


def _display_name(db: Session, mv: ModelVersion | None) -> str:
    if mv is None:
        return "model"
    model_obj = db.get(Model, mv.model_id)
    if model_obj is not None:
        return model_obj.name
    return BUILTIN_DISPLAY_NAMES.get(mv.slug, "model")


def _try_write_cam(
    *,
    db: Session,
    task_id: str,
    task_dir: Path,
    module,
    slug: str | None,
    tensor,
    pred_small: np.ndarray,
    origin: np.ndarray,
    sample_key: str,
    model_version_id: str,
    num_classes: int,
) -> dict[int, np.ndarray]:
    """Builtin-only. A CAM failure must not fail the model or the task."""
    overlays: dict[int, np.ndarray] = {}
    try:
        layer = resolve_target_layer(module, slug=slug, num_classes=num_classes)
    except Exception:
        return overlays
    for class_id in cam_class_ids(num_classes):
        try:
            cam = compute_gradcam(
                module,
                tensor,  # type: ignore[arg-type]
                class_id=class_id,
                pred_mask=pred_small,
                target_layer=layer,
            )
            rgb = overlay_cam_rgb(origin, cam)
            rel = cam_artifact_rel(model_version_id, sample_key, class_id)
            save_rgb_png(task_dir / rel, rgb)
            _add_artifact(db, task_id, rel, "cam", sample_key, model_version_id)
            overlays[class_id] = rgb
        except Exception:
            continue
    return overlays


def _upsert_metric_set(db: Session, task: Task, payload: dict, n: int, scope: str) -> None:
    existing = db.query(MetricSet).filter(MetricSet.task_id == task.id).one_or_none()
    if existing is None:
        db.add(
            MetricSet(
                id=new_id(),
                task_id=task.id,
                scope=scope,
                n=n,
                payload_json=payload,
            )
        )
        return
    existing.scope = scope
    existing.n = n
    existing.payload_json = payload


def _run_options(task: Task, settings) -> dict:
    if task.type == "demo":
        return {
            "viz_limit": 0,
            "metric_scope": None,
            "include_acc": False,
        }
    if task.type == "eval":
        return {
            "viz_limit": int(settings.eval_montage_samples),
            "metric_scope": OFFICIAL_SPLIT_SCOPE,
            "include_acc": True,
        }
    return {
        "viz_limit": 0,
        "metric_scope": BATCH_REFERENCE_SCOPE,
        "include_acc": False,
    }


def run_compare(task_id: str) -> None:
    _run_task(task_id, expected_types=("compare",))


def run_eval(task_id: str) -> None:
    _run_task(task_id, expected_types=("eval",))


def run_demo(task_id: str) -> None:
    _run_task(task_id, expected_types=("demo",))


def run_classification(task_id: str) -> None:
    _run_task(task_id, expected_types=("classification",))


def run_pcb_segmentation(task_id: str) -> None:
    _run_task(task_id, expected_types=("pcb_segmentation",))


def run_pcb_classification(task_id: str) -> None:
    _run_task(task_id, expected_types=("pcb_classify",))


def _assert_lab_execution_authorized(db: Session, task: Task) -> None:
    """Validate the whole task before ANY executor runs, using current DB grants."""
    # Lock current grants until queued -> running commits. A concurrent revocation
    # is ordered either before this check or after the task has started.
    user = (
        db.query(User).filter(User.id == task.creator_id).populate_existing().with_for_update().one_or_none()
        if task.creator_id else None
    )
    if user is None or user.status != "active":
        raise AppError("任务创建者当前不可运行任务", code="TASK_ACTOR_UNAVAILABLE", stage="auth")
    if task.type in {"classification", "pcb_segmentation", "pcb_classify"}:
        # Classification's caller immediately checks its complete contract using
        # the same protocol -> model -> version lock order as builtin registration.
        return
    links = (
        db.query(TaskModel).filter(TaskModel.task_id == task.id)
        .order_by(TaskModel.model_version_id.asc()).populate_existing().with_for_update().all()
    )
    if not links:
        raise AppError("任务没有模型", code="NO_MODELS", stage="protocol")
    for link in links:
        version = (
            db.query(ModelVersion).filter(ModelVersion.id == link.model_version_id)
            .populate_existing().with_for_update().one_or_none()
        )
        if version is None:
            raise AppError("任务模型版本不存在", code="MODEL_NOT_FOUND", stage="protocol")
        model = (
            db.query(Model).filter(Model.id == version.model_id)
            .populate_existing().with_for_update().one_or_none()
        )
        assert_model_role_access(user, model, version, link.role)
        from app.services.models import is_other_scene_version
        if is_other_scene_version(db, version):
            raise AppError("该场景模型不能进入钢铁分割执行器", code="TASK_KIND_MISMATCH", stage="protocol")
        if version.status != "runnable":
            raise AppError("任务模型当前不可运行", code="MODEL_NOT_RUNNABLE", stage="protocol")
        if version.requires_cuda:
            raise AppError("当前 CPU 环境不可运行该模型", code="CUDA_REQUIRED", stage="resource")


def _run_task(task_id: str, expected_types: tuple[str, ...]) -> None:
    settings = get_settings()
    db = SessionLocal()
    owns_attempt = False
    started = False
    try:
        # Same parent order as API/rerun: actor -> dataset version -> task.
        # Serialize sample locks with submissions before locking any model grants.
        candidate = db.query(Task.creator_id, Task.dataset_version_id).filter(Task.id == task_id).first()
        if candidate is None:
            return
        if candidate.creator_id:
            db.query(User).filter_by(id=candidate.creator_id).with_for_update().one_or_none()
        lock_version(db, candidate.dataset_version_id)
        task = db.query(Task).filter(Task.id == task_id).populate_existing().with_for_update().one_or_none()
        if task is None:
            return
        if task.type not in expected_types:
            raise RuntimeError(f"job type mismatch: job={expected_types} task={task.type}")
        if task.status != "queued":
            return
        owns_attempt = True
        if task.type in {"compare", "eval", "classification", "pcb_segmentation", "pcb_classify"}:
            _assert_lab_execution_authorized(db, task)
        if task.type == "classification":
            from apps.worker.classification import assert_classification_execution
            assert_classification_execution(db, task, settings)
        if task.type == "pcb_classify":
            from apps.worker.pcb_classification import assert_execution
            assert_execution(db, task, settings)
        if task.type == "pcb_segmentation":
            from apps.worker.pcb_segmentation import assert_pcb_execution
            assert_pcb_execution(db, task, settings)
        verify_inputs(db, task, settings)
        task.error_summary = None
        task.status = "running"
        task.updated_at = utcnow()
        db.commit()
        started = True
        invalidate_after_write(task.id, task.creator_id)
        if task.type == "demo":
            _run_demo_body(db, task, settings)
        elif task.type == "classification":
            from apps.worker.classification import run_classification_body
            run_classification_body(db, task, settings)
        elif task.type == "pcb_classify":
            from apps.worker.pcb_classification import run_body
            run_body(db, task, settings)
        elif task.type == "pcb_segmentation":
            from apps.worker.pcb_segmentation import run_pcb_body
            run_pcb_body(db, task, settings)
        else:
            _run_compare_body(db, task, settings)
    except Exception as exc:
        failure = exc
        if expected_types == ("pcb_classify",) and isinstance(exc, JobTimeoutException):
            failure = AppError("PCB 分类任务超过执行时限，请再跑", code="PCB_CLS_JOB_TIMEOUT", stage="resource")
        if expected_types == ("pcb_segmentation",) and isinstance(exc, JobTimeoutException):
            # The first admission/permission check runs before the PCB body;
            # its deadline needs the same terminal metadata as a body timeout.
            failure = AppError("PCB 任务超过执行时限，请通过再跑创建新任务", code="PCB_JOB_TIMEOUT", stage="resource")
        db.rollback()
        # A failed lookup/lock is not ownership. After rollback another worker
        # may have claimed the queued task, so recheck under a current row lock.
        task = (db.query(Task).filter_by(id=task_id).populate_existing().with_for_update().one_or_none()
                if owns_attempt else None)
        if task is not None and task.status == ("running" if started else "queued"):
            task.status = "failed"
            task.error_summary = f"{failure.code}: {failure.message}" if isinstance(failure, AppError) else str(failure)
            if isinstance(failure, AppError):
                for link in db.query(TaskModel).filter(TaskModel.task_id == task.id).all():
                    link.status = "failed"
                    link.fail_stage = failure.stage
                    link.fail_message = task.error_summary
            task.updated_at = utcnow()
            db.commit()
            invalidate_after_write(task.id, task.creator_id)
        if failure is not exc:
            raise failure from exc
        raise
    finally:
        db.close()


def _run_compare_body(db: Session, task: Task, settings) -> None:
    if task.type not in {"compare", "eval"}:
        raise RuntimeError("compare worker refused non-segmentation task")
    _run_inference_visuals(db, task, settings, mode="lab")


def _run_demo_body(db: Session, task: Task, settings) -> None:
    if task.type != "demo":
        raise RuntimeError("demo worker refused non-demo task")
    assert_demo_worker_contract(db, task)
    task.has_gt = False
    _run_inference_visuals(db, task, settings, mode="demo")


def _run_inference_visuals(db: Session, task: Task, settings, *, mode: str) -> None:
    demo_mode = mode == "demo"
    if demo_mode and task.type != "demo":
        raise RuntimeError("demo visuals require type=demo")
    if not demo_mode and task.type == "demo":
        raise RuntimeError("lab visuals refused demo task")
    preprocess_row = db.get(PreprocessSpecRow, task.preprocess_id)
    if preprocess_row is None:
        raise RuntimeError("missing preprocess spec")
    spec = PreprocessSpec(
        height=preprocess_row.height,
        width=preprocess_row.width,
        apply_clahe=preprocess_row.apply_clahe,
        sp_threshold=preprocess_row.sp_threshold,
        dataset=preprocess_row.dataset,
        num_classes=4,
        in_channels=3,
    )
    task_dir = prepare_task_dirs(settings.storage_path, task.id)
    sample_links = (
        db.query(TaskSample).filter(TaskSample.task_id == task.id).order_by(TaskSample.sort_order.asc()).all()
    )
    samples: list[Sample] = []
    for link in sample_links:
        sample = db.get(Sample, link.sample_id)
        if sample is None:
            raise RuntimeError("missing sample")
        samples.append(sample)

    options = _run_options(task, settings)
    preview_keys = select_preview_keys([sample.sample_key for sample in samples], options["viz_limit"])
    preview_set = set(preview_keys)

    origins: dict[str, np.ndarray] = {}
    tensors: dict[str, object] = {}
    for sample in samples:
        path = resolve_uri(sample.origin_uri, settings)
        rgb = read_rgb(path)
        origins[sample.sample_key] = rgb
        tensors[sample.sample_key] = preprocess_rgb(rgb, spec)
        if sample.sample_key in preview_set:
            rel = f"origin/{sample.sample_key}.png"
            save_rgb_png(task_dir / rel, rgb)
            _add_artifact(db, task.id, rel, "origin", sample.sample_key, None)

    gt_masks: dict[str, np.ndarray] = {}
    score_gt = False if demo_mode else bool(task.has_gt)
    if demo_mode:
        if any(sample.mask_uri for sample in samples):
            raise RuntimeError("demo worker refused sample with mask_uri")
        score_gt = False
    if score_gt:
        if not all(sample.mask_uri for sample in samples):
            raise RuntimeError("task.has_gt but some samples have no mask")
        for sample in samples:
            gt_path = resolve_uri(sample.mask_uri, settings)
            gt = read_index_mask(gt_path)
            origin = origins[sample.sample_key]
            if gt.shape[0] != origin.shape[0] or gt.shape[1] != origin.shape[1]:
                raise RuntimeError(
                    f"GT size {gt.shape[1]}x{gt.shape[0]} != origin {origin.shape[1]}x{origin.shape[0]} for {sample.sample_key}"
                )
            gt_masks[sample.sample_key] = gt
            if sample.sample_key in preview_set:
                gt_rel = f"gt/{sample.sample_key}.png"
                save_bgr_png(task_dir / gt_rel, colorize_bgr(gt, dataset=spec.dataset, num_classes=spec.num_classes))
                _add_artifact(db, task.id, gt_rel, "gt", sample.sample_key, None)

    task_models = (
        db.query(TaskModel).filter(TaskModel.task_id == task.id).order_by(TaskModel.sort_order.asc()).all()
    )
    pred_masks: dict[str, dict[str, np.ndarray]] = {}
    cam_overlays: dict[str, dict[str, dict[int, np.ndarray]]] = {}
    successful_models: list[TaskModel] = []
    confmats: dict[str, object] = {}

    for tm in task_models:
        mv = db.get(ModelVersion, tm.model_version_id)
        model_row = db.get(Model, mv.model_id) if mv else None
        try:
            if mv is None:
                raise RuntimeError("model version missing")
            if mv.requires_cuda:
                raise RuntimeError("当前环境不可运行（需要 CUDA）")
            pred_by_sample: dict[str, np.ndarray]
            live_module = None
            if model_row and model_row.source == "student":
                if demo_mode:
                    raise RuntimeError("demo forbids student models")
                raw_preds = infer_student_masks(db, mv, settings, task_id=task.id, tensors=tensors)
                pred_by_sample = raw_preds
            elif model_row and model_row.source == "builtin":
                if mv.slug not in BUILTIN_SLUGS:
                    raise RuntimeError(f"unsupported slug {mv.slug}")
                weight = db.query(Weight).filter(Weight.version_id == mv.id).first()
                weight_path = resolve_uri(weight.file_uri, settings) if weight else None
                module = get_builtin_module(mv.id, mv.slug, weight_path, num_classes=mv.num_classes)
                if weight and weight.param_count is None:
                    weight.param_count = count_parameters(module)
                pred_by_sample = {
                    sample.sample_key: predict_mask(module, tensors[sample.sample_key])  # type: ignore[arg-type]
                    for sample in samples
                }
                live_module = module
            else:
                raise RuntimeError("模型来源无效，拒绝执行")
            pred_masks[mv.id] = {}
            if score_gt:
                confmats[mv.id] = empty_confmat(spec.num_classes)
            for sample in samples:
                mask_small = pred_by_sample[sample.sample_key]
                origin = origins[sample.sample_key]
                aligned = align_mask(mask_small, origin.shape[0], origin.shape[1])
                if sample.sample_key in preview_set:
                    pred_masks[mv.id][sample.sample_key] = aligned
                    color = colorize_bgr(aligned, dataset=spec.dataset, num_classes=mv.num_classes)
                    overlay = overlay_rgb(origin, aligned)
                    boundary = boundary_bgr(aligned, dataset=spec.dataset, num_classes=mv.num_classes)
                    pred_rel = f"pred/{mv.id}/{sample.sample_key}.png"
                    over_rel = f"overlay/{mv.id}/{sample.sample_key}.png"
                    bound_rel = f"boundary/{mv.id}/{sample.sample_key}.png"
                    save_bgr_png(task_dir / pred_rel, color)
                    save_rgb_png(task_dir / over_rel, overlay)
                    save_bgr_png(task_dir / bound_rel, boundary)
                    _add_artifact(db, task.id, pred_rel, "pred_color", sample.sample_key, mv.id)
                    _add_artifact(db, task.id, over_rel, "overlay", sample.sample_key, mv.id)
                    _add_artifact(db, task.id, bound_rel, "boundary", sample.sample_key, mv.id)
                    if score_gt:
                        err = error_map_bgr(aligned, gt_masks[sample.sample_key])
                        err_rel = f"error/{mv.id}/{sample.sample_key}.png"
                        save_bgr_png(task_dir / err_rel, err)
                        _add_artifact(db, task.id, err_rel, "error", sample.sample_key, mv.id)
                    if live_module is not None:
                        written = _try_write_cam(
                            db=db,
                            task_id=task.id,
                            task_dir=task_dir,
                            module=live_module,
                            slug=mv.slug,
                            tensor=tensors[sample.sample_key],
                            pred_small=mask_small,
                            origin=origin,
                            sample_key=sample.sample_key,
                            model_version_id=mv.id,
                            num_classes=mv.num_classes,
                        )
                        if written:
                            cam_overlays.setdefault(mv.id, {})[sample.sample_key] = written
                if score_gt:
                    confmats[mv.id] = add_to_confmat(
                        confmats[mv.id], aligned, gt_masks[sample.sample_key], spec.num_classes
                    )  # type: ignore[arg-type]
            tm.status = "success"
            tm.fail_stage = None
            tm.fail_message = None
            successful_models.append(tm)
        except Exception as exc:
            tm.status = "failed"
            tm.fail_stage = _classify_fail(exc)
            tm.fail_message = str(exc)
            confmats.pop(tm.model_version_id, None)

    for sample in samples:
        if sample.sample_key not in preview_set:
            continue
        origin_bgr = cv2.cvtColor(origins[sample.sample_key], cv2.COLOR_RGB2BGR)
        mask_panels: list[tuple[str, np.ndarray]] = [("origin", origin_bgr)]
        overlay_panels: list[tuple[str, np.ndarray]] = [("origin", origin_bgr)]
        error_panels: list[tuple[str, np.ndarray]] = [("origin", origin_bgr)]
        if score_gt:
            gt = gt_masks[sample.sample_key]
            gt_color = colorize_bgr(gt, dataset=spec.dataset, num_classes=spec.num_classes)
            mask_panels.append(("GT", gt_color))
            overlay_panels.append(("GT", cv2.cvtColor(overlay_rgb(origins[sample.sample_key], gt), cv2.COLOR_RGB2BGR)))
            error_panels.append(("GT", gt_color))
        for tm in task_models:
            mv = db.get(ModelVersion, tm.model_version_id)
            name = _display_name(db, mv)
            if tm.status != "success" or mv is None:
                continue
            aligned = pred_masks[mv.id][sample.sample_key]
            mask_panels.append((name, colorize_bgr(aligned)))
            overlay_panels.append((name, cv2.cvtColor(overlay_rgb(origins[sample.sample_key], aligned), cv2.COLOR_RGB2BGR)))
            if score_gt:
                error_panels.append((name, error_map_bgr(aligned, gt_masks[sample.sample_key])))
        mask_rel = f"montage/{sample.sample_key}__mask.png"
        over_rel = f"montage/{sample.sample_key}__overlay.png"
        save_bgr_png(task_dir / mask_rel, build_row(mask_panels))
        save_bgr_png(task_dir / over_rel, build_row(overlay_panels))
        _add_artifact(db, task.id, mask_rel, "montage", sample.sample_key, None)
        _add_artifact(db, task.id, over_rel, "montage", sample.sample_key, None)
        if score_gt and len(error_panels) > 1:
            err_rel = f"montage/{sample.sample_key}__error.png"
            save_bgr_png(task_dir / err_rel, build_row(error_panels))
            _add_artifact(db, task.id, err_rel, "montage", sample.sample_key, None)
        for class_id in cam_class_ids(spec.num_classes):
            cam_panels: list[tuple[str, np.ndarray]] = [("origin", origin_bgr)]
            for tm in task_models:
                mv = db.get(ModelVersion, tm.model_version_id)
                name = _display_name(db, mv)
                if tm.status != "success" or mv is None:
                    continue
                rgb = cam_overlays.get(mv.id, {}).get(sample.sample_key, {}).get(class_id)
                if rgb is None:
                    continue
                cam_panels.append((name, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)))
            if len(cam_panels) <= 1:
                continue
            cam_rel = cam_montage_rel(sample.sample_key, class_id)
            save_bgr_png(task_dir / cam_rel, build_row(cam_panels))
            _add_artifact(db, task.id, cam_rel, "montage", sample.sample_key, None)

    if score_gt and successful_models and not demo_mode:
        model_payload = []
        for tm in successful_models:
            mv = db.get(ModelVersion, tm.model_version_id)
            if mv is None or mv.id not in confmats:
                continue
            scored = metrics_dict_from_confmat(
                confmats[mv.id],  # type: ignore[arg-type]
                NEU_CLASS_MAP,
                include_acc=bool(options["include_acc"]),
            )
            model_payload.append(
                {
                    "model_version_id": mv.id,
                    "name": _display_name(db, mv),
                    "slug": mv.slug,
                    "role": tm.role,
                    "n": len(samples),
                    **scored,
                }
            )
        if model_payload:
            metrics_payload = build_metric_payload(
                n=len(samples),
                models=model_payload,
                class_map=NEU_CLASS_MAP,
                scope=str(options["metric_scope"]),
            )
            write_json(task_dir / "metrics.json", metrics_payload)
            _upsert_metric_set(db, task, metrics_payload, n=len(samples), scope=str(options["metric_scope"]))

    model_info = []
    for tm in task_models:
        mv = db.get(ModelVersion, tm.model_version_id)
        model = db.get(Model, mv.model_id) if mv else None
        weight = db.query(Weight).filter(Weight.version_id == mv.id).first() if mv else None
        model_info.append(
            {
                "role": tm.role,
                "name": model.name if model else None,
                "slug": mv.slug if mv else None,
                "version_id": mv.id if mv else None,
                "status": tm.status,
                "fail_stage": tm.fail_stage,
                "weight_sha256": weight.sha256 if weight else None,
                "param_count": weight.param_count if weight else None,
                "requires_cuda": mv.requires_cuda if mv else None,
            }
        )
    env = {
        "device": "cpu",
        "platform": platform.platform(),
        "python": platform.python_version(),
    }
    try:
        import torch

        env["torch"] = torch.__version__
    except Exception:
        env["torch"] = "unavailable"

    input_manifest = verify_inputs(db, task, settings)
    task_payload = {
        "inputs": input_manifest,
        "task_id": task.id,
        "type": task.type,
        "has_gt": False if demo_mode else bool(task.has_gt),
        "preprocess_id": task.preprocess_id,
        "preprocess": spec.to_dict(),
        "models": model_info,
        "samples": [s.sample_key for s in samples],
        "preview_sample_keys": preview_keys,
        "display_align": "original_size",
        "environment": env,
    }
    if demo_mode:
        task_payload["disclaimer"] = DEMO_DISCLAIMER
        task_payload.pop("metrics", None)
    task_payload["cam_disclaimer"] = CAM_DISCLAIMER
    write_task_json(task_dir, task_payload)
    _add_artifact(db, task.id, "task.json", "log", None, None)
    write_bundle(db, task, settings)
    _add_artifact(db, task.id, "bundle.zip", "bundle", None, None)

    failed = [tm for tm in task_models if tm.status != "success"]
    succeeded = [tm for tm in task_models if tm.status == "success"]
    if not succeeded:
        task.status = "failed"
        task.error_summary = "; ".join(f"{tm.fail_stage}:{tm.fail_message}" for tm in failed)
    elif failed:
        task.status = "partial_success"
        task.error_summary = "; ".join(f"{tm.fail_stage}:{tm.fail_message}" for tm in failed)
    else:
        task.status = "success"
        task.error_summary = None
    task.updated_at = utcnow()
    db.commit()
    invalidate_after_write(task.id, task.creator_id)


def run_admit(version_id: str) -> None:
    settings = get_settings()
    db = SessionLocal()
    started = False
    source_hash = None
    try:
        version = db.query(ModelVersion).filter_by(id=version_id).populate_existing().with_for_update().one_or_none()
        if version is None:
            return
        current = get_current_job()
        expected_job = f"admit-{version.id}-{(version.source_sha256 or chr(45))[:16]}"
        if current is not None and current.id != expected_job:
            return
        if version.fail_stage == "admit_running" or version.status not in {"uploaded", "checking"}:
            return
        source_hash = version.source_sha256
        version.status = "checking"
        version.fail_stage = "admit_running"
        version.fail_message = "隔离检查执行中"
        db.commit()
        started = True
        model = db.get(Model, version.model_id)
        admit_version(db, version, settings)
        db.commit()
        invalidate_after_write(None, model.owner_id if model else None)
    except Exception as exc:
        db.rollback()
        version = (db.query(ModelVersion).filter_by(id=version_id).populate_existing().with_for_update().one_or_none()
                   if started else None)
        if (version is not None and version.status == "checking" and version.fail_stage == "admit_running"
                and version.source_sha256 == source_hash):
            version.status = "cannot_start"
            version.fail_stage = "resource"
            version.fail_message = str(exc)
            db.commit()
            model = db.get(Model, version.model_id)
            invalidate_after_write(None, model.owner_id if model else None)
        raise
    finally:
        db.close()


def run_perf(version_id: str) -> None:
    settings = get_settings()
    db = SessionLocal()
    started = False
    claimed_job_id = None
    try:
        from app.services.perf import apply_measure_result, get_or_create_profile, mark_measure_failed
        from infer.perf import measure_builtin

        version = db.query(ModelVersion).filter_by(id=version_id).populate_existing().with_for_update().one_or_none()
        if version is None:
            return
        model = db.get(Model, version.model_id)
        if model is None:
            return
        profile = get_or_create_profile(db, version)
        current = get_current_job()
        if profile.status != "queued" or (current is not None and current.id != profile.job_id):
            return
        claimed_job_id = profile.job_id
        profile.status = "measuring"
        profile.fail_message = None
        db.commit()
        started = True
        invalidate_models_lists()
        from app.services.models import is_other_scene_version
        if is_other_scene_version(db, version):
            mark_measure_failed(db, version, model, "该场景模型不能使用钢铁分割测参执行器。")
            db.commit()
            invalidate_models_lists()
            return
        if version.status != "runnable" or version.requires_cuda:
            mark_measure_failed(db, version, model, "只有当前环境可运行的版本才能测量。")
            db.commit()
            invalidate_models_lists()
            return
        if model.source == "student":
            payload = measure_student_version(db, version, settings)
        else:
            weight = db.query(Weight).filter(Weight.version_id == version.id).first()
            if weight is None:
                raise RuntimeError("缺少权重记录")
            weight_path = resolve_uri(weight.file_uri, settings)
            payload = measure_builtin(
                version_id=version.id,
                slug=version.slug,
                weight_path=weight_path,
                num_classes=version.num_classes,
                in_channels=version.in_channels,
                height=version.input_h,
                width=version.input_w,
            )
        apply_measure_result(db, version, model, payload, settings=settings)
        db.commit()
        invalidate_models_lists()
        invalidate_after_write(None, model.owner_id)
    except Exception as exc:
        db.rollback()
        if started:
            from app.services.perf import _load_profile, mark_measure_failed

            # Same version -> profile order as submission; never fail a newer job.
            version = db.query(ModelVersion).filter_by(id=version_id).populate_existing().with_for_update().one_or_none()
            profile = _load_profile(db, version_id) if version is not None else None
            if profile is not None and profile.status == "measuring" and profile.job_id == claimed_job_id:
                model = db.get(Model, version.model_id)
                if model is not None:
                    mark_measure_failed(db, version, model, str(exc))
                    db.commit()
                    invalidate_models_lists()
                    invalidate_after_write(None, model.owner_id)
        raise
    finally:
        db.close()
