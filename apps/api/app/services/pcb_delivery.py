"""Lightweight RQ failure reconciliation for PCB jobs that never claimed a task.

Keep this module independent of jobs, inference and Torch: a timeout importing
those modules is precisely why this callback exists. Running/terminal attempts
remain owned by jobs._run_task and are never overwritten here.
"""
from uuid import UUID

from rq.timeouts import JobTimeoutException

from app.cache import invalidate_after_write
from app.db.models import AuditLog, DatasetVersion, Task, TaskModel, User
from app.db.session import SessionLocal
from app.util_time import new_id, utcnow

CALLBACK = "app.services.pcb_delivery.reconcile_unclaimed_failure"
FUNCTION = "apps.worker.jobs.run_pcb_segmentation"
FUNCTIONS = {FUNCTION: ("pcb_segmentation", "PCB", "pcb"),
             "apps.worker.jobs.run_pcb_classification": ("pcb_classify", "PCB_CLS", "pcb_cls")}


def reconcile_unclaimed_failure(job, _connection, exc_type, _exc_value, _traceback):
    args = getattr(job, "args", ())
    identity = FUNCTIONS.get(getattr(job, "func_name", None))
    if (identity is None or not isinstance(args, (tuple, list))
            or len(args) != 1 or not isinstance(args[0], str) or getattr(job, "kwargs", None) not in (None, {})):
        return
    task_id = args[0]
    task_type, prefix, audit_prefix = identity
    try:
        if str(UUID(task_id)) != task_id or getattr(job, "id", None) != "task-" + task_id:
            return
    except (ValueError, AttributeError):
        return
    timeout = isinstance(exc_type, type) and issubclass(exc_type, JobTimeoutException)
    message = (prefix + "_JOB_TIMEOUT: 作业在领取任务前超时，请通过再跑创建新任务" if timeout else
               prefix + "_JOB_START_FAILED: 作业未能领取任务，请联系管理员后通过再跑创建新任务")
    creator_id = None
    changed = False
    with SessionLocal() as db:
        # Same actor -> dataset version -> task lock order as submission/claim.
        candidate = db.query(Task.creator_id, Task.dataset_version_id).filter_by(id=task_id).first()
        if candidate is None:
            return
        if candidate.creator_id:
            db.query(User).filter_by(id=candidate.creator_id).with_for_update().one_or_none()
        db.query(DatasetVersion).filter_by(id=candidate.dataset_version_id).with_for_update().one_or_none()
        task = db.query(Task).filter_by(id=task_id).populate_existing().with_for_update().one_or_none()
        if (task is None or task.type != task_type or task.status != "queued"
                or task.creator_id != candidate.creator_id or task.dataset_version_id != candidate.dataset_version_id):
            return
        task.status, task.error_summary, task.updated_at = "failed", message, utcnow()
        for link in db.query(TaskModel).filter_by(task_id=task_id).populate_existing().with_for_update().all():
            link.status, link.fail_stage, link.fail_message = "failed", "resource" if timeout else "queue", message
        creator_id = task.creator_id
        if creator_id:
            db.add(AuditLog(id=new_id(), actor_id=creator_id, action=audit_prefix + ".dispatch_failure",
                            target_type="task", target_id=task_id,
                            reason="RQ 确认任务领取前超时" if timeout else "RQ 确认任务领取前失败"))
        db.commit()
        changed = True
    if changed:
        invalidate_after_write(task_id, creator_id)
