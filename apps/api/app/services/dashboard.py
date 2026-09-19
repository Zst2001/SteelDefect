from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from app.db.models import Model, ModelVersion, Task, User
from app.services.tasks import TASK_TYPE_LABELS

NOTICES = [
    {
        "id": "v1-scope",
        "level": "info",
        "text": "第一版已开放内置对比、学生导入检查、配对掩码后的快速对比参考指标，以及基于预置 NEU-20 的正式评测（不是论文完整 test split）。网站不做训练。",
    }
]

ACTIVE_STATUSES = {"queued", "running"}
DONE_FOR_BUNDLE = {"success", "partial_success"}


def _task_payload(task: Task) -> dict:
    return {
        "id": task.id,
        "type": task.type,
        "type_label": TASK_TYPE_LABELS.get(task.type, task.type),
        "status": task.status,
        "has_gt": task.has_gt,
        "error_summary": task.error_summary,
        "bundle_ready": task.status in DONE_FOR_BUNDLE,
        "created_at": task.created_at.isoformat() + "Z",
    }


def _model_brief(version: ModelVersion, model: Model) -> dict:
    return {
        "id": version.id,
        "name": model.name,
        "source": model.source,
        "status": version.status,
        "fail_stage": version.fail_stage,
        "requires_cuda": version.requires_cuda,
    }


def build_dashboard(db: Session, user: User) -> dict:
    tasks = (
        db.query(Task)
        .filter(Task.creator_id == user.id)
        .order_by(Task.created_at.desc())
        .limit(20)
        .all()
    )
    payload_tasks = [_task_payload(task) for task in tasks]
    recent_versions = (
        db.query(ModelVersion)
        .options(selectinload(ModelVersion.model))
        .join(Model, Model.id == ModelVersion.model_id)
        .filter(Model.source == "student", Model.owner_id == user.id)
        .order_by(ModelVersion.created_at.desc())
        .limit(8)
        .all()
    )
    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "role_label": "导师" if user.role == "advisor" else "学生",
        },
        "notices": list(NOTICES),
        "active_tasks": [row for row in payload_tasks if row["status"] in ACTIVE_STATUSES],
        "failed_tasks": [row for row in payload_tasks if row["status"] == "failed"][:8],
        "recent_tasks": payload_tasks[:10],
        "recent_models": [_model_brief(version, version.model) for version in recent_versions],
    }
