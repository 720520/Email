"""增加后台用户角色和会话版本。

Revision ID: 20260729_0002
Revises: 20260728_0001
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260729_0002"
down_revision: str | None = "20260728_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("app_user") as batch_op:
        batch_op.add_column(
            sa.Column(
                "role",
                sa.Enum(
                    "admin",
                    "operator",
                    "viewer",
                    name="user_role",
                    native_enum=False,
                ),
                nullable=False,
                server_default="operator",
            )
        )
        batch_op.add_column(
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="1")
        )


def downgrade() -> None:
    with op.batch_alter_table("app_user") as batch_op:
        batch_op.drop_column("token_version")
        batch_op.drop_column("role")
