"""基金运营后台查询响应。"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.db.models import EmailStatus, ExceptionSeverity, ExceptionStatus


class DashboardMetric(BaseModel):
    value: int
    label: str
    helper: str


class RecentExceptionItem(BaseModel):
    id: int
    category: str
    message: str
    source: str
    severity: ExceptionSeverity
    create_time: datetime


class DashboardResponse(BaseModel):
    business_date: date
    today_email_count: int
    success_email_count: int
    fund_count: int
    open_exception_count: int
    latest_nav_date: date | None
    latest_nav_count: int
    recent_exceptions: list[RecentExceptionItem]


class EmailListItem(BaseModel):
    id: int
    mailbox_account_id: int
    mailbox_name: str
    subject: str
    sender: str
    receive_time: datetime
    attachment_count: int
    status: EmailStatus
    error_message: str | None


class FundNavListItem(BaseModel):
    id: int
    mailbox_account_id: int
    mailbox_name: str
    product_name: str
    product_code: str
    nav_date: date
    unit_nav: str | None
    total_nav: str | None
    asset_value: str | None
    source_file: str
    fund_group_name: str
    share_class: str | None


class LatestFundNavDateResponse(BaseModel):
    """基金净值台账中当前可导出的最新估值日。"""

    latest_nav_date: date | None


class FundProductOption(BaseModel):
    product_name: str
    product_code: str
    fund_group_name: str
    share_class: str | None


class FundHistoryPoint(BaseModel):
    nav_date: date
    unit_nav: str | None
    total_nav: str | None


class FundHistoryResponse(BaseModel):
    product_name: str
    product_code: str
    points: list[FundHistoryPoint]


class ExceptionListItem(BaseModel):
    id: int
    mailbox_account_id: int
    mailbox_name: str
    email_id: int | None
    category: str
    exception_type: str
    severity: ExceptionSeverity
    product_code: str | None
    product_name: str | None
    source: str
    sheet_name: str | None
    row_number: int | None
    field_name: str | None
    raw_value: str | None
    message: str
    status: ExceptionStatus
    create_time: datetime


class ExceptionStatusUpdate(BaseModel):
    status: ExceptionStatus


class ManualReparseResponse(BaseModel):
    email_id: int
    attachment_id: int
    parse_session_id: int
    inserted_count: int
    duplicate_count: int
    exception_count: int
    valid_count: int
    invalid_count: int
    status: str
    source_file: str = Field(max_length=500)
    message: str
    records: list["ParseReviewRowResponse"]
    issues: list["ParseReviewIssue"]


class ParseReviewIssue(BaseModel):
    code: str
    severity: str
    message: str
    sheet_name: str | None = None
    row_number: int | None = None
    field_name: str | None = None
    raw_value: Any = None
    raw_data: dict[str, Any] | None = None


class ParseReviewRowResponse(BaseModel):
    id: int
    status: str
    source_sheet: str
    source_row: int
    source_type: str
    product_name: str | None
    product_code: str | None
    asset_code: str | None
    registration_code: str | None
    share_class: str | None
    nav_date: date | None
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
    investment_manager_info: str | None
    investment_strategy_info: str | None
    issues: list[ParseReviewIssue]
    original_data: dict[str, Any]
    validation_message: str | None
    is_edited: bool
    edit_reason: str | None
    row_version: int
    conflict_action: str
    existing_nav_id: int | None
    committed_nav_id: int | None


class ParseReviewSessionResponse(BaseModel):
    id: int
    attachment_id: int
    source_attachment_id: int | None
    status: str
    parser_version: str
    source_file: str
    row_count: int
    valid_count: int
    invalid_count: int
    ignored_count: int
    duplicate_count: int
    inserted_count: int
    error_message: str | None
    create_time: datetime
    update_time: datetime
    confirmed_at: datetime | None
    file_issues: list[ParseReviewIssue]
    rows: list[ParseReviewRowResponse] = Field(default_factory=list)


class ParseReviewRowUpdate(BaseModel):
    product_name: str | None = Field(default=None, max_length=255)
    product_code: str | None = Field(default=None, max_length=64)
    asset_code: str | None = Field(default=None, max_length=64)
    registration_code: str | None = Field(default=None, max_length=64)
    share_class: str | None = Field(default=None, max_length=32)
    nav_date: date | None = None
    unit_nav: Decimal | None = None
    total_nav: Decimal | None = None
    asset_value: Decimal | None = None
    asset_share: Decimal | None = None
    paid_in_capital: Decimal | None = None
    holding_shares: Decimal | None = None
    reference_market_value: Decimal | None = None
    total_assets: Decimal | None = None
    total_assets_nav_ratio: Decimal | None = None
    investor_name: str | None = Field(default=None, max_length=255)
    investor_account: str | None = Field(default=None, max_length=128)
    parent_unit_nav: Decimal | None = None
    parent_total_nav: Decimal | None = None
    parent_asset_value: Decimal | None = None
    parent_product_code: str | None = Field(default=None, max_length=64)
    parent_product_name: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    parent_paid_in_capital: Decimal | None = None
    investment_manager_info: str | None = None
    investment_strategy_info: str | None = None
    ignored: bool | None = None
    conflict_action: Literal["unresolved", "keep_existing", "replace_existing"] | None = None
    edit_reason: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(ge=1)


class ParseCommitResponse(BaseModel):
    parse_session_id: int
    status: str
    inserted_count: int
    duplicate_count: int
    exception_count: int
    message: str


class ParseTaskItem(BaseModel):
    id: int
    attachment_id: int
    source_file: str
    mailbox_name: str
    status: str
    attempt_count: int
    max_attempts: int
    parser_version: str | None
    inserted_count: int
    duplicate_count: int
    exception_count: int
    error_message: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ParseTaskSummaryResponse(BaseModel):
    queued: int
    running: int
    success: int
    partial_success: int
    duplicate: int
    failed: int
    recent: list[ParseTaskItem]
