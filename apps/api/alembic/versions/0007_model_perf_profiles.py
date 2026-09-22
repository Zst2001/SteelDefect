import sqlalchemy as sa
from alembic import op

revision = "0007_model_perf_profiles"
down_revision = "0006_catalog_works_funds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_perf_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="unmeasured"),
        sa.Column("param_count", sa.BigInteger(), nullable=True),
        sa.Column("weight_bytes", sa.BigInteger(), nullable=True),
        sa.Column("latency_ms_per_image", sa.Float(), nullable=True),
        sa.Column("flops", sa.BigInteger(), nullable=True),
        sa.Column("warmup_runs", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("timed_runs", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("batch", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("input_h", sa.Integer(), nullable=True),
        sa.Column("input_w", sa.Integer(), nullable=True),
        sa.Column("input_kind", sa.String(length=32), nullable=False, server_default="dummy"),
        sa.Column("device", sa.String(length=16), nullable=False, server_default="cpu"),
        sa.Column("env_json", sa.JSON(), nullable=True),
        sa.Column("fail_message", sa.Text(), nullable=True),
        sa.Column("job_id", sa.String(length=64), nullable=True),
        sa.Column("measured_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["model_versions.id"]),
    )
    op.create_index("ix_model_perf_profiles_version_id", "model_perf_profiles", ["version_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_model_perf_profiles_version_id", table_name="model_perf_profiles")
    op.drop_table("model_perf_profiles")
