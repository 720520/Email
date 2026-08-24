"""增加动态报表字段注册中心。

Revision ID: 20260821_0008
Revises: 20260807_0007
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0008"
down_revision: str | None = "20260807_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_field_definition",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("field_key", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000)),
        sa.Column("data_type", sa.String(length=32), nullable=False),
        sa.Column("value_kind", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_config", sa.JSON(), nullable=False),
        sa.Column("format_config", sa.JSON(), nullable=False),
        sa.Column("default_value", sa.Text()),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("is_sensitive", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "field_key", name="uq_report_field_tenant_key"),
    )
    op.create_index(
        "ix_report_field_definition_tenant_id", "report_field_definition", ["tenant_id"]
    )
    op.create_index(
        "ix_report_field_definition_created_by_user_id",
        "report_field_definition",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_report_field_tenant_active", "report_field_definition", ["tenant_id", "is_active"]
    )

    op.create_table(
        "report_field_value",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("field_definition_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("value_text", sa.Text()),
        sa.Column("value_json", sa.JSON()),
        sa.Column("effective_date", sa.Date()),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_reference", sa.String(length=1000)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["field_definition_id"], ["report_field_definition.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "field_definition_id",
            "entity_type",
            "entity_id",
            "effective_date",
            name="uq_report_field_value_scope",
        ),
    )
    op.create_index("ix_report_field_value_tenant_id", "report_field_value", ["tenant_id"])
    op.create_index(
        "ix_report_field_value_field_definition_id", "report_field_value", ["field_definition_id"]
    )
    op.create_index(
        "ix_report_field_value_created_by_user_id", "report_field_value", ["created_by_user_id"]
    )
    op.create_index(
        "ix_report_field_value_entity",
        "report_field_value",
        ["tenant_id", "entity_type", "entity_id"],
    )


def downgrade() -> None:
    op.drop_table("report_field_value")
    op.drop_table("report_field_definition")
