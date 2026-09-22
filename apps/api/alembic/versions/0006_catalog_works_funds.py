import sqlalchemy as sa
from alembic import op

revision = "0006_catalog_works_funds"
down_revision = "0005_home_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_works",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("venue", sa.String(length=255), nullable=True),
        sa.Column("authors", sa.String(length=512), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("link_url", sa.String(length=512), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_catalog_works_kind", "catalog_works", ["kind"])
    op.create_table(
        "catalog_funds",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("number", sa.String(length=128), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="pi"),
        sa.Column("start_year", sa.Integer(), nullable=True),
        sa.Column("end_year", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ongoing"),
        sa.Column("amount_text", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_catalog_funds_source", "catalog_funds", ["source"])


def downgrade() -> None:
    op.drop_index("ix_catalog_funds_source", table_name="catalog_funds")
    op.drop_table("catalog_funds")
    op.drop_index("ix_catalog_works_kind", table_name="catalog_works")
    op.drop_table("catalog_works")
