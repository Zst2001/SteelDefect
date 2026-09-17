from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from admit.scan import format_static_failure, scan_student_source
from app.cache import invalidate_after_write, rq_connection
from app.config import Settings, get_settings
from app.db.models import Model, ModelVersion, PreprocessSpecRow, User, Weight
from app.errors import AppError
from app.services.storage import sha256_file
from app.util_time import new_id
from rq import Queue

ENTRY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
NAME_RE = re.compile(r"^[\w\u4e00-\u9fff][\w\u4e00-\u9fff\-_. ]{0,80}$")
BANNED_SUFFIXES = {
    ".exe",
    ".dll",
    ".so",
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".7z",
    ".rar",
    ".bat",
    ".cmd",
    ".ps1",
    ".sh",
    ".msi",
}


def model_dir(settings: Settings, version_id: str) -> Path:
    return settings.storage_path / "models" / version_id


def write_report(settings: Settings, version_id: str, payload: dict) -> None:
    root = model_dir(settings, version_id)
    root.mkdir(parents=True, exist_ok=True)
    (root / "admit_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def read_report(settings: Settings, version_id: str) -> dict | None:
    path = model_dir(settings, version_id) / "admit_report.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _slug(name: str) -> str:
    ascii_part = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32]
    return ascii_part or "student"


async def import_student_model(
    db: Session,
    user: User,
    *,
    name: str,
    entry_symbol: str,
    num_classes: int,
    in_channels: int,
    requires_cuda: bool,
    py_file: UploadFile,
    pth_file: UploadFile,
    settings: Settings | None = None,
) -> ModelVersion:
    settings = settings or get_settings()
    name = (name or "").strip()
    entry_symbol = (entry_symbol or "build_model").strip()
    if not NAME_RE.match(name):
        raise AppError("模型名不合法", code="BAD_NAME", stage="file", status_code=400)
    if not ENTRY_RE.match(entry_symbol):
        raise AppError("入口符号必须是合法标识符", code="BAD_ENTRY", stage="file", status_code=400)
    if num_classes < 2 or num_classes > 32:
        raise AppError("类别数须在 2–32", code="BAD_CLASSES", stage="protocol", status_code=400)
    if in_channels not in {1, 3}:
        raise AppError("输入通道只支持 1 或 3", code="BAD_CHANNELS", stage="protocol", status_code=400)

    py_name = Path(py_file.filename or "model.py").name
    pth_name = Path(pth_file.filename or "weights.pth").name
    py_ext = Path(py_name).suffix.lower()
    pth_ext = Path(pth_name).suffix.lower()
    if py_ext != ".py":
        raise AppError("源码必须是单个 .py 文件", code="BAD_TYPE", stage="file", status_code=400)
    if pth_ext not in {".pth", ".pt"}:
        raise AppError("权重必须是 .pth / .pt", code="BAD_TYPE", stage="file", status_code=400)
    if py_ext in BANNED_SUFFIXES or pth_ext in BANNED_SUFFIXES:
        raise AppError("拒绝可执行文件或压缩包", code="BAD_TYPE", stage="file", status_code=400)

    py_bytes = await py_file.read()
    pth_bytes = await pth_file.read()
    if not py_bytes or not pth_bytes:
        raise AppError("源码或权重为空", code="EMPTY_FILE", stage="file", status_code=400)
    if len(py_bytes) > settings.max_py_bytes:
        raise AppError("源码超过大小上限", code="FILE_TOO_LARGE", stage="file", status_code=400)
    if len(pth_bytes) > settings.max_pth_bytes:
        raise AppError("权重超过大小上限", code="FILE_TOO_LARGE", stage="file", status_code=400)
    if py_bytes[:2] == b"PK" or py_bytes[:4] == b"\x7fELF" or py_bytes[:2] == b"MZ":
        raise AppError("源码不是文本 Python 文件", code="BAD_TYPE", stage="file", status_code=400)

    try:
        source_text = py_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AppError("源码必须是 UTF-8 文本", code="BAD_ENCODING", stage="file", status_code=400) from exc

    preprocess = db.query(PreprocessSpecRow).filter(PreprocessSpecRow.name == "neu_200").one()
    version_id = new_id()
    dest = model_dir(settings, version_id)
    dest.mkdir(parents=True, exist_ok=True)
    py_path = dest / "model.py"
    pth_path = dest / "weights.pth"
    py_path.write_bytes(py_bytes)
    pth_path.write_bytes(pth_bytes)

    model = Model(id=new_id(), owner_id=user.id, name=name, source="student")
    version = ModelVersion(
        id=version_id,
        model_id=model.id,
        slug=f"{_slug(name)}-{version_id[:8]}",
        entry_symbol=entry_symbol,
        num_classes=num_classes,
        in_channels=in_channels,
        input_h=preprocess.height,
        input_w=preprocess.width,
        preprocess_id=preprocess.id,
        requires_cuda=requires_cuda,
        status="uploaded",
        fail_stage=None,
        fail_message=None,
        source_sha256=sha256_file(py_path),
        visibility="private",
    )
    weight = Weight(
        id=new_id(),
        version_id=version.id,
        file_uri=f"data:models/{version.id}/weights.pth",
        sha256=sha256_file(pth_path),
        param_count=None,
    )
    db.add(model)
    db.add(version)
    db.add(weight)
    db.flush()

    issues = scan_student_source(source_text, filename=py_name)
    stages = [{"stage": "file", "ok": True, "message": "已隔离保存并计算哈希"}]
    if issues:
        message = format_static_failure(issues)
        version.status = "cannot_start"
        version.fail_stage = "static"
        version.fail_message = message
        stages.append({"stage": "static", "ok": False, "message": message})
        write_report(
            settings,
            version.id,
            {
                "version_id": version.id,
                "status": version.status,
                "fail_stage": "static",
                "message": message,
                "stages": stages,
            },
        )
        db.commit()
        invalidate_after_write(None, user.id)
        return version

    stages.append({"stage": "static", "ok": True, "message": "未发现阻断调用"})
    if requires_cuda:
        message = "当前环境为 CPU，该模型标明需要 CUDA，不可运行。不会静默改用随机权重。"
        version.status = "cannot_start"
        version.fail_stage = "resource"
        version.fail_message = message
        stages.append({"stage": "resource", "ok": False, "message": message})
        write_report(
            settings,
            version.id,
            {
                "version_id": version.id,
                "status": version.status,
                "fail_stage": "resource",
                "message": message,
                "stages": stages,
            },
        )
        db.commit()
        invalidate_after_write(None, user.id)
        return version

    version.status = "checking"
    write_report(
        settings,
        version.id,
        {
            "version_id": version.id,
            "status": "checking",
            "fail_stage": None,
            "message": "排队隔离检查",
            "stages": stages,
        },
    )
    db.commit()
    invalidate_after_write(None, user.id)
    queue = Queue(settings.rq_queue_name, connection=rq_connection())
    queue.enqueue(
        "apps.worker.jobs.run_admit",
        version.id,
        job_timeout=settings.admit_job_timeout_sec,
        result_ttl=86400,
        failure_ttl=86400,
    )
    return version
