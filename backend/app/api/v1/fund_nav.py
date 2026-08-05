"""基金净值列表、产品搜索、历史曲线和 Excel 导出。"""

from datetime import date

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select

from app.api.deps import TenantDatabaseSession, TenantScope
from app.api.schemas.common import PageResponse
from app.api.schemas.operations import (
    FundHistoryPoint,
    FundHistoryResponse,
    FundNavListItem,
    FundProductOption,
    LatestFundNavDateResponse,
)
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import FundNav, MailboxAccount
from app.db.session import get_database_manager
from app.domain.fund_identity import fund_display_identity, fund_display_sort_key
from app.services.export_service import DailyExcelExportService

router = APIRouter()


@router.get("", response_model=PageResponse[FundNavListItem])
def list_fund_nav(
    session: TenantDatabaseSession,
    scope: TenantScope,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None, max_length=200),
    product_code: str | None = Query(default=None, max_length=64),
    date_from: date | None = None,
    date_to: date | None = None,
    mailbox_account_id: int | None = Query(default=None, ge=1),
) -> PageResponse[FundNavListItem]:
    if date_from and date_to and date_from > date_to:
        raise AppError("INVALID_DATE_RANGE", "开始日期不能晚于结束日期")
    conditions = []
    if mailbox_account_id is not None:
        if mailbox_account_id not in scope.mailbox_ids:
            raise AppError("FORBIDDEN", "当前账号没有查看该邮箱的权限", status_code=403)
        conditions.append(FundNav.mailbox_account_id == mailbox_account_id)
    if keyword and keyword.strip():
        search = keyword.strip()
        conditions.append(
            or_(
                FundNav.product_name.contains(search, autoescape=True),
                FundNav.product_code.contains(search, autoescape=True),
            )
        )
    if product_code and product_code.strip():
        conditions.append(FundNav.product_code == product_code.strip().upper())
    if date_from is not None:
        conditions.append(FundNav.nav_date >= date_from)
    if date_to is not None:
        conditions.append(FundNav.nav_date <= date_to)

    total = session.scalar(select(func.count(FundNav.id)).where(*conditions)) or 0
    statement = (
        select(FundNav, MailboxAccount.display_name)
        .join(MailboxAccount, MailboxAccount.id == FundNav.mailbox_account_id)
        .where(*conditions)
        .order_by(
            FundNav.nav_date.desc(),
            FundNav.product_name,
            FundNav.product_code,
            FundNav.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items: list[FundNavListItem] = []
    for item, mailbox_name in session.execute(statement):
        identity = fund_display_identity(item.product_name, item.product_code)
        items.append(FundNavListItem(
            id=item.id,
            mailbox_account_id=item.mailbox_account_id,
            mailbox_name=mailbox_name,
            product_name=item.product_name,
            product_code=item.product_code,
            nav_date=item.nav_date,
            unit_nav=_decimal_text(item.unit_nav),
            total_nav=_decimal_text(item.total_nav),
            asset_value=_decimal_text(item.asset_value),
            source_file=item.source_file,
            fund_group_name=identity.group_name,
            share_class=identity.share_class,
        ))
    return PageResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/latest-date", response_model=LatestFundNavDateResponse)
def latest_fund_nav_date(
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> LatestFundNavDateResponse:
    """返回数据库最大净值日期，供页面确定默认导出业务日期。"""

    del scope
    return LatestFundNavDateResponse(
        latest_nav_date=session.scalar(select(func.max(FundNav.nav_date)))
    )


@router.get("/products", response_model=list[FundProductOption])
def list_products(
    session: TenantDatabaseSession,
    scope: TenantScope,
    keyword: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=1000, ge=1, le=2000),
) -> list[FundProductOption]:
    del scope
    conditions = []
    if keyword and keyword.strip():
        search = keyword.strip()
        conditions.append(
            or_(
                FundNav.product_name.contains(search, autoescape=True),
                FundNav.product_code.contains(search, autoescape=True),
            )
        )
    statement = select(FundNav.product_name, FundNav.product_code).where(*conditions).distinct()
    products = list(session.execute(statement))
    products.sort(key=lambda item: fund_display_sort_key(item[0], item[1]))

    result: list[FundProductOption] = []
    for name, code in products[:limit]:
        identity = fund_display_identity(name, code)
        result.append(
            FundProductOption(
                product_name=name,
                product_code=code,
                fund_group_name=identity.group_name,
                share_class=identity.share_class,
            )
        )
    return result


@router.get("/history", response_model=FundHistoryResponse)
def fund_history(
    session: TenantDatabaseSession,
    scope: TenantScope,
    product_code: str = Query(min_length=1, max_length=64),
) -> FundHistoryResponse:
    del scope
    code = product_code.strip().upper()
    statement = (
        select(FundNav)
        .where(FundNav.product_code == code)
        .order_by(FundNav.nav_date, FundNav.id)
        .limit(5000)
    )
    records = list(session.scalars(statement))
    if not records:
        raise AppError("FUND_NOT_FOUND", "未找到该产品的历史净值", status_code=404)
    return FundHistoryResponse(
        product_name=records[-1].product_name,
        product_code=code,
        points=[
            FundHistoryPoint(
                nav_date=item.nav_date,
                unit_nav=_decimal_text(item.unit_nav),
                total_nav=_decimal_text(item.total_nav),
            )
            for item in records
        ],
    )


@router.get("/export")
def export_fund_nav(report_date: date, scope: TenantScope) -> FileResponse:
    settings = get_settings()
    result = DailyExcelExportService(
        settings,
        get_database_manager().session_factory,
        tenant_id=scope.tenant_id,
        mailbox_ids=scope.mailbox_ids,
        actor_user_id=scope.user.id,
        actor_username=scope.user.username,
    ).export(report_date)
    return FileResponse(
        result.output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=settings.storage.daily_export_filename,
    )


def _decimal_text(value) -> str | None:
    return None if value is None else format(value, "f")
