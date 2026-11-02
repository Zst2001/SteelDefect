from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from app.db.models import AuditLog, ModelVersion, Sample, Task, TaskModel, TaskSample, User
from app.errors import AppError
from app.config import get_settings
from app.services.task_artifacts import TaskArtifacts
from app.services.demo import create_demo_task
from app.services.demo_identity import DemoIdentity
from app.services.tasks import (
    TASK_TYPE_LABELS,
    _can_view_task,
    create_compare_task,
    create_eval_task,
    get_visible_task,
)
from app.util_time import new_id, utcnow

DONE = {"success", "partial_success"}
LAB_TYPES = {"compare", "eval", "classification", "pcb_segmentation", "pcb_classify"}
PAGE_SIZE_MAX = 50


def _iso(value) -> str | None:
    return value.isoformat() + "Z" if value else None


def _require_owner(task: Task, user: User) -> None:
    if task.creator_id != user.id:
        raise AppError("只能操作本人任务", code="FORBIDDEN", stage="auth", status_code=403)


def _locked_visible_record(db: Session, task_id: str, user: User) -> Task:
    # Authorize before locking, then refresh and recheck after acquiring the row.
    # A withdrawal/read/archive can have committed since the first visibility check.
    get_visible_task(db, task_id, user)
    task = (db.query(Task).filter_by(id=task_id).populate_existing()
            .with_for_update().one_or_none())
    if task is None or not _can_view_task(task, user):
        raise AppError("任务不存在", code="NOT_FOUND", stage="auth", status_code=404)
    return task


def _write_audit(db: Session, *, actor_id: str, action: str, target_id: str, reason: str) -> None:
    db.add(
        AuditLog(
            id=new_id(),
            actor_id=actor_id,
            action=action,
            target_type="task",
            target_id=target_id,
            reason=reason,
            created_at=utcnow(),
        )
    )


def _creator_name(db: Session, task: Task) -> str | None:
    if not task.creator_id:
        return None
    owner = db.get(User, task.creator_id)
    return owner.username if owner else None


def record_flags(task: Task, user: User) -> dict:
    owner = task.creator_id == user.id
    submitted = task.submitted_to_advisor_at is not None
    return {
        "note": task.note or "",
        "archived": bool(task.archived),
        "submitted_to_advisor_at": _iso(task.submitted_to_advisor_at),
        "advisor_seen_at": _iso(task.advisor_seen_at),
        "can_submit": (
            owner
            and task.type in LAB_TYPES
            and task.status in DONE
            and not task.archived
            and not submitted
        ),
        "can_withdraw": owner and submitted and task.advisor_seen_at is None,
        "can_rerun": owner and not task.archived and task.type in LAB_TYPES | {"demo"},
        "can_archive": owner,
        "can_note": owner,
        "can_analyze": task.type in {"compare", "eval"} and task.status in DONE,
    }


def serialize_record(db: Session, task: Task, user: User) -> dict:
    flags = record_flags(task, user)
    n = len(task.samples) if task.samples is not None else 0
    return {
        "id": task.id,
        "type": task.type,
        "type_label": TASK_TYPE_LABELS.get(task.type, task.type),
        "status": task.status,
        "has_gt": bool(task.has_gt) if task.type != "demo" else False,
        "error_summary": task.error_summary,
        **TaskArtifacts(db, task, get_settings()).bundle_state(),
        "created_at": _iso(task.created_at),
        "creator_id": task.creator_id,
        "creator_username": _creator_name(db, task),
        "n": n,
        "open_path": _open_path(task),
        **flags,
    }


def _open_path(task: Task) -> str:
    if task.type == "pcb_classify":
        return f"/inspect/pcb/classification/tasks/{task.id}"
    if task.type == "pcb_segmentation":
        return f"/inspect/pcb/tasks/{task.id}"
    if task.type == "classification":
        return f"/classification/{task.id}"
    if task.type == "eval":
        return f"/eval/{task.id}"
    if task.type == "demo":
        return f"/demo/{task.id}"
    return f"/compare/{task.id}"


