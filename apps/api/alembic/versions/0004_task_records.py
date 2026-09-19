import sqlalchemy as sa
from alembic import op

revision = "0004_task_records"
down_revision = "0003_demo_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("note", sa.String(length=255), nullable=True))
    op.add_column("tasks", sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("tasks", sa.Column("submitted_to_advisor_at", sa.DateTime(), nullable=True))
    op.add_column("tasks", sa.Column("advisor_seen_at", sa.DateTime(), nullable=True))
    op.create_index("ix_tasks_archived", "tasks", ["archived"])
    op.create_index("ix_tasks_submitted_to_advisor_at", "tasks", ["submitted_to_advisor_at"])


def downgrade() -> None:
    op.drop_index("ix_tasks_submitted_to_advisor_at", table_name="tasks")
    op.drop_index("ix_tasks_archived", table_name="tasks")
    op.drop_column("tasks", "advisor_seen_at")
    op.drop_column("tasks", "submitted_to_advisor_at")
    op.drop_column("tasks", "archived")
    op.drop_column("tasks", "note")
