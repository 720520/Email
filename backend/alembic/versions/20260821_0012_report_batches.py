"""增加批量报表数据库任务队列。

Revision ID: 20260821_0012
Revises: 20260821_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0012"
down_revision: str | None = "20260821_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_batch",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("template_version_id", sa.Integer()),
        sa.Column("template_key", sa.String(64), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("cancelled_count", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["template_version_id"], ["report_template_version.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_report_batch_idempotency"),
    )
    op.create_index("ix_report_batch_tenant_id", "report_batch", ["tenant_id"])
    op.create_index("ix_report_batch_template_version_id", "report_batch", ["template_version_id"])
    op.create_index("ix_report_batch_created_by_user_id", "report_batch", ["created_by_user_id"])
    op.create_index("ix_report_batch_tenant_status", "report_batch", ["tenant_id", "status"])
    op.create_table(
        "report_batch_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("fund_product_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False, unique=True),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("report_run_id", sa.Integer()),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("locked_by", sa.String(128)),
        sa.Column("locked_at", sa.DateTime()),
        sa.Column("error_code", sa.String(128)),
        sa.Column("error_message", sa.Text()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["batch_id"], ["report_batch.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fund_product_id"], ["fund_product.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["report_run_id"], ["report_run.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "tenant_id", "batch_id", "fund_product_id", name="uq_report_batch_item"
        ),
    )
    for name, columns in (
        ("ix_report_batch_item_tenant_id", ["tenant_id"]),
        ("ix_report_batch_item_batch_id", ["batch_id"]),
        ("ix_report_batch_item_fund_product_id", ["fund_product_id"]),
        ("ix_report_batch_item_report_run_id", ["report_run_id"]),
        ("ix_report_batch_item_claim", ["tenant_id", "status", "id"]),
    ):
        op.create_index(name, "report_batch_item", columns)


def downgrade() -> None:
    op.drop_table("report_batch_item")
    op.drop_table("report_batch")
