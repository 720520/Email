"""标准基金净值模型。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import CreatedAtMixin

if TYPE_CHECKING:
    from app.db.models.email_record import AttachmentRecord


class FundNav(CreatedAtMixin, Base):
    __tablename__ = "fund_nav"
    __table_args__ = (
        UniqueConstraint(
            "product_code",
            "nav_date",
            name="uq_fund_nav_product_code_nav_date",
        ),
        Index("ix_fund_nav_nav_date", "nav_date"),
        Index("ix_fund_nav_product_name", "product_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_code: Mapped[str] = mapped_column(String(64), nullable=False)
    nav_date: Mapped[date] = mapped_column(Date, nullable=False)
    unit_nav: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    total_nav: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    asset_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    source_file: Mapped[str] = mapped_column(String(500), nullable=False)
    source_sheet: Mapped[str | None] = mapped_column(String(255))
    source_row: Mapped[int | None] = mapped_column(Integer)
    source_type: Mapped[str | None] = mapped_column(String(64))
    attachment_id: Mapped[int | None] = mapped_column(
        ForeignKey("attachment_record.id", ondelete="RESTRICT"), index=True
    )

    attachment: Mapped[AttachmentRecord | None] = relationship(back_populates="nav_records")
