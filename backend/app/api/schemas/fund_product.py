"""产品要素统计、详情和可编辑说明字段模型。"""

from datetime import date, datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator


class FundProductSummary(BaseModel):
    product_count: int
    share_count: int
    latest_nav_date: date | None
    latest_asset_value: str | None
    missing_manager_count: int
    missing_strategy_count: int


class FundProductNavUpdateItem(BaseModel):
    product_id: int
    product_code: str
    product_name: str
    nav_date: date
    status: str
    updated_share_count: int
    expected_share_count: int
    updated_share_codes: list[str] = Field(default_factory=list)
    missing_share_codes: list[str] = Field(default_factory=list)
    latest_update_date: date | None = None


class FundProductNavUpdateSummary(BaseModel):
    nav_date: date
    total_count: int
    updated_count: int
    partial_count: int
    pending_count: int
    items: list[FundProductNavUpdateItem]


class FundProductListItem(BaseModel):
    id: int
    product_code: str
    product_name: str
    latest_source_date: date | None
    share_count: int
    unit_nav: str | None
    total_nav: str | None
    asset_value: str | None
    paid_in_capital: str | None
    total_assets: str | None
    investment_manager_info: str | None
    investment_strategy_info: str | None
    investment_manager_manual: bool
    investment_strategy_manual: bool
    latest_source_file: str | None
    inception_date: str | None = None
    strategy_category: str | None = None
    manager_name: str | None = None
    custodian_name: str | None = None
    risk_level: str | None = None
    custodian_platform_url: str | None = None


class FundProductSnapshotItem(BaseModel):
    id: int
    mailbox_account_id: int
    nav_date: date
    product_code: str
    product_name: str
    asset_code: str | None
    registration_code: str | None
    share_class: str | None
    unit_nav: str | None
    total_nav: str | None
    asset_value: str | None
    asset_share: str | None
    paid_in_capital: str | None
    holding_shares: str | None
    reference_market_value: str | None
    total_assets: str | None
    total_assets_nav_ratio: str | None
    investor_name: str | None
    investor_account: str | None
    parent_unit_nav: str | None
    parent_total_nav: str | None
    parent_asset_value: str | None
    parent_product_code: str | None
    parent_product_name: str | None
    notes: str | None
    parent_paid_in_capital: str | None
    source_file: str
    available_field_count: int
    total_field_count: int = 21


class FundProductDetail(FundProductListItem):
    source_investment_manager_info: str | None
    source_investment_strategy_info: str | None
    manual_investment_manager_info: str | None
    manual_investment_strategy_info: str | None
    create_time: datetime
    update_time: datetime
    latest_snapshots: list[FundProductSnapshotItem]


class FundProductProfileUpdate(BaseModel):
    investment_manager_info: str | None = Field(default=None, max_length=20_000)
    investment_strategy_info: str | None = Field(default=None, max_length=20_000)
    restore_investment_manager_from_source: bool = False
    restore_investment_strategy_from_source: bool = False
    custodian_platform_url: str | None = Field(default=None, max_length=2000)

    @field_validator("custodian_platform_url")
    @classmethod
    def validate_platform_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = value.strip()
        parsed = urlsplit(cleaned)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("托管平台链接必须使用 http:// 或 https://")
        return cleaned

    @model_validator(mode="after")
    def validate_update(self) -> "FundProductProfileUpdate":
        if (
            "investment_manager_info" not in self.model_fields_set
            and "investment_strategy_info" not in self.model_fields_set
            and not self.restore_investment_manager_from_source
            and not self.restore_investment_strategy_from_source
            and "custodian_platform_url" not in self.model_fields_set
        ):
            raise ValueError("至少提交一项经理、策略或托管平台信息变更")
        if (
            "investment_manager_info" in self.model_fields_set
            and self.restore_investment_manager_from_source
        ):
            raise ValueError("投资经理信息不能同时人工覆盖并恢复来源值")
        if (
            "investment_strategy_info" in self.model_fields_set
            and self.restore_investment_strategy_from_source
        ):
            raise ValueError("投资策略信息不能同时人工覆盖并恢复来源值")
        return self
