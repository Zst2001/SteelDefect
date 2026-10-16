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
    perf_profile: Mapped["ModelPerfProfile | None"] = relationship(back_populates="version", uselist=False)


class Weight(Base):
    __tablename__ = "weights"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version_id: Mapped[str] = mapped_column(String(36), ForeignKey("model_versions.id"), nullable=False, index=True)
    file_uri: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    param_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    version: Mapped[ModelVersion] = relationship(back_populates="weights")


class ModelPerfProfile(Base):
    """CPU dummy-forward efficiency facts for one ModelVersion. Not eval metrics."""

    __tablename__ = "model_perf_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("model_versions.id"), unique=True, nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unmeasured")
    param_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    weight_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    latency_ms_per_image: Mapped[float | None] = mapped_column(Float, nullable=True)
    flops: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    warmup_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    timed_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    batch: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    input_h: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_w: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="dummy")
    device: Mapped[str] = mapped_column(String(16), nullable=False, default="cpu")
    env_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fail_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    measured_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    version: Mapped[ModelVersion] = relationship(back_populates="perf_profile")


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


class HomeStat(Base):
    __tablename__ = "home_stats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    research_models: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    papers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class CatalogModel(Base):
    """Homepage catalog of literature / group models. Not the runnable lab Model table."""

    __tablename__ = "catalog_models"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    backbone: Mapped[str | None] = mapped_column(String(128), nullable=True)
    keywords: Mapped[str | None] = mapped_column(String(512), nullable=True)
    paper_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    code_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    dataset: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_group_work: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class CatalogWork(Base):
    """Group research outcomes shown on the homepage. No source-code links."""

    __tablename__ = "catalog_works"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    authors: Mapped[str | None] = mapped_column(String(512), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class CatalogFund(Base):
    """Advisor research grants shown on the homepage."""

    __tablename__ = "catalog_funds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="pi")
    start_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ongoing")
    amount_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class CatalogDataset(Base):
    __tablename__ = "catalog_datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_object: Mapped[str | None] = mapped_column(String(255), nullable=True)
    numbers_text: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    defect_types: Mapped[str | None] = mapped_column(String(512), nullable=True)
    size: Mapped[str | None] = mapped_column(String(128), nullable=True)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    access_note: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class AssistantSession(Base):
    __tablename__ = "assistant_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    specialty: Mapped[str] = mapped_column(String(32), nullable=False, default="segment")
    title: Mapped[str | None] = mapped_column(String(80), nullable=True)
    working_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    turns: Mapped[list["AssistantTurn"]] = relationship(back_populates="session")


class AssistantTurn(Base):
    __tablename__ = "assistant_turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("assistant_sessions.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="assistant")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent: Mapped[str] = mapped_column(String(32), nullable=False, default="analyze_task")
    tool_name: Mapped[str] = mapped_column(String(32), nullable=False, default="task.analyze")
    params_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=True, index=True)
    llm_status: Mapped[str] = mapped_column(String(16), nullable=False, default="skipped")
    llm_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    writing: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    session: Mapped[AssistantSession] = relationship(back_populates="turns")


class AssistantKbDoc(Base):
    """Advisor-curated reading pack for the academic specialty. Students read-only."""

    __tablename__ = "assistant_kb_docs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="protocol")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source_label: Mapped[str] = mapped_column(String(128), nullable=False, default="导师审定")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
