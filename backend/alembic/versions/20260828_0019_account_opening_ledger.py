"""阶段 3 机构模板与开户台账。

Revision ID: 20260828_0019
Revises: 20260827_0018
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260828_0019"
down_revision: str | None = "20260827_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "counterparty_institution",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("institution_type", sa.String(32), nullable=False),
        sa.Column("full_name", sa.String(300), nullable=False),
        sa.Column("short_name", sa.String(100)),
        sa.Column("license_code", sa.String(100)),
        sa.Column("contact_information", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("entity_id", name="uq_counterparty_institution_entity_id"),
        sa.UniqueConstraint("tenant_id", "full_name", name="uq_counterparty_institution_full_name"),
    )
    _indexes(
        "counterparty_institution",
        "tenant_id",
        "entity_id",
    )
    op.create_index(
        "ix_counterparty_institution_type_active",
        "counterparty_institution",
        ["institution_type", "is_active"],
    )

    op.create_table(
        "requirement_template",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("institution_id", sa.Integer()),
        sa.Column("template_scope", sa.String(32), nullable=False),
        sa.Column("account_type", sa.String(64), nullable=False),
        sa.Column("fund_type", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["institution_id"], ["counterparty_institution.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "institution_id",
            "account_type",
            "fund_type",
            "name",
            "version",
            name="uq_requirement_template_version",
        ),
    )
    _indexes("requirement_template", "tenant_id", "institution_id")
    op.create_index(
        "ix_requirement_template_match",
        "requirement_template",
        ["tenant_id", "institution_id", "account_type", "fund_type", "is_active"],
    )

    op.create_table(
        "requirement_template_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("requirement_code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source_scope", sa.String(32), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("condition_json", sa.JSON(), nullable=False),
        sa.Column("seal_requirement", sa.String(200)),
        sa.Column("original_required", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["template_id"], ["requirement_template.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "template_id", "requirement_code", name="uq_requirement_template_item_code"
        ),
    )
    _indexes("requirement_template_item", "tenant_id", "template_id")
    op.create_index(
        "ix_requirement_template_item_order",
        "requirement_template_item",
        ["template_id", "sort_order"],
    )

    op.create_table(
        "account_application",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("institution_id", sa.Integer(), nullable=False),
        sa.Column("account_type", sa.String(64), nullable=False),
        sa.Column("settlement_mode", sa.String(64), nullable=False),
        sa.Column("fund_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("application_date", sa.Date(), nullable=False),
        sa.Column("completed_date", sa.Date()),
        sa.Column("closed_date", sa.Date()),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_user_id", sa.Integer()),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["fund_product.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["institution_id"], ["counterparty_institution.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["app_user.id"], ondelete="SET NULL"),
    )
    _indexes(
        "account_application",
        "tenant_id",
        "product_id",
        "institution_id",
        "owner_user_id",
        "reviewer_user_id",
    )
    op.create_index(
        "ix_account_application_status",
        "account_application",
        ["tenant_id", "status", "application_date"],
    )
    op.create_index(
        "ix_account_application_product",
        "account_application",
        ["product_id", "institution_id"],
    )

    op.create_table(
        "application_requirement",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("source_template_id", sa.Integer()),
        sa.Column("requirement_code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source_scope", sa.String(32), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("condition_json", sa.JSON(), nullable=False),
        sa.Column("seal_requirement", sa.String(200)),
        sa.Column("original_required", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("document_id", sa.Integer()),
        sa.Column("review_comment", sa.String(1000)),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["application_id"], ["account_application.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_template_id"], ["requirement_template.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["source_document.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "application_id", "requirement_code", name="uq_application_requirement_code"
        ),
    )
    _indexes(
        "application_requirement",
        "tenant_id",
        "application_id",
        "source_template_id",
        "document_id",
    )
    op.create_index(
        "ix_application_requirement_order",
        "application_requirement",
        ["application_id", "sort_order"],
    )

    op.create_table(
        "application_supplement",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("requirement_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String(1000)),
        sa.Column("submitted_by_user_id", sa.Integer(), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["application_id"], ["account_application.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["requirement_id"], ["application_requirement.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["source_document.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["app_user.id"], ondelete="RESTRICT"),
    )
    _indexes(
        "application_supplement",
        "tenant_id",
        "application_id",
        "requirement_id",
        "document_id",
        "submitted_by_user_id",
    )
    op.create_index(
        "ix_application_supplement_application",
        "application_supplement",
        ["application_id", "create_time"],
    )

    op.create_table(
        "application_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("from_status", sa.String(32)),
        sa.Column("to_status", sa.String(32)),
        sa.Column("comment", sa.String(1000)),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("detail_json", sa.JSON(), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["application_id"], ["account_application.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["app_user.id"], ondelete="RESTRICT"),
    )
    _indexes("application_event", "tenant_id", "application_id", "actor_user_id")
    op.create_index(
        "ix_application_event_application",
        "application_event",
        ["application_id", "create_time"],
    )


def downgrade() -> None:
    op.drop_table("application_event")
    op.drop_table("application_supplement")
    op.drop_table("application_requirement")
    op.drop_table("account_application")
    op.drop_table("requirement_template_item")
    op.drop_table("requirement_template")
    op.drop_table("counterparty_institution")


def _indexes(table: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])
