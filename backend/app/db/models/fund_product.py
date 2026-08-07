"""基金产品主档；表格要素不可人工覆盖，说明字段允许人工维护。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import JSON, Boolean, Date, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import TenantOwnedMixin, TimestampMixin


class FundProduct(TenantOwnedMixin, TimestampMixin, Base):
    """按备案/产品主体归并的主档，不替代份额级每日净值快照。"""

    __tablename__ = "fund_product"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "product_code",
            name="uq_fund_product_tenant_product_code",
        ),
        Index("ix_fund_product_product_name", "product_name"),
        Index("ix_fund_product_latest_source_date", "latest_source_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_code: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # 原始说明保留最近一次托管附件中的非空内容，缺失时不会清空。
    source_investment_manager_info: Mapped[str | None] = mapped_column(Text)
    source_investment_strategy_info: Mapped[str | None] = mapped_column(Text)
    # 人工值与是否启用覆盖分开保存，便于恢复来源值并完整审计。
    manual_investment_manager_info: Mapped[str | None] = mapped_column(Text)
    manual_investment_strategy_info: Mapped[str | None] = mapped_column(Text)
    investment_manager_manual: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    investment_strategy_manual: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # 合同/邮件提取的扩展要素与人工覆盖分层保存；字段级来源写入 source_profile_meta。
    source_profile: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_profile_meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    manual_profile: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    latest_source_file: Mapped[str | None] = mapped_column(String(500))
    latest_source_date: Mapped[date | None] = mapped_column(Date)

    @property
    def investment_manager_info(self) -> str | None:
        if self.investment_manager_manual:
            return self.manual_investment_manager_info
        return self.source_investment_manager_info

    @property
    def investment_strategy_info(self) -> str | None:
        if self.investment_strategy_manual:
            return self.manual_investment_strategy_info
        return self.source_investment_strategy_info

    def effective_profile(self) -> dict:
        """返回人工值优先的有效要素，不改变任何来源数据。"""

        return {**(self.source_profile or {}), **(self.manual_profile or {})}
