from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party"), str(ROOT / "apps" / "api")]

import pytest

from app.db.models import AuditLog, User
from app.db.session import Base
from app.errors import AppError
from app.routers.auth import register
from app.security import verify_password
from app.services.users import create_student, serialize_user, set_student_status
from app.util_time import utcnow
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def test_register_api_is_disabled() -> None:
    with pytest.raises(AppError) as exc:
        register()
    assert exc.value.code == "REGISTER_DISABLED"
    assert exc.value.status_code == 403
    assert "导师开通" in exc.value.message


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _advisor(db: Session) -> User:
    row = User(
        id="adv-1",
        username="advisor",
        password_hash="unused",
        role="advisor",
        status="active",
        quota_json={"max_upload_images": 50},
        created_at=utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_advisor_can_provision_student_who_could_login(db: Session) -> None:
    advisor = _advisor(db)
    student = create_student(db, advisor, username="李四-lab", password="StudentDev!234", reason="入组")
    assert student.role == "student"
    assert student.status == "active"
    assert verify_password("StudentDev!234", student.password_hash)
    payload = serialize_user(student)
    assert payload["username"] == "李四-lab"
    assert "password" not in payload
    assert "password_hash" not in payload
    logs = db.query(AuditLog).all()
    assert len(logs) == 1
    assert logs[0].action == "user.create"
    assert logs[0].actor_id == advisor.id
    assert logs[0].reason == "入组"


def test_duplicate_student_username_rejected(db: Session) -> None:
    advisor = _advisor(db)
    create_student(db, advisor, username="dup", password="StudentDev!234")
    with pytest.raises(AppError) as exc:
        create_student(db, advisor, username="dup", password="StudentDev!234")
    assert exc.value.code == "USERNAME_TAKEN"
    assert db.query(User).filter(User.role == "student").count() == 1


def test_cannot_disable_advisor(db: Session) -> None:
    advisor = _advisor(db)
    with pytest.raises(AppError) as exc:
        set_student_status(db, advisor, advisor.id, status="disabled", reason="误操作")
    assert exc.value.code == "NOT_STUDENT"
    db.refresh(advisor)
    assert advisor.status == "active"


def test_disable_student_revokes_status(db: Session) -> None:
    advisor = _advisor(db)
    student = create_student(db, advisor, username="temp", password="StudentDev!234")
    updated = set_student_status(db, advisor, student.id, status="disabled", reason="离组")
    assert updated.status == "disabled"
    actions = {row.action for row in db.query(AuditLog).all()}
    assert actions == {"user.create", "user.disable"}
