import sqlalchemy as sa
from alembic import op

revision = "0010_assistant_chat"
down_revision = "0009_assistant_kb_docs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assistant_sessions", sa.Column("title", sa.String(length=80), nullable=True))
    op.add_column("assistant_sessions", sa.Column("working_json", sa.JSON(), nullable=True))
    op.add_column(
        "assistant_turns",
        sa.Column("role", sa.String(length=16), nullable=False, server_default="assistant"),
    )
    op.add_column("assistant_turns", sa.Column("content", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("assistant_turns", "content")
    op.drop_column("assistant_turns", "role")
    op.drop_column("assistant_sessions", "working_json")
    op.drop_column("assistant_sessions", "title")
