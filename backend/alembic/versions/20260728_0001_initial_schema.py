"""创建基金运营核心数据表。

Revision ID: 20260728_0001
Revises:
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260728_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_user")),
    )
    op.create_index(op.f("ix_app_user_username"), "app_user", ["username"], unique=True)

    op.create_table(
        "job_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "job_type",
            sa.Enum(
                "mail_sync",
                "attachment_reparse",
                "manual_upload",
                "export",
                name="job_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "trigger_type",
            sa.Enum(
                "scheduled",
                "manual",
                "startup_recovery",
                name="trigger_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "success",
                "partial_success",
                "failed",
                name="job_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("emails_found", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_run")),
    )
    op.create_index(op.f("ix_job_run_job_type"), "job_run", ["job_type"], unique=False)
    op.create_index(op.f("ix_job_run_status"), "job_run", ["status"], unique=False)

    op.create_table(
        "email_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_run_id", sa.Integer(), nullable=True),
        sa.Column("mailbox", sa.String(length=255), nullable=False),
        sa.Column("mailbox_key", sa.String(length=64), nullable=False),
        sa.Column("uid_validity", sa.String(length=64), nullable=False),
        sa.Column("message_uid", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.String(length=500), nullable=True),
        sa.Column("subject", sa.String(length=1000), nullable=False),
        sa.Column("sender", sa.String(length=500), nullable=False),
        sa.Column("receive_time", sa.DateTime(), nullable=False),
        sa.Column("attachment_count", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "discovered",
                "archived",
                "processing",
                "success",
                "partial_success",
                "failed",
                "skipped",
                name="email_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("eml_path", sa.String(length=1000), nullable=True),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_run_id"],
            ["job_run.id"],
            name=op.f("fk_email_record_job_run_id_job_run"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_record")),
        sa.UniqueConstraint(
            "mailbox_key",
            "uid_validity",
            "message_uid",
            name="uq_email_record_mailbox_uidvalidity_uid",
        ),
    )
    op.create_index(
        op.f("ix_email_record_message_id"), "email_record", ["message_id"], unique=False
    )
    op.create_index(
        "ix_email_record_receive_time", "email_record", ["receive_time"], unique=False
    )
    op.create_index(op.f("ix_email_record_status"), "email_record", ["status"], unique=False)

    op.create_table(
        "attachment_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email_id", sa.Integer(), nullable=False),
        sa.Column("original_name", sa.String(length=500), nullable=False),
        sa.Column("stored_path", sa.String(length=1000), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("file_type", sa.String(length=64), nullable=True),
        sa.Column(
            "parse_status",
            sa.Enum(
                "pending",
                "archived",
                "parsing",
                "success",
                "partial_success",
                "failed",
                "duplicate",
                "unsupported",
                name="attachment_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["email_id"],
            ["email_record.id"],
            name=op.f("fk_attachment_record_email_id_email_record"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attachment_record")),
        sa.UniqueConstraint(
            "email_id", "stored_path", name="uq_attachment_record_email_path"
        ),
    )
    op.create_index(
        op.f("ix_attachment_record_email_id"),
        "attachment_record",
        ["email_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attachment_record_parse_status"),
        "attachment_record",
        ["parse_status"],
        unique=False,
    )
    op.create_index(
        "ix_attachment_record_sha256", "attachment_record", ["sha256"], unique=False
    )

    op.create_table(
        "exception_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email_id", sa.Integer(), nullable=True),
        sa.Column("attachment_id", sa.Integer(), nullable=True),
        sa.Column("exception_type", sa.String(length=100), nullable=False),
        sa.Column(
            "severity",
            sa.Enum(
                "warning",
                "error",
                name="exception_severity",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("sheet_name", sa.String(length=255), nullable=True),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("field_name", sa.String(length=100), nullable=True),
        sa.Column("raw_value", sa.Text(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "resolved",
                "ignored",
                name="exception_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("resolved_time", sa.DateTime(), nullable=True),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["attachment_id"],
            ["attachment_record.id"],
            name=op.f("fk_exception_record_attachment_id_attachment_record"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["email_id"],
            ["email_record.id"],
            name=op.f("fk_exception_record_email_id_email_record"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exception_record")),
    )
    op.create_index(
        op.f("ix_exception_record_attachment_id"),
        "exception_record",
        ["attachment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_exception_record_email_id"),
        "exception_record",
        ["email_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_exception_record_exception_type"),
        "exception_record",
        ["exception_type"],
        unique=False,
    )
    op.create_index(
        "ix_exception_record_status_create_time",
        "exception_record",
        ["status", "create_time"],
        unique=False,
    )

    op.create_table(
        "fund_nav",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("nav_date", sa.Date(), nullable=False),
        sa.Column("unit_nav", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("total_nav", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("asset_value", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("source_file", sa.String(length=500), nullable=False),
        sa.Column("source_sheet", sa.String(length=255), nullable=True),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("attachment_id", sa.Integer(), nullable=True),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["attachment_id"],
            ["attachment_record.id"],
            name=op.f("fk_fund_nav_attachment_id_attachment_record"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fund_nav")),
        sa.UniqueConstraint(
            "product_code", "nav_date", name="uq_fund_nav_product_code_nav_date"
        ),
    )
    op.create_index(
        op.f("ix_fund_nav_attachment_id"), "fund_nav", ["attachment_id"], unique=False
    )
    op.create_index("ix_fund_nav_nav_date", "fund_nav", ["nav_date"], unique=False)
    op.create_index(
        "ix_fund_nav_product_name", "fund_nav", ["product_name"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_fund_nav_product_name", table_name="fund_nav")
    op.drop_index("ix_fund_nav_nav_date", table_name="fund_nav")
    op.drop_index(op.f("ix_fund_nav_attachment_id"), table_name="fund_nav")
    op.drop_table("fund_nav")

    op.drop_index("ix_exception_record_status_create_time", table_name="exception_record")
    op.drop_index(op.f("ix_exception_record_exception_type"), table_name="exception_record")
    op.drop_index(op.f("ix_exception_record_email_id"), table_name="exception_record")
    op.drop_index(op.f("ix_exception_record_attachment_id"), table_name="exception_record")
    op.drop_table("exception_record")

    op.drop_index("ix_attachment_record_sha256", table_name="attachment_record")
    op.drop_index(op.f("ix_attachment_record_parse_status"), table_name="attachment_record")
    op.drop_index(op.f("ix_attachment_record_email_id"), table_name="attachment_record")
    op.drop_table("attachment_record")

    op.drop_index(op.f("ix_email_record_status"), table_name="email_record")
    op.drop_index("ix_email_record_receive_time", table_name="email_record")
    op.drop_index(op.f("ix_email_record_message_id"), table_name="email_record")
    op.drop_table("email_record")

    op.drop_index(op.f("ix_job_run_status"), table_name="job_run")
    op.drop_index(op.f("ix_job_run_job_type"), table_name="job_run")
    op.drop_table("job_run")

    op.drop_index(op.f("ix_app_user_username"), table_name="app_user")
    op.drop_table("app_user")
