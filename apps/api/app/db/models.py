from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.util_time import utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # student | advisor
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    quota_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    sessions: Mapped[list["Session"]] = relationship(back_populates="user")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="sessions")


class PreprocessSpecRow(Base):
    __tablename__ = "preprocess_specs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    apply_clahe: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sp_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.02)
    dataset: Mapped[str] = mapped_column(String(32), nullable=False, default="neu")
    extra_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)  # preset | private | shared
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    versions: Mapped[list["DatasetVersion"]] = relationship(back_populates="dataset")


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    class_map_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    preprocess_id: Mapped[str] = mapped_column(String(36), ForeignKey("preprocess_specs.id"), nullable=False)
    is_fixed_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    forbid_student_gt_download: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    dataset: Mapped[Dataset] = relationship(back_populates="versions")
    samples: Mapped[list["Sample"]] = relationship(back_populates="version")


class Sample(Base):
    __tablename__ = "samples"
    __table_args__ = (UniqueConstraint("version_id", "sample_key", name="uq_sample_version_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version_id: Mapped[str] = mapped_column(String(36), ForeignKey("dataset_versions.id"), nullable=False, index=True)
    sample_key: Mapped[str] = mapped_column(String(128), nullable=False)
    origin_uri: Mapped[str] = mapped_column(String(512), nullable=False)
    mask_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    version: Mapped[DatasetVersion] = relationship(back_populates="samples")


class Model(Base):
    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # builtin | student
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    versions: Mapped[list["ModelVersion"]] = relationship(back_populates="model")


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(36), ForeignKey("models.id"), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entry_symbol: Mapped[str | None] = mapped_column(String(128), nullable=True)
    num_classes: Mapped[int] = mapped_column(Integer, nullable=False)
    in_channels: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    input_h: Mapped[int] = mapped_column(Integer, nullable=False)
    input_w: Mapped[int] = mapped_column(Integer, nullable=False)
    preprocess_id: Mapped[str] = mapped_column(String(36), ForeignKey("preprocess_specs.id"), nullable=False)
    requires_cuda: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")
    fail_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fail_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="public")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    model: Mapped[Model] = relationship(back_populates="versions")
    weights: Mapped[list["Weight"]] = relationship(back_populates="version")


class Weight(Base):
    __tablename__ = "weights"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version_id: Mapped[str] = mapped_column(String(36), ForeignKey("model_versions.id"), nullable=False, index=True)
    file_uri: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    param_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    version: Mapped[ModelVersion] = relationship(back_populates="weights")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # compare | eval | demo
    creator_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    guest_sid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    guest_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dataset_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("dataset_versions.id"), nullable=False)
    preprocess_id: Mapped[str] = mapped_column(String(36), ForeignKey("preprocess_specs.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    has_gt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    submitted_to_advisor_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    advisor_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    models: Mapped[list["TaskModel"]] = relationship(back_populates="task")
    samples: Mapped[list["TaskSample"]] = relationship(back_populates="task")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="task")
    metric_set: Mapped["MetricSet | None"] = relationship(back_populates="task", uselist=False)


class TaskModel(Base):
    __tablename__ = "task_models"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    model_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("model_versions.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # student_under_test | baseline
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    fail_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fail_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    task: Mapped[Task] = relationship(back_populates="models")


class TaskSample(Base):
    __tablename__ = "task_samples"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    sample_id: Mapped[str] = mapped_column(String(36), ForeignKey("samples.id"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    task: Mapped[Task] = relationship(back_populates="samples")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    sample_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    rel_path: Mapped[str] = mapped_column(String(512), nullable=False)

    task: Mapped[Task] = relationship(back_populates="artifacts")


class MetricSet(Base):
    __tablename__ = "metric_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), unique=True, nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    n: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    task: Mapped[Task] = relationship(back_populates="metric_set")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
