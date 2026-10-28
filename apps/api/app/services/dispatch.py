"""One enqueue attempt. Never interpret a post-send timeout as rejection."""
from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass

from redis.exceptions import RedisError
from rq import Queue

from app.cache import rq_connection
from app.db.models import ModelVersion, Task, TaskModel
from app.util_time import utcnow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Delivery:
    state: str  # confirmed | rejected | unknown
    job_id: str


def enqueue(settings, function: str, object_id: str, timeout: int, *, job_id: str) -> Delivery:
    # Older RQ accepts arbitrary kwargs; explicitly check support before sending anything.
    if "unique" not in inspect.signature(Queue.enqueue_call).parameters:
        logger.error("dispatch rejected: RQ unique enqueue unavailable job=%s", job_id)
        return Delivery("rejected", job_id)
    try:
        connection = rq_connection()
        connection.ping()  # Failure here is known to precede enqueue.
        queue = Queue(settings.rq_queue_name, connection=connection)
    except (RedisError, OSError):
        logger.warning("dispatch unavailable before send job=%s", job_id)
        return Delivery("rejected", job_id)
    try:
        queue.enqueue(function, object_id, job_id=job_id, unique=True,
                      job_timeout=timeout, result_ttl=86400, failure_ttl=86400)
        logger.info("dispatch confirmed job=%s", job_id)
        return Delivery("confirmed", job_id)
    except Exception as exc:
        # Includes DuplicateJobError. Lookup is observational, never an enqueue retry.
        logger.warning("dispatch response uncertain job=%s error=%s", job_id, type(exc).__name__)
        try:
            job = queue.fetch_job(job_id)
            if job is not None and job.func_name == function and tuple(job.args) == (object_id,):
                status = str(job.get_status()).split(".")[-1].lower()
                # A job hash alone is not proof of list insertion (e.g. a Redis
                # script can fail after writing its first key).
                if status in {"started", "finished", "failed", "stopped", "canceled"} or (
                    status == "queued" and queue.get_job_position(job_id) is not None
                ):
                    return Delivery("confirmed", job_id)
        except Exception as lookup_error:
            logger.warning("dispatch lookup unavailable job=%s error=%s", job_id, type(lookup_error).__name__)
        # Even a missing job now cannot disprove a delayed write later.
        return Delivery("unknown", job_id)


def apply_task_delivery(db, task, delivery) -> str:
    state = delivery.state if isinstance(delivery, Delivery) else "confirmed"
    row = db.query(Task).filter_by(id=task.id).populate_existing().with_for_update().one()
    if row.status != "queued":
        db.rollback()
        return "confirmed"  # A Worker already took ownership.
    if state == "confirmed":
        row.error_summary = None
        db.commit()
        return state
    row.error_summary = ("QUEUE_REJECTED: 未入队，请通过再跑创建新任务" if delivery.state == "rejected"
                         else "QUEUE_UNKNOWN: 入队结果待核验，请勿重复提交；作业 ID=" + delivery.job_id)
    if delivery.state == "rejected":
        row.status = "failed"
        for link in db.query(TaskModel).filter_by(task_id=row.id).all():
            link.status, link.fail_stage, link.fail_message = "failed", "queue", row.error_summary
    row.updated_at = utcnow()
    db.commit()
    return delivery.state


def apply_admit_delivery(db, version, delivery) -> None:
    state = delivery.state if isinstance(delivery, Delivery) else "confirmed"
    row = db.query(ModelVersion).filter_by(id=version.id).populate_existing().with_for_update().one()
    if row.status != "checking" or row.fail_stage == "admit_running":
        db.rollback()
        return
    if state == "confirmed":
        row.fail_stage, row.fail_message = None, None
        db.commit()
        return
    row.fail_stage = "queue"
    row.fail_message = ("QUEUE_REJECTED: 隔离检查未入队；需要显式重新导入/复检" if delivery.state == "rejected"
                        else "QUEUE_UNKNOWN: 隔离检查入队待核验；作业 ID=" + delivery.job_id)
    if delivery.state == "rejected":
        row.status = "cannot_start"
    db.commit()
