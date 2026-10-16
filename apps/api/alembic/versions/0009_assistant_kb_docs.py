import sqlalchemy as sa
from alembic import op

revision = "0009_assistant_kb_docs"
down_revision = "0008_assistant_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_kb_docs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="protocol"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source_label", sa.String(length=128), nullable=False, server_default="导师审定"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_assistant_kb_docs_slug", "assistant_kb_docs", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_assistant_kb_docs_slug", table_name="assistant_kb_docs")
    op.drop_table("assistant_kb_docs")
