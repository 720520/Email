"""增加基金产品主档和托管表格要素快照。

Revision ID: 20260805_0006
Revises: 20260805_0005
Create Date: 2026-08-05
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "20260805_0006"
down_revision: str | None = "20260805_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fund_product",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("source_investment_manager_info", sa.Text()),
        sa.Column("source_investment_strategy_info", sa.Text()),
        sa.Column("manual_investment_manager_info", sa.Text()),
        sa.Column("manual_investment_strategy_info", sa.Text()),
        sa.Column(
            "investment_manager_manual",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "investment_strategy_manual",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("latest_source_file", sa.String(length=500)),
        sa.Column("latest_source_date", sa.Date()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_fund_product_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fund_product")),
        sa.UniqueConstraint(
            "tenant_id",
            "product_code",
            name="uq_fund_product_tenant_product_code",
        ),
    )
    op.create_index(
        op.f("ix_fund_product_tenant_id"),
        "fund_product",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_fund_product_product_name",
        "fund_product",
        ["product_name"],
        unique=False,
    )
    op.create_index(
        "ix_fund_product_latest_source_date",
        "fund_product",
        ["latest_source_date"],
        unique=False,
    )

    with op.batch_alter_table("fund_nav") as batch_op:
        batch_op.add_column(sa.Column("master_product_code", sa.String(length=64)))
        batch_op.add_column(sa.Column("asset_code", sa.String(length=64)))
        batch_op.add_column(sa.Column("registration_code", sa.String(length=64)))
        batch_op.add_column(sa.Column("share_class", sa.String(length=32)))
        batch_op.add_column(sa.Column("asset_share", sa.Numeric(24, 4)))
        batch_op.add_column(sa.Column("paid_in_capital", sa.Numeric(24, 4)))
        batch_op.add_column(sa.Column("holding_shares", sa.Numeric(24, 4)))
        batch_op.add_column(sa.Column("reference_market_value", sa.Numeric(24, 4)))
        batch_op.add_column(sa.Column("total_assets", sa.Numeric(24, 4)))
        batch_op.add_column(sa.Column("total_assets_nav_ratio", sa.Numeric(20, 8)))
        batch_op.add_column(sa.Column("investor_name", sa.String(length=255)))
        batch_op.add_column(sa.Column("investor_account", sa.String(length=128)))
        batch_op.add_column(sa.Column("parent_unit_nav", sa.Numeric(20, 8)))
        batch_op.add_column(sa.Column("parent_total_nav", sa.Numeric(20, 8)))
        batch_op.add_column(sa.Column("parent_asset_value", sa.Numeric(24, 4)))
        batch_op.add_column(sa.Column("parent_product_code", sa.String(length=64)))
        batch_op.add_column(sa.Column("parent_product_name", sa.String(length=255)))
        batch_op.add_column(sa.Column("notes", sa.Text()))
        batch_op.add_column(sa.Column("parent_paid_in_capital", sa.Numeric(24, 4)))
    op.create_index(
        "ix_fund_nav_master_product_code",
        "fund_nav",
        ["master_product_code"],
        unique=False,
    )

    connection = op.get_bind()
    connection.execute(sa.text("UPDATE fund_nav SET master_product_code = product_code"))
    now = datetime.now(UTC).replace(tzinfo=None)
    connection.execute(
        sa.text(
            "INSERT INTO fund_product ("
            "tenant_id, product_code, product_name, latest_source_file, latest_source_date, "
            "investment_manager_manual, investment_strategy_manual, create_time, update_time"
            ") SELECT tenant_id, product_code, MAX(product_name), MAX(source_file), "
            "MAX(nav_date), 0, 0, :now, :now FROM fund_nav "
            "GROUP BY tenant_id, product_code"
        ),
        {"now": now},
    )


def downgrade() -> None:
    op.drop_index("ix_fund_nav_master_product_code", table_name="fund_nav")
    with op.batch_alter_table("fund_nav") as batch_op:
        batch_op.drop_column("parent_paid_in_capital")
        batch_op.drop_column("notes")
        batch_op.drop_column("parent_product_name")
        batch_op.drop_column("parent_product_code")
        batch_op.drop_column("parent_asset_value")
        batch_op.drop_column("parent_total_nav")
        batch_op.drop_column("parent_unit_nav")
        batch_op.drop_column("investor_account")
        batch_op.drop_column("investor_name")
        batch_op.drop_column("total_assets_nav_ratio")
        batch_op.drop_column("total_assets")
        batch_op.drop_column("reference_market_value")
        batch_op.drop_column("holding_shares")
        batch_op.drop_column("paid_in_capital")
        batch_op.drop_column("asset_share")
        batch_op.drop_column("share_class")
        batch_op.drop_column("registration_code")
        batch_op.drop_column("asset_code")
        batch_op.drop_column("master_product_code")
    op.drop_index("ix_fund_product_latest_source_date", table_name="fund_product")
    op.drop_index("ix_fund_product_product_name", table_name="fund_product")
    op.drop_index(op.f("ix_fund_product_tenant_id"), table_name="fund_product")
    op.drop_table("fund_product")
