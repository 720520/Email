"""开放多邮箱配置并补充邮箱运行状态。

Revision ID: 20260805_0004
Revises: 20260804_0003
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260805_0004"
down_revision: str | None = "20260804_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("mailbox_account") as batch_op:
        batch_op.add_column(
            sa.Column(
                "configuration_source",
                sa.String(length=32),
                nullable=False,
                server_default="legacy",
            )
        )
        batch_op.add_column(sa.Column("last_connection_error", sa.String(length=1000)))
        batch_op.add_column(sa.Column("last_sync_status", sa.String(length=32)))
        batch_op.add_column(sa.Column("last_sync_at", sa.DateTime()))
    op.create_index(
        "uq_mailbox_account_one_default_per_tenant",
        "mailbox_account",
        ["tenant_id"],
        unique=True,
        sqlite_where=sa.text("is_default = 1"),
        postgresql_where=sa.text("is_default = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_mailbox_account_one_default_per_tenant",
        table_name="mailbox_account",
    )
    with op.batch_alter_table("mailbox_account") as batch_op:
        batch_op.drop_column("last_sync_at")
        batch_op.drop_column("last_sync_status")
        batch_op.drop_column("last_connection_error")
        batch_op.drop_column("configuration_source")
