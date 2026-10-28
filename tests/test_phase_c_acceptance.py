"""Final C acceptance: never overwrite another worker's active attempt."""
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import OperationalError

from test_phase_a_authorization import lab, create
from app.db.models import Task, ModelVersion, ModelPerfProfile
from app.errors import AppError
from app.services import perf
from apps.worker import jobs


@pytest.mark.parametrize("kind", ["compare", "admit", "perf"])
def test_preclaim_query_failure_preserves_other_worker(lab, monkeypatch, kind):
    monkeypatch.setattr(jobs, "invalidate_models_lists", lambda: None)
    if kind == "compare":
        row = lab.db.get(Task, create(lab).json()["id"])
        row.status = "running"
        row.error_summary = "active-attempt"
        table, row_id, expected = Task, row.id, ("running", "active-attempt")
    elif kind == "admit":
        row = lab.mine
        row.status, row.fail_stage, row.fail_message = "checking", "admit_running", "active-attempt"
        table, row_id, expected = ModelVersion, row.id, ("checking", "admit_running", "active-attempt")
    else:
        row = perf.get_or_create_profile(lab.db, lab.mine)
        row.status, row.job_id, row.fail_message = "measuring", "active-job", "active-attempt"
        table, row_id, expected = ModelPerfProfile, row.id, ("measuring", "active-job", "active-attempt")
    target = row_id if kind != "perf" else lab.mine.id
    lab.db.commit()
    worker_db = lab.factory()
    query = worker_db.query
    first = True
    def fail_once(*args, **kwargs):
        nonlocal first
        if first:
            first = False
            raise OperationalError("synthetic lock query", {}, RuntimeError("lock wait timeout"))
        return query(*args, **kwargs)
    monkeypatch.setattr(worker_db, "query", fail_once)
    monkeypatch.setattr(jobs, "SessionLocal", lambda: worker_db)
    with pytest.raises(OperationalError):
        getattr(jobs, f"run_{kind}")(target)
    lab.db.expire_all()
    row = lab.db.get(table, row_id)
    actual = ((row.status, row.error_summary) if kind == "compare" else
              (row.status, row.fail_stage, row.fail_message) if kind == "admit" else
              (row.status, row.job_id, row.fail_message))
    assert actual == expected


@pytest.mark.parametrize("kind", ["compare", "admit", "perf"])
@pytest.mark.parametrize("completed", [False, True])
def test_owned_failure_is_recorded_but_completed_result_is_preserved(lab, monkeypatch, kind, completed):
    monkeypatch.setattr(jobs, "invalidate_models_lists", lambda: None)
    if kind == "compare":
        target = create(lab).json()["id"]
        executor = "_run_compare_body"
    elif kind == "admit":
        lab.mine.status, lab.mine.fail_stage = "checking", "queue"
        target, executor = lab.mine.id, "admit_version"
    else:
        profile = perf.get_or_create_profile(lab.db, lab.mine)
        profile.status, profile.job_id = "queued", "current-job"
        target, executor = lab.mine.id, "measure_student_version"
    lab.db.commit()
    def execute(db, row, settings):
        if completed:
            if kind == "compare": row.status = "success"
            elif kind == "admit": row.status, row.fail_stage = "runnable", None
            else:
                current = db.query(ModelPerfProfile).filter_by(version_id=target).one()
                current.status = "success"
            db.commit()
        raise RuntimeError("synthetic executor or post-commit failure")
    monkeypatch.setattr(jobs, executor, execute)
    with pytest.raises(RuntimeError, match="synthetic"):
        getattr(jobs, f"run_{kind}")(target)
    lab.db.expire_all()
    row = (lab.db.get(Task, target) if kind == "compare" else
           lab.db.get(ModelVersion, target) if kind == "admit" else
           lab.db.query(ModelPerfProfile).filter_by(version_id=target).one())
    assert row.status == (("runnable" if kind == "admit" else "success") if completed else
                          ("cannot_start" if kind == "admit" else "failed"))


@pytest.mark.parametrize("kind", ["admit", "perf"])
def test_failure_does_not_overwrite_changed_generation(lab, monkeypatch, kind):
    monkeypatch.setattr(jobs, "invalidate_models_lists", lambda: None)
    target = lab.mine.id
    if kind == "admit":
        lab.mine.status, lab.mine.fail_stage, lab.mine.source_sha256 = "checking", "queue", "old-hash"
        executor = "admit_version"
    else:
        row = perf.get_or_create_profile(lab.db, lab.mine)
        row.status, row.job_id = "queued", "old-job"
        executor = "measure_student_version"
    lab.db.commit()
    def execute(db, version, settings):
        # Fault injection emulates another committed generation, not a real retry.
        if kind == "admit": version.source_sha256, version.fail_message = "new-hash", "new-attempt"
        else:
            row = db.query(ModelPerfProfile).filter_by(version_id=target).one()
            row.job_id, row.fail_message = "new-job", "new-attempt"
        db.commit()
        raise RuntimeError("old attempt failed")
    monkeypatch.setattr(jobs, executor, execute)
    with pytest.raises(RuntimeError, match="old attempt"):
        getattr(jobs, f"run_{kind}")(target)
    lab.db.expire_all()
    row = (lab.db.get(ModelVersion, target) if kind == "admit" else
           lab.db.query(ModelPerfProfile).filter_by(version_id=target).one())
    assert row.status == ("checking" if kind == "admit" else "measuring")
    assert row.fail_message == "new-attempt"


def test_prestart_failure_does_not_overwrite_claim_after_rollback(lab, monkeypatch):
    target = create(lab).json()["id"]
    worker_db = lab.factory()
    rollback = worker_db.rollback
    def release_and_handover():
        rollback()
        with lab.factory() as other:
            row = other.get(Task, target)
            row.status, row.error_summary = "running", "other-worker"
            other.commit()
    monkeypatch.setattr(worker_db, "rollback", release_and_handover)
    monkeypatch.setattr(jobs, "SessionLocal", lambda: worker_db)
    monkeypatch.setattr(jobs, "verify_inputs", Mock(side_effect=AppError("synthetic", code="INPUT_CHANGED", stage="file")))
    with pytest.raises(AppError): jobs.run_compare(target)
    lab.db.expire_all()
    row = lab.db.get(Task, target)
    assert (row.status, row.error_summary) == ("running", "other-worker")
