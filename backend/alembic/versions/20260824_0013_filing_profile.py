"""增加租户备案资料库。

Revision ID: 20260824_0013
Revises: 20260821_0012
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "20260824_0013"
down_revision: str | None = "20260821_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "filing_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("field_values", sa.JSON(), nullable=False),
        sa.Column("document_notes", sa.JSON(), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", name="uq_filing_profile_tenant"),
    )
    op.create_index("ix_filing_profile_tenant_id", "filing_profile", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("filing_profile")
