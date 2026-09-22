from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from admit.dockerutil import DockerUnavailable, run_student_container
from admit.sanitize import sanitize_text
from admit.scan import format_static_failure, scan_student_file
from app.config import Settings
from app.db.models import ModelVersion, Weight
from app.services.import_model import model_dir, write_report


def _admit_code_dir(settings: Settings) -> Path | None:
    path = settings.repo_root / "packages" / "admit"
    return path if path.is_dir() else None


def _link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _write_log(path: Path, text: str, extra: list[Path]) -> None:
    path.write_text(sanitize_text(text, extra_paths=extra), encoding="utf-8")


def admit_version(db: Session, version: ModelVersion, settings: Settings) -> None:
    root = model_dir(settings, version.id)
    py_path = root / "model.py"
    stages = [{"stage": "file", "ok": True, "message": "已隔离保存并计算哈希"}]
    issues = scan_student_file(str(py_path))
    if issues:
        message = format_static_failure(issues)
        _mark(db, version, settings, "cannot_start", "static", message, stages + [
            {"stage": "static", "ok": False, "message": message}
        ])
        return
    stages.append({"stage": "static", "ok": True, "message": "未发现阻断调用"})
    if version.requires_cuda:
        message = "当前环境为 CPU，该模型标明需要 CUDA，不可运行。不会静默改用随机权重。"
        _mark(db, version, settings, "cannot_start", "resource", message, stages + [
            {"stage": "resource", "ok": False, "message": message}
        ])
        return

    manifest = {
        "mode": "admit",
        "source_name": "model.py",
        "weight_name": "weights.pth",
        "entry_symbol": version.entry_symbol or "build_model",
        "num_classes": version.num_classes,
        "in_channels": version.in_channels,
        "input_h": version.input_h,
        "input_w": version.input_w,
    }
    in_dir = root / "admit_in"
    out_dir = root / "admit_out"
    if in_dir.exists():
        shutil.rmtree(in_dir, ignore_errors=True)
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    _link_or_copy(py_path, in_dir / "model.py")
    _link_or_copy(root / "weights.pth", in_dir / "weights.pth")
    (in_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        payload = run_student_container(
            image=settings.student_image,
            mode="admit",
            in_dir=in_dir,
            out_dir=out_dir,
            timeout_sec=min(settings.admit_job_timeout_sec, 300),
            extra_paths=[root, settings.storage_path, settings.repo_root],
            code_dir=_admit_code_dir(settings),
        )
    except DockerUnavailable as exc:
        message = str(exc)
        _mark(db, version, settings, "cannot_start", "resource", message, stages + [
            {"stage": "resource", "ok": False, "message": message}
        ], log=message)
        return

    log = str(payload.get("log") or "")
    if payload.get("ok"):
        weight = db.query(Weight).filter(Weight.version_id == version.id).first()
        if weight is not None and payload.get("param_count") is not None:
            weight.param_count = int(payload["param_count"])
        stages.extend(
            [
                {"stage": "import", "ok": True, "message": "隔离 import 成功"},
                {"stage": "build", "ok": True, "message": "已实例化 nn.Module"},
                {"stage": "load", "ok": True, "message": "strict load_state_dict 成功"},
                {"stage": "forward", "ok": True, "message": "dummy 前向输出形状合法"},
            ]
        )
        _mark(db, version, settings, "runnable", None, "检查通过", stages, log=log, extra={"param_count": payload.get("param_count")})
        return

    stage = str(payload.get("fail_stage") or "resource")
    message = str(payload.get("message") or "隔离检查失败")
    stages.append({"stage": stage, "ok": False, "message": message})
    _mark(db, version, settings, "cannot_start", stage, message, stages, log=log)


def infer_student_masks(
    db: Session,
    version: ModelVersion,
    settings: Settings,
    *,
    task_id: str,
    tensors: dict[str, object],
) -> dict[str, np.ndarray]:
    root = model_dir(settings, version.id)
    work = settings.storage_path / "tasks" / task_id / "student" / version.id
    in_dir = work / "in"
    out_dir = work / "out"
    if in_dir.exists():
        shutil.rmtree(in_dir, ignore_errors=True)
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    tensor_dir = in_dir / "tensors"
    tensor_dir.mkdir(parents=True, exist_ok=True)
    _link_or_copy(root / "model.py", in_dir / "model.py")
    _link_or_copy(root / "weights.pth", in_dir / "weights.pth")
    keys = list(tensors.keys())
    for key, tensor in tensors.items():
        array = tensor.detach().cpu().numpy() if hasattr(tensor, "detach") else np.asarray(tensor)
        np.save(tensor_dir / f"{key}.npy", array.astype(np.float32))
    manifest = {
        "mode": "infer",
        "source_name": "model.py",
        "weight_name": "weights.pth",
        "entry_symbol": version.entry_symbol or "build_model",
        "num_classes": version.num_classes,
        "in_channels": version.in_channels,
        "sample_keys": keys,
    }
    (in_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    payload = run_student_container(
        image=settings.student_image,
        mode="infer",
        in_dir=in_dir,
        out_dir=out_dir,
        timeout_sec=min(settings.student_infer_timeout_sec, 60 + 8 * max(len(keys), 1)),
        extra_paths=[work, settings.storage_path],
        code_dir=_admit_code_dir(settings),
    )
    if not payload.get("ok"):
        stage = str(payload.get("fail_stage") or "forward")
        raise RuntimeError(f"{stage}:{payload.get('message') or '学生模型隔离推理失败'}")
    preds: dict[str, np.ndarray] = {}
    for key in keys:
        path = out_dir / "preds" / f"{key}.npy"
        if not path.is_file():
            raise RuntimeError(f"shape:缺少 {key} 的预测")
        preds[key] = np.load(path)
    return preds


def measure_student_version(db: Session, version: ModelVersion, settings: Settings) -> dict:
    root = model_dir(settings, version.id)
    work = settings.storage_path / "perf" / version.id
    in_dir = work / "in"
    out_dir = work / "out"
    if in_dir.exists():
        shutil.rmtree(in_dir, ignore_errors=True)
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    _link_or_copy(root / "model.py", in_dir / "model.py")
    _link_or_copy(root / "weights.pth", in_dir / "weights.pth")
    manifest = {
        "mode": "perf",
        "source_name": "model.py",
        "weight_name": "weights.pth",
        "entry_symbol": version.entry_symbol or "build_model",
        "num_classes": version.num_classes,
        "in_channels": version.in_channels,
        "input_h": version.input_h,
        "input_w": version.input_w,
    }
    (in_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    payload = run_student_container(
        image=settings.student_image,
        mode="perf",
        in_dir=in_dir,
        out_dir=out_dir,
        timeout_sec=min(settings.perf_job_timeout_sec, 300),
        extra_paths=[root, work, settings.storage_path, settings.repo_root],
        code_dir=_admit_code_dir(settings),
    )
    if not payload.get("ok"):
        stage = str(payload.get("fail_stage") or "resource")
        message = str(payload.get("message") or "隔离测量失败")
        raise RuntimeError(f"{stage}:{message}")
    return payload


def _mark(
    db: Session,
    version: ModelVersion,
    settings: Settings,
    status: str,
    fail_stage: str | None,
    message: str,
    stages: list[dict],
    *,
    log: str = "",
    extra: dict | None = None,
) -> None:
    version.status = status
    version.fail_stage = fail_stage
    version.fail_message = None if status == "runnable" else message
    payload = {
        "version_id": version.id,
        "status": status,
        "fail_stage": fail_stage,
        "message": message if status != "runnable" else "检查通过",
        "stages": stages,
        **(extra or {}),
    }
    write_report(settings, version.id, payload)
    _write_log(
        model_dir(settings, version.id) / "admit.log",
        log or message,
        [model_dir(settings, version.id), settings.storage_path, settings.repo_root],
    )
    db.flush()
