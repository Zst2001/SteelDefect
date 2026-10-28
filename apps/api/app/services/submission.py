"""Optional client idempotency keys, serialized by existing database rows."""
from uuid import NAMESPACE_URL, uuid5

from app.db.models import Task, TaskModel, TaskSample, Sample, User
from app.errors import AppError
from app.util_time import new_id


def request_id(scope: str, actor: str, key: str | None) -> str:
    if key is None:
        return new_id()
    if not key.strip() or len(key) > 128:
        raise AppError("幂等键长度须为 1–128", code="BAD_IDEMPOTENCY_KEY", stage="protocol")
    return str(uuid5(NAMESPACE_URL, f"steel:{scope}:{actor}:{key}"))


def lock_user(db, user):
    return db.query(User).filter_by(id=user.id).populate_existing().with_for_update().one()


def existing_task(db, task_id, kind, version_id, baselines, student, keys=None):
    task = db.query(Task).filter_by(id=task_id).populate_existing().with_for_update().one_or_none()
    if task is None:
        return None
    links = db.query(TaskModel).filter_by(task_id=task.id).order_by(TaskModel.sort_order).populate_existing().with_for_update().all()
    actual = [(r.role, r.model_version_id) for r in links]
    expected = [("baseline", x) for x in baselines] + ([("student_under_test", student)] if student else [])
    valid = task.type == kind and task.dataset_version_id == version_id and actual == expected
    if keys is not None:
        samples = db.query(Sample).join(TaskSample, Sample.id == TaskSample.sample_id).filter(TaskSample.task_id == task.id).order_by(TaskSample.sort_order).populate_existing().with_for_update().all()
        valid = valid and [s.sample_key for s in samples] == keys
    if not valid:
        raise AppError("同一幂等键不能用于不同参数", code="IDEMPOTENCY_CONFLICT", stage="protocol", status_code=409)
    return task
