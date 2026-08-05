"""增加租户、邮箱账户、资源作用域和审计基础设施。

Revision ID: 20260804_0003
Revises: 20260729_0002
Create Date: 2026-08-04
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "20260804_0003"
down_revision: str | None = "20260729_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    op.create_table(
        "tenant",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant")),
    )
    op.create_index(op.f("ix_tenant_code"), "tenant", ["code"], unique=True)

    op.create_table(
        "mailbox_account",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=320), nullable=False),
        sa.Column("auth_mode", sa.String(length=32), nullable=False),
        sa.Column("credential_ciphertext", sa.Text(), nullable=True),
        sa.Column("credential_key_version", sa.Integer(), nullable=False),
        sa.Column("credential_updated_at", sa.DateTime(), nullable=True),
        sa.Column("use_ssl", sa.Boolean(), nullable=False),
        sa.Column("start_tls", sa.Boolean(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("folder", sa.String(length=255), nullable=False),
        sa.Column("lookback_days", sa.Integer(), nullable=False),
        sa.Column("max_messages_per_run", sa.Integer(), nullable=False),
        sa.Column("max_attachment_bytes", sa.Integer(), nullable=False),
        sa.Column("retry_attempts", sa.Integer(), nullable=False),
        sa.Column("retry_base_delay_seconds", sa.Float(), nullable=False),
        sa.Column("uid_reservation_stale_seconds", sa.Integer(), nullable=False),
        sa.Column("parsing_options", sa.JSON(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("last_connection_status", sa.String(length=32), nullable=True),
        sa.Column("last_connection_at", sa.DateTime(), nullable=True),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_mailbox_account_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mailbox_account")),
        sa.UniqueConstraint(
            "tenant_id",
            "host",
            "username",
            "folder",
            name="uq_mailbox_account_tenant_identity",
        ),
    )
    op.create_index(
        op.f("ix_mailbox_account_tenant_id"), "mailbox_account", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_mailbox_account_is_default"), "mailbox_account", ["is_default"], unique=False
    )
    op.create_index(
        op.f("ix_mailbox_account_is_enabled"), "mailbox_account", ["is_enabled"], unique=False
    )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "INSERT INTO tenant (id, code, name, is_active, create_time, update_time) "
            "VALUES (1, 'default', :name, 1, :now, :now)"
        ),
        {"name": "默认业务账套", "now": now},
    )
    connection.execute(
        sa.text(
            "INSERT INTO mailbox_account ("
            "id, tenant_id, display_name, provider_type, host, port, username, auth_mode, "
            "credential_ciphertext, credential_key_version, use_ssl, start_tls, "
            "timeout_seconds, folder, lookback_days, max_messages_per_run, "
            "max_attachment_bytes, retry_attempts, retry_base_delay_seconds, "
            "uid_reservation_stale_seconds, parsing_options, is_default, is_enabled, "
            "create_time, update_time"
            ") VALUES ("
            "1, 1, :display_name, 'generic_imap', '', 993, '', 'password', NULL, 1, "
            "1, 0, 30, 'INBOX', 7, 200, 52428800, 3, 1, 1800, :options, 1, 1, :now, :now"
            ")"
        ),
        {"display_name": "默认邮箱", "options": "{}", "now": now},
    )

    op.create_table(
        "tenant_membership",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "admin", "operator", "viewer", name="tenant_user_role", native_enum=False
            ),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_tenant_membership_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"], name=op.f("fk_tenant_membership_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_membership")),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_membership_tenant_user"),
    )
    op.create_index(
        op.f("ix_tenant_membership_tenant_id"),
        "tenant_membership",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tenant_membership_user_id"),
        "tenant_membership",
        ["user_id"],
        unique=False,
    )
    connection.execute(
        sa.text(
            "INSERT INTO tenant_membership "
            "(tenant_id, user_id, role, is_active, create_time, update_time) "
            "SELECT 1, id, role, 1, :now, :now FROM app_user"
        ),
        {"now": now},
    )

    op.create_table(
        "mailbox_user_grant",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("mailbox_account_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("can_read_metadata", sa.Boolean(), nullable=False),
        sa.Column("can_read_content", sa.Boolean(), nullable=False),
        sa.Column("can_operate", sa.Boolean(), nullable=False),
        sa.Column("can_manage_credentials", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_mailbox_user_grant_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["mailbox_account_id"],
            ["mailbox_account.id"],
            name=op.f("fk_mailbox_user_grant_mailbox_account_id_mailbox_account"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"], name=op.f("fk_mailbox_user_grant_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mailbox_user_grant")),
        sa.UniqueConstraint(
            "mailbox_account_id", "user_id", name="uq_mailbox_user_grant_mailbox_user"
        ),
    )
    for column in ("tenant_id", "mailbox_account_id", "user_id"):
        op.create_index(
            op.f(f"ix_mailbox_user_grant_{column}"),
            "mailbox_user_grant",
            [column],
            unique=False,
        )
    connection.execute(
        sa.text(
            "INSERT INTO mailbox_user_grant ("
            "tenant_id, mailbox_account_id, user_id, can_read_metadata, can_read_content, "
            "can_operate, can_manage_credentials, is_active, create_time, update_time"
            ") SELECT 1, 1, id, 1, 1, "
            "CASE WHEN role IN ('admin', 'operator') THEN 1 ELSE 0 END, "
            "CASE WHEN role = 'admin' THEN 1 ELSE 0 END, 1, :now, :now FROM app_user"
        ),
        {"now": now},
    )

    _add_scope_columns(connection)
    _create_audit_table(connection)


def _add_scope_columns(connection) -> None:
    with op.batch_alter_table("job_run") as batch_op:
        batch_op.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("mailbox_account_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("triggered_by_user_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("email_record") as batch_op:
        batch_op.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("mailbox_account_id", sa.Integer(), nullable=True))
    for table_name in ("attachment_record", "exception_record", "fund_nav"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("mailbox_account_id", sa.Integer(), nullable=True))

    connection.execute(sa.text("UPDATE job_run SET tenant_id = 1, mailbox_account_id = 1"))
    connection.execute(sa.text("UPDATE email_record SET tenant_id = 1, mailbox_account_id = 1"))
    connection.execute(
        sa.text(
            "UPDATE attachment_record SET tenant_id = 1, mailbox_account_id = 1"
        )
    )
    connection.execute(
        sa.text("UPDATE exception_record SET tenant_id = 1, mailbox_account_id = 1")
    )
    connection.execute(sa.text("UPDATE fund_nav SET tenant_id = 1, mailbox_account_id = 1"))

    with op.batch_alter_table("job_run") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            op.f("fk_job_run_tenant_id_tenant"), "tenant", ["tenant_id"], ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            op.f("fk_job_run_mailbox_account_id_mailbox_account"),
            "mailbox_account", ["mailbox_account_id"], ["id"], ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            op.f("fk_job_run_triggered_by_user_id_app_user"),
            "app_user", ["triggered_by_user_id"], ["id"], ondelete="SET NULL",
        )
        batch_op.create_index(op.f("ix_job_run_tenant_id"), ["tenant_id"])
        batch_op.create_index(op.f("ix_job_run_mailbox_account_id"), ["mailbox_account_id"])
        batch_op.create_index(op.f("ix_job_run_triggered_by_user_id"), ["triggered_by_user_id"])

    with op.batch_alter_table("email_record") as batch_op:
        batch_op.drop_constraint("uq_email_record_mailbox_uidvalidity_uid", type_="unique")
        batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("mailbox_account_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            op.f("fk_email_record_tenant_id_tenant"), "tenant", ["tenant_id"], ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            op.f("fk_email_record_mailbox_account_id_mailbox_account"),
            "mailbox_account", ["mailbox_account_id"], ["id"], ondelete="RESTRICT",
        )
        batch_op.create_unique_constraint(
            "uq_email_record_scope_uidvalidity_uid",
            ["tenant_id", "mailbox_account_id", "uid_validity", "message_uid"],
        )
        batch_op.create_index(op.f("ix_email_record_tenant_id"), ["tenant_id"])
        batch_op.create_index(
            op.f("ix_email_record_mailbox_account_id"), ["mailbox_account_id"]
        )

    for table_name in ("attachment_record", "exception_record", "fund_nav"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=False)
            batch_op.alter_column(
                "mailbox_account_id", existing_type=sa.Integer(), nullable=False
            )
            batch_op.create_foreign_key(
                op.f(f"fk_{table_name}_tenant_id_tenant"),
                "tenant", ["tenant_id"], ["id"], ondelete="RESTRICT",
            )
            batch_op.create_foreign_key(
                op.f(f"fk_{table_name}_mailbox_account_id_mailbox_account"),
                "mailbox_account", ["mailbox_account_id"], ["id"], ondelete="RESTRICT",
            )
            batch_op.create_index(op.f(f"ix_{table_name}_tenant_id"), ["tenant_id"])
            batch_op.create_index(
                op.f(f"ix_{table_name}_mailbox_account_id"), ["mailbox_account_id"]
            )

    with op.batch_alter_table("fund_nav") as batch_op:
        batch_op.drop_constraint("uq_fund_nav_product_code_nav_date", type_="unique")
        batch_op.create_unique_constraint(
            "uq_fund_nav_tenant_product_code_nav_date",
            ["tenant_id", "product_code", "nav_date"],
        )


def _create_audit_table(connection) -> None:
    op.create_table(
        "audit_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_username", sa.String(length=100), nullable=False),
        sa.Column("mailbox_account_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=100), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("previous_hash", sa.String(length=64), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_audit_event_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["app_user.id"],
            name=op.f("fk_audit_event_actor_user_id_app_user"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["mailbox_account_id"], ["mailbox_account.id"],
            name=op.f("fk_audit_event_mailbox_account_id_mailbox_account"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_event")),
        sa.UniqueConstraint("event_hash", name=op.f("uq_audit_event_event_hash")),
    )
    for name, columns in (
        (op.f("ix_audit_event_tenant_id"), ["tenant_id"]),
        (op.f("ix_audit_event_actor_user_id"), ["actor_user_id"]),
        (op.f("ix_audit_event_mailbox_account_id"), ["mailbox_account_id"]),
        (op.f("ix_audit_event_action"), ["action"]),
        (op.f("ix_audit_event_request_id"), ["request_id"]),
        ("ix_audit_event_tenant_time", ["tenant_id", "create_time"]),
        ("ix_audit_event_resource", ["resource_type", "resource_id"]),
    ):
        op.create_index(name, "audit_event", columns, unique=False)

    if connection.dialect.name == "sqlite":
        op.execute(
            "CREATE TRIGGER trg_audit_event_no_update BEFORE UPDATE ON audit_event "
            "BEGIN SELECT RAISE(ABORT, 'audit_event is append-only'); END"
        )
        op.execute(
            "CREATE TRIGGER trg_audit_event_no_delete BEFORE DELETE ON audit_event "
            "BEGIN SELECT RAISE(ABORT, 'audit_event is append-only'); END"
        )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trg_audit_event_no_delete")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_event_no_update")
    op.drop_table("audit_event")

    with op.batch_alter_table("fund_nav") as batch_op:
        batch_op.drop_constraint("uq_fund_nav_tenant_product_code_nav_date", type_="unique")
        batch_op.create_unique_constraint(
            "uq_fund_nav_product_code_nav_date", ["product_code", "nav_date"]
        )

    with op.batch_alter_table("email_record") as batch_op:
        batch_op.drop_constraint("uq_email_record_scope_uidvalidity_uid", type_="unique")
        batch_op.create_unique_constraint(
            "uq_email_record_mailbox_uidvalidity_uid",
            ["mailbox_key", "uid_validity", "message_uid"],
        )

    for table_name in ("fund_nav", "exception_record", "attachment_record", "email_record"):
        op.drop_index(op.f(f"ix_{table_name}_mailbox_account_id"), table_name=table_name)
        op.drop_index(op.f(f"ix_{table_name}_tenant_id"), table_name=table_name)
    op.drop_index(op.f("ix_job_run_triggered_by_user_id"), table_name="job_run")
    op.drop_index(op.f("ix_job_run_mailbox_account_id"), table_name="job_run")
    op.drop_index(op.f("ix_job_run_tenant_id"), table_name="job_run")

    for table_name in ("fund_nav", "exception_record", "attachment_record"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column("mailbox_account_id")
            batch_op.drop_column("tenant_id")
    with op.batch_alter_table("email_record") as batch_op:
        batch_op.drop_column("mailbox_account_id")
        batch_op.drop_column("tenant_id")
    with op.batch_alter_table("job_run") as batch_op:
        batch_op.drop_column("triggered_by_user_id")
        batch_op.drop_column("mailbox_account_id")
        batch_op.drop_column("tenant_id")

    op.drop_table("mailbox_user_grant")
    op.drop_table("tenant_membership")
    op.drop_table("mailbox_account")
    op.drop_index(op.f("ix_tenant_code"), table_name="tenant")
    op.drop_table("tenant")
