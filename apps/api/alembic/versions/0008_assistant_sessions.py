import sqlalchemy as sa
from alembic import op

revision = "0008_assistant_sessions"
down_revision = "0007_model_perf_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("specialty", sa.String(length=32), nullable=False, server_default="segment"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_assistant_sessions_user_id", "assistant_sessions", ["user_id"])
    op.create_table(
        "assistant_turns",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("intent", sa.String(length=32), nullable=False, server_default="analyze_task"),
        sa.Column("tool_name", sa.String(length=32), nullable=False, server_default="task.analyze"),
        sa.Column("params_summary", sa.Text(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("llm_status", sa.String(length=16), nullable=False, server_default="skipped"),
        sa.Column("llm_model", sa.String(length=64), nullable=True),
        sa.Column("writing", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["assistant_sessions.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
    )
    op.create_index("ix_assistant_turns_session_id", "assistant_turns", ["session_id"])
    op.create_index("ix_assistant_turns_task_id", "assistant_turns", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_assistant_turns_task_id", table_name="assistant_turns")
    op.drop_index("ix_assistant_turns_session_id", table_name="assistant_turns")
    op.drop_table("assistant_turns")
    op.drop_index("ix_assistant_sessions_user_id", table_name="assistant_sessions")
    op.drop_table("assistant_sessions")
