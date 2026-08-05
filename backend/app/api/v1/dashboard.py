"""基金运营数据概览。"""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from sqlalchemy import distinct, func, select

from app.api.deps import TenantDatabaseSession, TenantScope
from app.api.schemas.operations import DashboardResponse, RecentExceptionItem
from app.core.config import get_settings
from app.db.models import (
    AttachmentRecord,
    EmailRecord,
    EmailStatus,
    ExceptionRecord,
    ExceptionStatus,
    FundNav,
)
from app.domain.exception_categories import exception_category

router = APIRouter()


@router.get("", response_model=DashboardResponse)
def dashboard(session: TenantDatabaseSession, scope: TenantScope) -> DashboardResponse:
    del scope
    settings = get_settings()
    timezone = ZoneInfo(settings.storage.archive_timezone)
    business_date = datetime.now(timezone).date()
    start_local = datetime.combine(business_date, time.min, tzinfo=timezone)
    start_utc = start_local.astimezone(UTC)
    end_utc = (start_local + timedelta(days=1)).astimezone(UTC)

    today_email_count = session.scalar(
        select(func.count(EmailRecord.id)).where(
            EmailRecord.receive_time >= start_utc,
            EmailRecord.receive_time < end_utc,
        )
    ) or 0
    success_email_count = session.scalar(
        select(func.count(EmailRecord.id)).where(
            EmailRecord.receive_time >= start_utc,
            EmailRecord.receive_time < end_utc,
            EmailRecord.status == EmailStatus.SUCCESS,
        )
    ) or 0
    fund_count = session.scalar(select(func.count(distinct(FundNav.product_code)))) or 0
    open_exception_count = session.scalar(
        select(func.count(ExceptionRecord.id)).where(
            ExceptionRecord.status == ExceptionStatus.OPEN
        )
    ) or 0
    latest_nav_date = session.scalar(select(func.max(FundNav.nav_date)))
    latest_nav_count = 0
    if latest_nav_date is not None:
        latest_nav_count = session.scalar(
            select(func.count(FundNav.id)).where(FundNav.nav_date == latest_nav_date)
        ) or 0

    recent_statement = (
        select(ExceptionRecord, AttachmentRecord.original_name, EmailRecord.subject)
        .outerjoin(
            AttachmentRecord,
            ExceptionRecord.attachment_id == AttachmentRecord.id,
        )
        .outerjoin(EmailRecord, ExceptionRecord.email_id == EmailRecord.id)
        .where(ExceptionRecord.status == ExceptionStatus.OPEN)
        .order_by(ExceptionRecord.create_time.desc(), ExceptionRecord.id.desc())
        .limit(5)
    )
    recent_exceptions = [
        RecentExceptionItem(
            id=exception.id,
            category=exception_category(exception.exception_type),
            message=exception.message,
            source=attachment_name or subject or "系统",
            severity=exception.severity,
            create_time=exception.create_time,
        )
        for exception, attachment_name, subject in session.execute(recent_statement)
    ]
    return DashboardResponse(
        business_date=business_date,
        today_email_count=today_email_count,
        success_email_count=success_email_count,
        fund_count=fund_count,
        open_exception_count=open_exception_count,
        latest_nav_date=latest_nav_date,
        latest_nav_count=latest_nav_count,
        recent_exceptions=recent_exceptions,
    )
