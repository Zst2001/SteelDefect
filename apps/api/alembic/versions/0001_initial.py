from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("quota_json", mysql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "preprocess_specs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("apply_clahe", sa.Boolean(), nullable=False),
        sa.Column("sp_threshold", sa.Float(), nullable=False),
        sa.Column("dataset", sa.String(32), nullable=False),
        sa.Column("extra_json", mysql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("datasets.id"), nullable=False, index=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("class_map_json", mysql.JSON(), nullable=True),
        sa.Column("preprocess_id", sa.String(36), sa.ForeignKey("preprocess_specs.id"), nullable=False),
        sa.Column("is_fixed_test", sa.Boolean(), nullable=False),
        sa.Column("forbid_student_gt_download", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "samples",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version_id", sa.String(36), sa.ForeignKey("dataset_versions.id"), nullable=False, index=True),
        sa.Column("sample_key", sa.String(128), nullable=False),
        sa.Column("origin_uri", sa.String(512), nullable=False),
        sa.Column("mask_uri", sa.String(512), nullable=True),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.UniqueConstraint("version_id", "sample_key", name="uq_sample_version_key"),
    )
    op.create_table(
        "models",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "model_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("model_id", sa.String(36), sa.ForeignKey("models.id"), nullable=False, index=True),
        sa.Column("slug", sa.String(64), nullable=False, index=True),
        sa.Column("entry_symbol", sa.String(128), nullable=True),
        sa.Column("num_classes", sa.Integer(), nullable=False),
        sa.Column("in_channels", sa.Integer(), nullable=False),
        sa.Column("input_h", sa.Integer(), nullable=False),
        sa.Column("input_w", sa.Integer(), nullable=False),
        sa.Column("preprocess_id", sa.String(36), sa.ForeignKey("preprocess_specs.id"), nullable=False),
        sa.Column("requires_cuda", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("fail_stage", sa.String(32), nullable=True),
        sa.Column("fail_message", sa.Text(), nullable=True),
        sa.Column("source_sha256", sa.String(64), nullable=True),
        sa.Column("visibility", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "weights",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version_id", sa.String(36), sa.ForeignKey("model_versions.id"), nullable=False, index=True),
        sa.Column("file_uri", sa.String(512), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("param_count", sa.BigInteger(), nullable=True),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("creator_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("dataset_version_id", sa.String(36), sa.ForeignKey("dataset_versions.id"), nullable=False),
        sa.Column("preprocess_id", sa.String(36), sa.ForeignKey("preprocess_specs.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, index=True),
        sa.Column("has_gt", sa.Boolean(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "task_models",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id"), nullable=False, index=True),
        sa.Column("model_version_id", sa.String(36), sa.ForeignKey("model_versions.id"), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("fail_stage", sa.String(32), nullable=True),
        sa.Column("fail_message", sa.Text(), nullable=True),
    )
    op.create_table(
        "task_samples",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id"), nullable=False, index=True),
        sa.Column("sample_id", sa.String(36), sa.ForeignKey("samples.id"), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
    )
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id"), nullable=False, index=True),
        sa.Column("sample_key", sa.String(128), nullable=True),
        sa.Column("model_version_id", sa.String(36), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("rel_path", sa.String(512), nullable=False),
    )
    op.create_table(
        "metric_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id"), nullable=False, unique=True),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("payload_json", mysql.JSON(), nullable=False),
    )


def downgrade() -> None:
    for table in [
        "metric_sets",
        "artifacts",
        "task_samples",
        "task_models",
        "tasks",
        "weights",
        "model_versions",
        "models",
        "samples",
        "dataset_versions",
        "datasets",
        "preprocess_specs",
        "sessions",
        "users",
    ]:
        op.drop_table(table)
