"""增加报表中心、合同来源和产品扩展要素。

Revision ID: 20260807_0007
Revises: 20260805_0006
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260807_0007"
down_revision: str | None = "20260805_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("fund_product") as batch_op:
        batch_op.add_column(
            sa.Column("source_profile", sa.JSON(), nullable=False, server_default="{}")
        )
        batch_op.add_column(
            sa.Column("source_profile_meta", sa.JSON(), nullable=False, server_default="{}")
        )
        batch_op.add_column(
            sa.Column("manual_profile", sa.JSON(), nullable=False, server_default="{}")
        )

    op.create_table(
        "product_document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("fund_product_id", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("original_name", sa.String(length=500), nullable=False),
        sa.Column("stored_path", sa.String(length=1000), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("extracted_fields", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["fund_product_id"], ["fund_product.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["app_user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "fund_product_id", "content_hash",
            name="uq_product_document_tenant_product_hash",
        ),
    )
    op.create_index("ix_product_document_tenant_id", "product_document", ["tenant_id"])
    op.create_index(
        "ix_product_document_fund_product_id", "product_document", ["fund_product_id"]
    )
    op.create_index(
        "ix_product_document_created_by_user_id", "product_document", ["created_by_user_id"]
    )
    op.create_index(
        "ix_product_document_product_time", "product_document",
        ["fund_product_id", "create_time"],
    )

    op.create_table(
        "report_template",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000)),
        sa.Column("original_name", sa.String(length=500), nullable=False),
        sa.Column("stored_path", sa.String(length=1000), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["app_user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_report_template_tenant_name"),
    )
    op.create_index("ix_report_template_tenant_id", "report_template", ["tenant_id"])
    op.create_index(
        "ix_report_template_created_by_user_id", "report_template", ["created_by_user_id"]
    )

    op.create_table(
        "report_definition",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("fund_product_id", sa.Integer(), nullable=False),
        sa.Column("template_key", sa.String(length=64), nullable=False),
        sa.Column("report_type", sa.String(length=32), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["fund_product_id"], ["fund_product.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["app_user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_report_definition_tenant_name"),
    )
    op.create_index("ix_report_definition_tenant_id", "report_definition", ["tenant_id"])
    op.create_index(
        "ix_report_definition_fund_product_id", "report_definition", ["fund_product_id"]
    )
    op.create_index(
        "ix_report_definition_created_by_user_id", "report_definition", ["created_by_user_id"]
    )
    op.create_index(
        "ix_report_definition_product", "report_definition", ["fund_product_id", "update_time"]
    )

    op.create_table(
        "report_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("definition_id", sa.Integer()),
        sa.Column("fund_product_id", sa.Integer(), nullable=False),
        sa.Column("template_key", sa.String(length=64), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("output_filename", sa.String(length=500)),
        sa.Column("output_path", sa.String(length=1000)),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["definition_id"], ["report_definition.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["fund_product_id"], ["fund_product.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["app_user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_run_tenant_id", "report_run", ["tenant_id"])
    op.create_index("ix_report_run_definition_id", "report_run", ["definition_id"])
    op.create_index("ix_report_run_fund_product_id", "report_run", ["fund_product_id"])
    op.create_index(
        "ix_report_run_created_by_user_id", "report_run", ["created_by_user_id"]
    )
    op.create_index("ix_report_run_tenant_time", "report_run", ["tenant_id", "create_time"])
    op.create_index(
        "ix_report_run_product_date", "report_run", ["fund_product_id", "report_date"]
    )


def downgrade() -> None:
    op.drop_table("report_run")
    op.drop_table("report_definition")
    op.drop_table("report_template")
    op.drop_table("product_document")
    with op.batch_alter_table("fund_product") as batch_op:
        batch_op.drop_column("manual_profile")
        batch_op.drop_column("source_profile_meta")
        batch_op.drop_column("source_profile")
