"""增加报表字段定义版本快照。

Revision ID: 20260821_0009
Revises: 20260821_0008
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0009"
down_revision: str | None = "20260821_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_field_definition_version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("field_definition_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["field_definition_id"],
            ["report_field_definition.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "field_definition_id",
            "version",
            name="uq_report_field_definition_version",
        ),
    )
    op.create_index(
        "ix_report_field_definition_version_tenant_id",
        "report_field_definition_version",
        ["tenant_id"],
    )
    op.create_index(
        "ix_report_field_definition_version_field_definition_id",
        "report_field_definition_version",
        ["field_definition_id"],
    )
    op.create_index(
        "ix_report_field_definition_version_created_by_user_id",
        "report_field_definition_version",
        ["created_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("report_field_definition_version")
