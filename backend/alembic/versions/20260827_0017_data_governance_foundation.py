"""阶段 1 数据治理底座。

Revision ID: 20260827_0017
Revises: 20260825_0016
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260827_0017"
down_revision: str | None = "20260825_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tenant_columns() -> list[sa.Column]:
    return [sa.Column("tenant_id", sa.Integer(), nullable=False)]


def upgrade() -> None:
    op.create_table(
        "entity",
        sa.Column("id", sa.Integer(), primary_key=True),
        *_tenant_columns(),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(300), nullable=False),
        sa.Column("external_code", sa.String(100)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "entity_type", "external_code", name="uq_entity_code"),
    )
    op.create_index("ix_entity_tenant_id", "entity", ["tenant_id"])
    op.create_index("ix_entity_created_by_user_id", "entity", ["created_by_user_id"])
    op.create_index(
        "ix_entity_tenant_type_status", "entity", ["tenant_id", "entity_type", "status"]
    )

    op.create_table(
        "field_definition",
        sa.Column("id", sa.Integer(), primary_key=True),
        *_tenant_columns(),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("field_code", sa.String(100), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("data_type", sa.String(32), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("sensitivity", sa.String(32), nullable=False),
        sa.Column("is_multivalue", sa.Boolean(), nullable=False),
        sa.Column("validation_schema", sa.JSON(), nullable=False),
        sa.Column("display_schema", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "tenant_id", "entity_type", "field_code", name="uq_field_definition_code"
        ),
    )
    op.create_index("ix_field_definition_tenant_id", "field_definition", ["tenant_id"])
    op.create_index(
        "ix_field_definition_type_order",
        "field_definition",
        ["tenant_id", "entity_type", "sort_order"],
    )

    op.create_table(
        "source_document",
        sa.Column("id", sa.Integer(), primary_key=True),
        *_tenant_columns(),
        sa.Column("document_key", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.Integer()),
        sa.Column("document_type", sa.String(100), nullable=False),
        sa.Column("original_name", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(200), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("effective_date", sa.Date()),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("source_channel", sa.String(32), nullable=False),
        sa.Column("sensitivity", sa.String(32), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "tenant_id", "document_key", "version", name="uq_source_document_version"
        ),
    )
    for column in ("tenant_id", "entity_id", "uploaded_by_user_id"):
        op.create_index(f"ix_source_document_{column}", "source_document", [column])
    op.create_index(
        "ix_source_document_entity_time", "source_document", ["entity_id", "create_time"]
    )
    op.create_index("ix_source_document_hash", "source_document", ["tenant_id", "content_hash"])

    op.create_table(
        "field_value",
        sa.Column("id", sa.Integer(), primary_key=True),
        *_tenant_columns(),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("field_definition_id", sa.Integer(), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("valid_from", sa.DateTime(), nullable=False),
        sa.Column("valid_to", sa.DateTime()),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_document_id", sa.Integer()),
        sa.Column("source_locator_json", sa.JSON(), nullable=False),
        sa.Column("extraction_run_id", sa.Integer()),
        sa.Column("confidence", sa.Integer()),
        sa.Column("entered_by_user_id", sa.Integer()),
        sa.Column("reviewed_by_user_id", sa.Integer()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["field_definition_id"], ["field_definition.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["source_document.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["entered_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
    )
    for column in (
        "tenant_id",
        "entity_id",
        "field_definition_id",
        "source_document_id",
        "entered_by_user_id",
        "reviewed_by_user_id",
    ):
        op.create_index(f"ix_field_value_{column}", "field_value", [column])
    op.create_index(
        "ix_field_value_entity_field_time",
        "field_value",
        ["entity_id", "field_definition_id", "valid_from"],
    )
    op.create_index("ix_field_value_source_document", "field_value", ["source_document_id"])

    op.create_table(
        "document_relation",
        sa.Column("id", sa.Integer(), primary_key=True),
        *_tenant_columns(),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("relation_type", sa.String(64), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id"], ["source_document.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "document_id", "entity_id", "relation_type", name="uq_document_relation"
        ),
    )
    for column in ("tenant_id", "document_id", "entity_id"):
        op.create_index(f"ix_document_relation_{column}", "document_relation", [column])

    op.create_table(
        "resource_grant",
        sa.Column("id", sa.Integer(), primary_key=True),
        *_tenant_columns(),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.Integer()),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("sensitivity_ceiling", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("granted_by_user_id", sa.Integer()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "user_id", "entity_id", name="uq_resource_grant_scope"),
    )
    for column in ("tenant_id", "user_id", "entity_id", "granted_by_user_id"):
        op.create_index(f"ix_resource_grant_{column}", "resource_grant", [column])


def downgrade() -> None:
    op.drop_table("resource_grant")
    op.drop_table("document_relation")
    op.drop_table("field_value")
    op.drop_table("source_document")
    op.drop_table("field_definition")
    op.drop_table("entity")