def maybe_mark_advisor_seen(db: Session, task: Task, user: User) -> None:
    if user.role != "advisor":
        return
    task = _locked_visible_record(db, task.id, user)
    if task.submitted_to_advisor_at is None or task.advisor_seen_at is not None:
        return
    task.advisor_seen_at = utcnow()
    db.add(task)
    db.commit()
    db.refresh(task)


def list_records(
    db: Session,
    user: User,
    *,
    scope: str = "mine",
    type: str | None = None,
    status: str | None = None,
    archived: bool = False,
    inbox_state: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    if page < 1:
        page = 1
    page_size = min(max(page_size, 1), PAGE_SIZE_MAX)
    query = db.query(Task).options(selectinload(Task.samples), selectinload(Task.models))
    if scope == "inbox":
        if user.role != "advisor":
            raise AppError("只有导师可以查看学生提交", code="FORBIDDEN", stage="auth", status_code=403)
        query = query.filter(
            Task.submitted_to_advisor_at.isnot(None),
            Task.type.in_(tuple(LAB_TYPES)),
        )
        if inbox_state == "pending":
            query = query.filter(Task.advisor_seen_at.is_(None))
        elif inbox_state == "seen":
            query = query.filter(Task.advisor_seen_at.isnot(None))
    elif scope == "mine":
        query = query.filter(Task.creator_id == user.id)
    else:
        raise AppError("范围只能是 mine 或 inbox", code="BAD_SCOPE", stage="protocol", status_code=400)
    if scope != "inbox":
        query = query.filter(Task.archived.is_(archived))
    if type:
        if type not in LAB_TYPES | {"demo"}:
            raise AppError("任务类型无效", code="BAD_TYPE", stage="protocol", status_code=400)
        if scope == "inbox" and type == "demo":
            return {"page": page, "page_size": page_size, "total": 0, "items": []}
        query = query.filter(Task.type == type)
    if status:
        query = query.filter(Task.status == status)
    total = query.count()
    rows = query.order_by(Task.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [serialize_record(db, row, user) for row in rows],
    }


def patch_record(
    db: Session,
    user: User,
    task_id: str,
    *,
    note: str | None = None,
    archived: bool | None = None,
) -> Task:
    task = _locked_visible_record(db, task_id, user)
    _require_owner(task, user)
    if note is not None:
        text = note.strip()
        if len(text) > 255:
            raise AppError("备注最多 255 字", code="NOTE_TOO_LONG", stage="protocol", status_code=400)
        task.note = text or None
    if archived is not None:
        task.archived = bool(archived)
    task.updated_at = utcnow()
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def submit_to_advisor(db: Session, user: User, task_id: str) -> Task:
    task = _locked_visible_record(db, task_id, user)
    _require_owner(task, user)
    if task.type not in LAB_TYPES:
        raise AppError("公开演示不能提交导师", code="DEMO_NO_SUBMIT", stage="protocol", status_code=400)
    if task.archived:
        raise AppError("已归档任务不能提交", code="ARCHIVED", stage="protocol", status_code=400)
    if task.status not in DONE:
        raise AppError("仅成功或部分成功的任务可提交导师", code="NOT_READY", stage="protocol", status_code=400)
    if task.submitted_to_advisor_at is not None:
        raise AppError("已经提交给导师", code="ALREADY_SUBMITTED", stage="protocol", status_code=409)
    task.submitted_to_advisor_at = utcnow()
    task.advisor_seen_at = None
    task.updated_at = utcnow()
    db.add(task)
    _write_audit(db, actor_id=user.id, action="task.submit_advisor", target_id=task.id, reason="提交导师审阅")
    db.commit()
    db.refresh(task)
    return task


def withdraw_from_advisor(db: Session, user: User, task_id: str) -> Task:
    task = _locked_visible_record(db, task_id, user)
    _require_owner(task, user)
    if task.submitted_to_advisor_at is None:
        raise AppError("尚未提交导师", code="NOT_SUBMITTED", stage="protocol", status_code=400)
    if task.advisor_seen_at is not None:
        raise AppError("导师已查看，不能撤回", code="ALREADY_SEEN", stage="protocol", status_code=409)
    task.submitted_to_advisor_at = None
    task.updated_at = utcnow()
    db.add(task)
    _write_audit(db, actor_id=user.id, action="task.withdraw_advisor", target_id=task.id, reason="撤回导师提交")
    db.commit()
    db.refresh(task)
    return task


def _model_ids(db: Session, task: Task) -> tuple[list[str], str | None]:
    models = db.query(TaskModel).filter_by(task_id=task.id).order_by(TaskModel.sort_order).populate_existing().with_for_update().all()
    baselines = [row.model_version_id for row in models if row.role == "baseline"]
    students = [row.model_version_id for row in models if row.role == "student_under_test"]
    return baselines, students[0] if students else None


def rerun_record(db: Session, user: User, task_id: str) -> Task:
    source = get_visible_task(db, task_id, user)
    _require_owner(source, user)
    if source.archived:
        raise AppError("已归档任务不能再跑", code="ARCHIVED", stage="protocol", status_code=400)
    from app.services.input_freeze import verify_inputs, lock_version
    from app.services.submission import lock_user
    lock_user(db, user)
    lock_version(db, source.dataset_version_id)
    source = db.query(Task).filter_by(id=source.id).populate_existing().with_for_update().one()
    _require_owner(source, user)
    if source.archived:
        raise AppError("已归档任务不能再跑", code="ARCHIVED", stage="protocol", status_code=400)
    baselines, student_id = _model_ids(db, source)
    verify_inputs(db, source, get_settings())
    if not baselines:
        raise AppError("原任务没有可再跑的模型", code="NO_MODELS", stage="protocol", status_code=400)
    if source.type == "pcb_classify":
        from app.services.pcb_classification import create_task
        versions = [db.get(ModelVersion, vid) for vid in baselines]
        if student_id or len(versions) != 1 or versions[0] is None:
            raise AppError("PCB 分类模型不完整", code="MODEL_ROLE_INVALID", stage="protocol", status_code=400)
        return create_task(db, user, batch_id=source.dataset_version_id, model_id=versions[0].slug)
    if source.type == "pcb_segmentation":
        from app.services.pcb_segmentation import create_pcb_task, task_include_cam
        versions = [db.get(ModelVersion, vid) for vid in baselines]
        if student_id or len(versions) != 1 or versions[0] is None:
            raise AppError("PCB 任务模型不完整或角色不匹配", code="MODEL_ROLE_INVALID", stage="protocol", status_code=400)
        return create_pcb_task(db, user, batch_id=source.dataset_version_id,
                               model_id=versions[0].slug, include_cam=task_include_cam(db, source))
    if source.type == "classification":
        from app.services.classification import create_classification_task
        versions = [db.get(ModelVersion, vid) for vid in baselines]
        if student_id or any(version is None for version in versions):
            raise AppError("分类任务模型不完整或角色不匹配", code="MODEL_ROLE_INVALID", stage="protocol", status_code=400)
        return create_classification_task(db, user, batch_id=source.dataset_version_id,
                                          model_slugs=[version.slug for version in versions])
    if source.type == "compare":
        return create_compare_task(
            db,
            user,
            batch_id=source.dataset_version_id,
            baseline_version_ids=baselines,
            student_version_id=student_id,
        )
    if source.type == "eval":
        return create_eval_task(
            db,
            user,
            dataset_version_id=source.dataset_version_id,
            baseline_version_ids=baselines,
            student_version_id=student_id,
        )
    if source.type == "demo":
        samples = db.query(Sample).join(TaskSample, Sample.id == TaskSample.sample_id).filter(TaskSample.task_id == source.id).order_by(TaskSample.sort_order).populate_existing().with_for_update().all()
        keys = [sample.sample_key for sample in samples]
        if not keys:
            raise AppError("原任务没有预备样例", code="NO_SAMPLES", stage="protocol", status_code=400)
        identity = DemoIdentity(sid=new_id(), user=user, ip="0.0.0.0", ip_hash="rerun")
        return create_demo_task(db, identity, sample_keys=keys, baseline_version_ids=baselines)
    raise AppError("该类型不能再跑", code="BAD_TYPE", stage="protocol", status_code=400)
