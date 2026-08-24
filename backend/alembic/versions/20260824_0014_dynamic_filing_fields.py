"""增加动态备案字段和不可变文件版本。

Revision ID: 20260824_0014
Revises: 20260824_0013
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "20260824_0014"
down_revision: str | None = "20260824_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "filing_field",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("field_key", sa.String(64), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("field_type", sa.String(16), nullable=False),
        sa.Column("sensitive", sa.Boolean(), nullable=False),
        sa.Column("multiline", sa.Boolean(), nullable=False),
        sa.Column("source_forms", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "field_key", name="uq_filing_field_tenant_key"),
    )
    op.create_index("ix_filing_field_tenant_id", "filing_field", ["tenant_id"])
    op.create_index("ix_filing_field_created_by_user_id", "filing_field", ["created_by_user_id"])
    op.create_index("ix_filing_field_tenant_order", "filing_field", ["tenant_id", "sort_order", "id"])
    op.create_table(
        "filing_file_version",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("field_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("original_name", sa.String(500), nullable=False),
        sa.Column("stored_path", sa.String(1000), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(200)),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["field_id"], ["filing_field.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "field_id", "version", name="uq_filing_file_version"),
    )
    op.create_index("ix_filing_file_version_tenant_id", "filing_file_version", ["tenant_id"])
    op.create_index("ix_filing_file_version_field_id", "filing_file_version", ["field_id"])
    op.create_index("ix_filing_file_version_created_by_user_id", "filing_file_version", ["created_by_user_id"])
    op.create_index("ix_filing_file_version_field_time", "filing_file_version", ["field_id", "create_time"])


def downgrade() -> None:
    op.drop_table("filing_file_version")
    op.drop_table("filing_field")
