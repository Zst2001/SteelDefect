import sqlalchemy as sa
from alembic import op

revision = "0005_home_catalog"
down_revision = "0004_task_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "home_stats",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("research_models", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("papers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "catalog_models",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("task_type", sa.String(length=32), nullable=False),
        sa.Column("backbone", sa.String(length=128), nullable=True),
        sa.Column("keywords", sa.String(length=512), nullable=True),
        sa.Column("paper_url", sa.String(length=512), nullable=True),
        sa.Column("code_url", sa.String(length=512), nullable=True),
        sa.Column("dataset", sa.String(length=255), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("is_group_work", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_catalog_models_task_type", "catalog_models", ["task_type"])
    op.create_index("ix_catalog_models_is_group_work", "catalog_models", ["is_group_work"])
    op.create_table(
        "catalog_datasets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("task_type", sa.String(length=32), nullable=False),
        sa.Column("source_object", sa.String(length=255), nullable=True),
        sa.Column("numbers_text", sa.String(length=512), nullable=True),
        sa.Column("image_count", sa.Integer(), nullable=True),
        sa.Column("class_count", sa.Integer(), nullable=True),
        sa.Column("defect_types", sa.String(length=512), nullable=True),
        sa.Column("size", sa.String(length=128), nullable=True),
        sa.Column("url", sa.String(length=512), nullable=True),
        sa.Column("access_note", sa.String(length=128), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_catalog_datasets_task_type", "catalog_datasets", ["task_type"])


def downgrade() -> None:
    op.drop_index("ix_catalog_datasets_task_type", table_name="catalog_datasets")
    op.drop_table("catalog_datasets")
    op.drop_index("ix_catalog_models_is_group_work", table_name="catalog_models")
    op.drop_index("ix_catalog_models_task_type", table_name="catalog_models")
    op.drop_table("catalog_models")
    op.drop_table("home_stats")
