"""标准基金净值模型。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import CreatedAtMixin, MailboxOwnedMixin

if TYPE_CHECKING:
    from app.db.models.email_record import AttachmentRecord


class FundNav(MailboxOwnedMixin, CreatedAtMixin, Base):
    __tablename__ = "fund_nav"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "product_code",
            "nav_date",
            name="uq_fund_nav_tenant_product_code_nav_date",
        ),
        Index("ix_fund_nav_nav_date", "nav_date"),
        Index("ix_fund_nav_product_name", "product_name"),
        Index("ix_fund_nav_master_product_code", "master_product_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_code: Mapped[str] = mapped_column(String(64), nullable=False)
    master_product_code: Mapped[str | None] = mapped_column(String(64))
    asset_code: Mapped[str | None] = mapped_column(String(64))
    registration_code: Mapped[str | None] = mapped_column(String(64))
    share_class: Mapped[str | None] = mapped_column(String(32))
    nav_date: Mapped[date] = mapped_column(Date, nullable=False)
    unit_nav: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    total_nav: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    asset_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    asset_share: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    paid_in_capital: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    holding_shares: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    reference_market_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    total_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    total_assets_nav_ratio: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    investor_name: Mapped[str | None] = mapped_column(String(255))
    investor_account: Mapped[str | None] = mapped_column(String(128))
    parent_unit_nav: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    parent_total_nav: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    parent_asset_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    parent_product_code: Mapped[str | None] = mapped_column(String(64))
    parent_product_name: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    parent_paid_in_capital: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    source_file: Mapped[str] = mapped_column(String(500), nullable=False)
    source_sheet: Mapped[str | None] = mapped_column(String(255))
    source_row: Mapped[int | None] = mapped_column(Integer)
    source_type: Mapped[str | None] = mapped_column(String(64))
    attachment_id: Mapped[int | None] = mapped_column(
        ForeignKey("attachment_record.id", ondelete="RESTRICT"), index=True
    )

    attachment: Mapped[AttachmentRecord | None] = relationship(back_populates="nav_records")
