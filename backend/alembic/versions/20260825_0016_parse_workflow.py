"""解析队列与人工复核暂存。

Revision ID: 20260825_0016
Revises: 20260825_0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_0016"
down_revision: str | None = "20260825_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "attachment_parse_task",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attachment_id", sa.Integer(), nullable=False),
        sa.Column("source_job_run_id", sa.Integer(), nullable=True),
        sa.Column("parse_job_run_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("queued_at", sa.DateTime(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("locked_by", sa.String(length=255), nullable=True),
        sa.Column("parser_version", sa.String(length=64), nullable=True),
        sa.Column("inserted_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("exception_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("mailbox_account_id", sa.Integer(), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["attachment_id"], ["attachment_record.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_job_run_id"], ["job_run.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parse_job_run_id"], ["job_run.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["mailbox_account_id"], ["mailbox_account.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attachment_id", name="uq_attachment_parse_task_attachment"),
    )
    op.create_index("ix_attachment_parse_task_attachment_id", "attachment_parse_task", ["attachment_id"])
    op.create_index("ix_attachment_parse_task_source_job_run_id", "attachment_parse_task", ["source_job_run_id"])
    op.create_index("ix_attachment_parse_task_parse_job_run_id", "attachment_parse_task", ["parse_job_run_id"])
    op.create_index("ix_attachment_parse_task_status", "attachment_parse_task", ["status"])
    op.create_index("ix_attachment_parse_task_tenant_id", "attachment_parse_task", ["tenant_id"])
    op.create_index("ix_attachment_parse_task_mailbox_account_id", "attachment_parse_task", ["mailbox_account_id"])
    op.create_index("ix_attachment_parse_task_queue", "attachment_parse_task", ["status", "next_attempt_at", "id"])

    op.create_table(
        "parse_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attachment_id", sa.Integer(), nullable=False),
        sa.Column("source_attachment_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("file_issues", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("valid_count", sa.Integer(), nullable=False),
        sa.Column("invalid_count", sa.Integer(), nullable=False),
        sa.Column("ignored_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("inserted_count", sa.Integer(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("mailbox_account_id", sa.Integer(), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["attachment_id"], ["attachment_record.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_attachment_id"], ["attachment_record.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["mailbox_account_id"], ["mailbox_account.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attachment_id", name="uq_parse_session_attachment"),
    )
    for column in ("attachment_id", "source_attachment_id", "created_by_user_id", "confirmed_by_user_id", "status", "tenant_id", "mailbox_account_id"):
        op.create_index(f"ix_parse_session_{column}", "parse_session", [column])
    op.create_index("ix_parse_session_status_update_time", "parse_session", ["status", "update_time"])

    op.create_table(
        "parse_result_row",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parse_session_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_sheet", sa.String(length=255), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=True),
        sa.Column("product_code", sa.String(length=64), nullable=True),
        sa.Column("master_product_code", sa.String(length=64), nullable=True),
        sa.Column("asset_code", sa.String(length=64), nullable=True),
        sa.Column("registration_code", sa.String(length=64), nullable=True),
        sa.Column("share_class", sa.String(length=32), nullable=True),
        sa.Column("nav_date", sa.Date(), nullable=True),
        sa.Column("unit_nav", sa.Numeric(20, 8), nullable=True),
        sa.Column("total_nav", sa.Numeric(20, 8), nullable=True),
        sa.Column("asset_value", sa.Numeric(24, 4), nullable=True),
        sa.Column("asset_share", sa.Numeric(24, 4), nullable=True),
        sa.Column("paid_in_capital", sa.Numeric(24, 4), nullable=True),
        sa.Column("holding_shares", sa.Numeric(24, 4), nullable=True),
        sa.Column("reference_market_value", sa.Numeric(24, 4), nullable=True),
        sa.Column("total_assets", sa.Numeric(24, 4), nullable=True),
        sa.Column("total_assets_nav_ratio", sa.Numeric(20, 8), nullable=True),
        sa.Column("investor_name", sa.String(length=255), nullable=True),
        sa.Column("investor_account", sa.String(length=128), nullable=True),
        sa.Column("parent_unit_nav", sa.Numeric(20, 8), nullable=True),
        sa.Column("parent_total_nav", sa.Numeric(20, 8), nullable=True),
        sa.Column("parent_asset_value", sa.Numeric(24, 4), nullable=True),
        sa.Column("parent_product_code", sa.String(length=64), nullable=True),
        sa.Column("parent_product_name", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("parent_paid_in_capital", sa.Numeric(24, 4), nullable=True),
        sa.Column("investment_manager_info", sa.Text(), nullable=True),
        sa.Column("investment_strategy_info", sa.Text(), nullable=True),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("original_data", sa.JSON(), nullable=False),
        sa.Column("validation_message", sa.Text(), nullable=True),
        sa.Column("conflict_action", sa.String(length=32), nullable=False),
        sa.Column("existing_nav_id", sa.Integer(), nullable=True),
        sa.Column("is_edited", sa.Boolean(), nullable=False),
        sa.Column("edit_reason", sa.String(length=500), nullable=True),
        sa.Column("edited_by_user_id", sa.Integer(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("committed_nav_id", sa.Integer(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("mailbox_account_id", sa.Integer(), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["parse_session_id"], ["parse_session.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["edited_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["existing_nav_id"], ["fund_nav.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["committed_nav_id"], ["fund_nav.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["mailbox_account_id"], ["mailbox_account.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("parse_session_id", "source_sheet", "source_row", name="uq_parse_result_row_source"),
    )
    for column in ("parse_session_id", "status", "edited_by_user_id", "existing_nav_id", "committed_nav_id", "tenant_id", "mailbox_account_id"):
        op.create_index(f"ix_parse_result_row_{column}", "parse_result_row", [column])
    op.create_index("ix_parse_result_row_session_status", "parse_result_row", ["parse_session_id", "status", "id"])

    op.create_table(
        "fund_nav_revision",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fund_nav_id", sa.Integer(), nullable=False),
        sa.Column("parse_session_id", sa.Integer(), nullable=False),
        sa.Column("parse_result_row_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("original_data", sa.JSON(), nullable=False),
        sa.Column("corrected_data", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("mailbox_account_id", sa.Integer(), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["fund_nav_id"], ["fund_nav.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parse_session_id"], ["parse_session.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parse_result_row_id"], ["parse_result_row.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["mailbox_account_id"], ["mailbox_account.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("fund_nav_id", "parse_session_id", "parse_result_row_id", "actor_user_id", "tenant_id", "mailbox_account_id"):
        op.create_index(f"ix_fund_nav_revision_{column}", "fund_nav_revision", [column])

    # 仅为历史尚未处理的 Excel 附件补任务，已成功/失败记录保持原状。
    op.execute(sa.text("""
        INSERT INTO attachment_parse_task (
            attachment_id, source_job_run_id, status, trigger_type, attempt_count,
            max_attempts, queued_at, inserted_count, duplicate_count, exception_count,
            tenant_id, mailbox_account_id, create_time, update_time
        )
        SELECT a.id, e.job_run_id, 'queued', 'startup_recovery', 0, 3,
               CURRENT_TIMESTAMP, 0, 0, 0, a.tenant_id, a.mailbox_account_id,
               CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM attachment_record a
        JOIN email_record e ON e.id = a.email_id
        WHERE a.parse_status IN ('archived', 'pending')
          AND lower(a.file_type) IN ('xls', 'xlsx')
    """))
    op.execute(sa.text("UPDATE attachment_record SET parse_status = 'pending' WHERE id IN (SELECT attachment_id FROM attachment_parse_task WHERE status = 'queued')"))


def downgrade() -> None:
    op.drop_table("fund_nav_revision")
    op.drop_table("parse_result_row")
    op.drop_table("parse_session")
    op.drop_table("attachment_parse_task")
