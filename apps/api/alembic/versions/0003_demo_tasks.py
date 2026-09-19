import sqlalchemy as sa
from alembic import op

revision = "0003_demo_tasks"
down_revision = "0002_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "tasks",
        "creator_id",
        existing_type=sa.String(length=36),
        nullable=True,
    )
    op.add_column("tasks", sa.Column("guest_sid", sa.String(length=36), nullable=True))
    op.add_column("tasks", sa.Column("guest_ip_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_tasks_guest_sid", "tasks", ["guest_sid"])
    op.create_index("ix_tasks_type", "tasks", ["type"])
    op.create_index("ix_tasks_created_at", "tasks", ["created_at"])
    op.create_index("ix_tasks_type_created_at", "tasks", ["type", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_tasks_type_created_at", table_name="tasks")
    op.drop_index("ix_tasks_created_at", table_name="tasks")
    op.drop_index("ix_tasks_type", table_name="tasks")
    op.drop_index("ix_tasks_guest_sid", table_name="tasks")
    op.drop_column("tasks", "guest_ip_hash")
    op.drop_column("tasks", "guest_sid")
    op.alter_column(
        "tasks",
        "creator_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
