"""基金运营后台查询响应。"""

from datetime import date, datetime

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
    subject: str
    sender: str
    receive_time: datetime
    attachment_count: int
    status: EmailStatus
    error_message: str | None


class FundNavListItem(BaseModel):
    id: int
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
    inserted_count: int
    duplicate_count: int
    exception_count: int
    status: str
    source_file: str = Field(max_length=500)
