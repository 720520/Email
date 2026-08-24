"""增加 PPTX 模板草稿、校验和不可变发布版本。

Revision ID: 20260821_0010
Revises: 20260821_0009
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0010"
down_revision: str | None = "20260821_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_template_version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("original_name", sa.String(length=500), nullable=False),
        sa.Column("stored_path", sa.String(length=1000), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("required_fields", sa.JSON(), nullable=False),
        sa.Column("required_components", sa.JSON(), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime()),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("published_by_user_id", sa.Integer()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["template_id"], ["report_template.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "template_id", "version", name="uq_report_template_version"
        ),
    )
    op.create_index(
        "ix_report_template_version_tenant_id", "report_template_version", ["tenant_id"]
    )
    op.create_index(
        "ix_report_template_version_template_id",
        "report_template_version",
        ["template_id"],
    )
    op.create_index(
        "ix_report_template_version_created_by_user_id",
        "report_template_version",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_report_template_version_published_by_user_id",
        "report_template_version",
        ["published_by_user_id"],
    )
    op.create_index(
        "ix_report_template_version_status",
        "report_template_version",
        ["tenant_id", "status"],
    )
    # 旧模板视为已发布 v1，保持 uploaded:{id} 历史引用可用。
    op.execute(
        sa.text(
            """
            INSERT INTO report_template_version (
                tenant_id, template_id, version, status, original_name, stored_path,
                content_hash, required_fields, required_components, validation_errors,
                published_at, created_by_user_id, published_by_user_id, create_time
            )
            SELECT tenant_id, id, 1, 'published', original_name, stored_path,
                   content_hash, '[]', '[]', '[]', create_time,
                   created_by_user_id, created_by_user_id, create_time
            FROM report_template
            """
        )
    )


def downgrade() -> None:
    op.drop_table("report_template_version")
