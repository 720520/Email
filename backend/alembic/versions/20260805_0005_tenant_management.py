"""增加平台管理员标记以开放租户管理。

Revision ID: 20260805_0005
Revises: 20260805_0004
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260805_0005"
down_revision: str | None = "20260805_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("app_user") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_platform_admin",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
    # 兼容既有安装：原全局 admin 是系统初始化管理员，升级后保留租户创建权限。
    app_user = sa.table(
        "app_user",
        sa.column("role", sa.String()),
        sa.column("is_platform_admin", sa.Boolean()),
    )
    op.execute(
        app_user.update()
        .where(app_user.c.role == "admin")
        .values(is_platform_admin=True)
    )


def downgrade() -> None:
    with op.batch_alter_table("app_user") as batch_op:
        batch_op.drop_column("is_platform_admin")
