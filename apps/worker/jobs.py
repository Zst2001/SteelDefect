from __future__ import annotations

import platform
import zipfile
from pathlib import Path

import cv2
import numpy as np
from sqlalchemy.orm import Session

from app.bootstrap import ROOT  # noqa: F401
from app.cache import invalidate_after_write
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
    Weight,
)
from app.db.session import SessionLocal
from app.services.storage import resolve_uri
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
    NEU_CLASS_MAP,
    OFFICIAL_SPLIT_SCOPE,
    PreprocessSpec,
)
from infer.task_io import prepare_task_dirs, select_preview_keys, write_json, write_task_json
from infer.viz import align_mask, boundary_bgr, colorize_bgr, error_map_bgr, overlay_rgb, save_bgr_png, save_rgb_png

from apps.worker.student_exec import admit_version, infer_student_masks

BUNDLE_FOLDERS = ("origin", "gt", "pred", "overlay", "boundary", "error", "montage")


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


def _write_bundle(task_dir: Path) -> None:
    bundle = task_dir / "bundle.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for folder in BUNDLE_FOLDERS:
            root = task_dir / folder
            if not root.exists():
                continue
            for file_path in root.rglob("*"):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() == ".pdf" or file_path.name.lower() == "metrics.json":
                    continue
                zf.write(file_path, file_path.relative_to(task_dir).as_posix())
        task_json = task_dir / "task.json"
        if task_json.is_file():
            zf.write(task_json, "task.json")
        # metrics.json stays out of the Draw.io bundle; it is not a layer.


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
    _run_task(task_id)


def run_eval(task_id: str) -> None:
    _run_task(task_id)


def _run_task(task_id: str) -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).with_for_update().one_or_none()
        if task is None:
            return
        if task.status in {"success", "failed", "partial_success"}:
            return
        task.status = "running"
        task.updated_at = utcnow()
        db.commit()
        invalidate_after_write(task.id, task.creator_id)
        _run_compare_body(db, task, settings)
    except Exception as exc:
        db.rollback()
        task = db.get(Task, task_id)
        if task is not None:
            task.status = "failed"
            task.error_summary = str(exc)
            task.updated_at = utcnow()
            db.commit()
            invalidate_after_write(task.id, task.creator_id)
        raise
    finally:
        db.close()


def _run_compare_body(db: Session, task: Task, settings) -> None:
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
    score_gt = bool(task.has_gt)
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
            if model_row and model_row.source == "student":
                raw_preds = infer_student_masks(db, mv, settings, task_id=task.id, tensors=tensors)
                pred_by_sample = raw_preds
            else:
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

    if score_gt and successful_models:
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

    task_payload = {
        "task_id": task.id,
        "type": task.type,
        "has_gt": bool(task.has_gt),
        "preprocess_id": task.preprocess_id,
        "preprocess": spec.to_dict(),
        "models": model_info,
        "samples": [s.sample_key for s in samples],
        "preview_sample_keys": preview_keys,
        "display_align": "original_size",
        "environment": env,
    }
    write_task_json(task_dir, task_payload)
    _add_artifact(db, task.id, "task.json", "log", None, None)
    _write_bundle(task_dir)
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
    try:
        version = db.get(ModelVersion, version_id)
        if version is None:
            return
        if version.status not in {"uploaded", "checking"}:
            return
        version.status = "checking"
        db.commit()
        model = db.get(Model, version.model_id)
        admit_version(db, version, settings)
        db.commit()
        invalidate_after_write(None, model.owner_id if model else None)
    except Exception as exc:
        db.rollback()
        version = db.get(ModelVersion, version_id)
        if version is not None:
            version.status = "cannot_start"
            version.fail_stage = "resource"
            version.fail_message = str(exc)
            db.commit()
            model = db.get(Model, version.model_id)
            invalidate_after_write(None, model.owner_id if model else None)
        raise
    finally:
        db.close()
