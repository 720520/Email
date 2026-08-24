"""增加单份报表快照固定信息和不可变文件版本。

Revision ID: 20260821_0011
Revises: 20260821_0010
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0011"
down_revision: str | None = "20260821_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("report_run") as batch:
        batch.add_column(sa.Column("template_version_id", sa.Integer()))
        batch.add_column(
            sa.Column("field_definition_versions", sa.JSON(), nullable=False, server_default="{}")
        )
        batch.add_column(sa.Column("current_version_id", sa.Integer()))
        batch.add_column(sa.Column("error_stage", sa.String(length=64)))
        batch.add_column(sa.Column("error_code", sa.String(length=128)))
        batch.create_foreign_key(
            "fk_report_run_template_version",
            "report_template_version",
            ["template_version_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index("ix_report_run_template_version_id", ["template_version_id"])
        batch.create_index("ix_report_run_current_version_id", ["current_version_id"])

    op.create_table(
        "report_file_version",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("report_run_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("stored_path", sa.String(length=1000), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["report_run_id"], ["report_run.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "report_run_id", "version", name="uq_report_file_version"),
    )
    op.create_index("ix_report_file_version_tenant_id", "report_file_version", ["tenant_id"])
    op.create_index(
        "ix_report_file_version_report_run_id", "report_file_version", ["report_run_id"]
    )
    op.create_index(
        "ix_report_file_version_created_by_user_id", "report_file_version", ["created_by_user_id"]
    )
    op.create_index(
        "ix_report_file_version_run_time", "report_file_version", ["report_run_id", "create_time"]
    )

    # 旧的成功记录回填为文件版本 1，下载行为保持兼容。
    op.execute(
        sa.text(
            """
            INSERT INTO report_file_version (
                tenant_id, report_run_id, version, source, filename, stored_path,
                content_hash, file_size, created_by_user_id, create_time
            )
            SELECT tenant_id, id, 1, 'generated', output_filename, output_path,
                   '', 0, created_by_user_id, create_time
            FROM report_run
            WHERE status = 'success' AND output_path IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE report_run
            SET current_version_id = (
                SELECT id FROM report_file_version
                WHERE report_file_version.report_run_id = report_run.id AND version = 1
            )
            WHERE status = 'success' AND output_path IS NOT NULL
            """
        )
    )
    with op.batch_alter_table("report_run") as batch:
        batch.create_foreign_key(
            "fk_report_run_current_version",
            "report_file_version",
            ["current_version_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("report_run") as batch:
        batch.drop_constraint("fk_report_run_current_version", type_="foreignkey")
    op.drop_table("report_file_version")
    with op.batch_alter_table("report_run") as batch:
        batch.drop_index("ix_report_run_current_version_id")
        batch.drop_index("ix_report_run_template_version_id")
        batch.drop_constraint("fk_report_run_template_version", type_="foreignkey")
        batch.drop_column("error_code")
        batch.drop_column("error_stage")
        batch.drop_column("current_version_id")
        batch.drop_column("field_definition_versions")
        batch.drop_column("template_version_id")
