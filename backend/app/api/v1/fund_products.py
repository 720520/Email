"""基金产品主档、托管要素统计和人工说明维护。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, TenantDatabaseSession, TenantScope, require_roles
from app.api.schemas.common import PageResponse
from app.api.schemas.fund_product import (
    FundProductDetail,
    FundProductListItem,
    FundProductNavUpdateItem,
    FundProductNavUpdateSummary,
    FundProductProfileUpdate,
    FundProductSnapshotItem,
    FundProductSummary,
)
from app.core.config import get_settings
from app.core.credential_security import audit_signing_key
from app.core.errors import AppError
from app.db.models import FundNav, FundProduct, UserRole
from app.services.audit_service import AuditService

router = APIRouter()
ProfileEditorScope = Annotated[
    TenantContext,
    Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR)),
]

_SNAPSHOT_FIELDS = (
    "nav_date",
    "asset_code",
    "product_name",
    "unit_nav",
    "total_nav",
    "asset_value",
    "paid_in_capital",
    "holding_shares",
    "reference_market_value",
    "total_assets",
    "total_assets_nav_ratio",
    "investor_name",
    "investor_account",
    "parent_unit_nav",
    "parent_total_nav",
    "parent_asset_value",
    "parent_product_code",
    "parent_product_name",
    "notes",
    "registration_code",
    "parent_paid_in_capital",
)


@router.get("/summary", response_model=FundProductSummary)
def product_summary(
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> FundProductSummary:
    del scope
    products = list(session.scalars(select(FundProduct).where(_visible_product())))
    latest_nav_date = session.scalar(select(func.max(FundNav.nav_date)))
    share_count = 0
    asset_value = Decimal("0")
    has_asset_value = False
    for product in products:
        rows = _latest_rows(session, product.product_code)
        share_count += len(rows)
        value = _representative_value(rows, "asset_value")
        if value is not None:
            asset_value += value
            has_asset_value = True
    return FundProductSummary(
        product_count=len(products),
        share_count=share_count,
        latest_nav_date=latest_nav_date,
        latest_asset_value=_decimal_text(asset_value) if has_asset_value else None,
        missing_manager_count=sum(not item.investment_manager_info for item in products),
        missing_strategy_count=sum(not item.investment_strategy_info for item in products),
    )


@router.get("/nav-update-status", response_model=FundProductNavUpdateSummary)
def nav_update_status(
    session: TenantDatabaseSession,
    scope: TenantScope,
    nav_date: date = Query(),
) -> FundProductNavUpdateSummary:
    del scope
    products = list(
        session.scalars(
            select(FundProduct)
            .where(_visible_product())
            .order_by(FundProduct.product_name, FundProduct.product_code)
        )
    )
    items: list[FundProductNavUpdateItem] = []
    for product in products:
        latest_date = session.scalar(
            select(func.max(FundNav.nav_date)).where(
                FundNav.master_product_code == product.product_code
            )
        )
        expected_rows = _reference_rows(session, product.product_code, nav_date)
        expected_codes = {
            row.product_code for row in expected_rows if row.product_code
        } or {product.product_code}
        updated_rows = list(
            session.scalars(
                select(FundNav).where(
                    FundNav.master_product_code == product.product_code,
                    FundNav.nav_date == nav_date,
                )
            )
        )
        updated_codes = {row.product_code for row in updated_rows if row.product_code}
        missing_codes = expected_codes - updated_codes
        if not updated_codes:
            status = "pending"
        elif missing_codes:
            status = "partial"
        else:
            status = "updated"
        items.append(
            FundProductNavUpdateItem(
                product_id=product.id,
                product_code=product.product_code,
                product_name=product.product_name,
                nav_date=nav_date,
                status=status,
                updated_share_count=len(updated_codes),
                expected_share_count=len(expected_codes),
                updated_share_codes=sorted(updated_codes),
                missing_share_codes=sorted(missing_codes),
                latest_update_date=latest_date,
            )
        )
    return FundProductNavUpdateSummary(
        nav_date=nav_date,
        total_count=len(items),
        updated_count=sum(item.status == "updated" for item in items),
        partial_count=sum(item.status == "partial" for item in items),
        pending_count=sum(item.status == "pending" for item in items),
        items=items,
    )


@router.get("", response_model=PageResponse[FundProductListItem])
def list_fund_products(
    session: TenantDatabaseSession,
    scope: TenantScope,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None, max_length=200),
) -> PageResponse[FundProductListItem]:
    del scope
    conditions = [_visible_product()]
    if keyword and keyword.strip():
        search = keyword.strip()
        conditions.append(
            or_(
                FundProduct.product_name.contains(search, autoescape=True),
                FundProduct.product_code.contains(search, autoescape=True),
            )
        )
    total = session.scalar(select(func.count(FundProduct.id)).where(*conditions)) or 0
    products = session.scalars(
        select(FundProduct)
        .where(*conditions)
        .order_by(FundProduct.product_name, FundProduct.product_code)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return PageResponse(
        items=[_list_item(session, product) for product in products],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{product_id}", response_model=FundProductDetail)
def get_fund_product(
    product_id: int,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> FundProductDetail:
    del scope
    product = _get_visible_product(session, product_id)
    return _detail(session, product)


@router.patch("/{product_id}/profile", response_model=FundProductDetail)
def update_fund_product_profile(
    product_id: int,
    payload: FundProductProfileUpdate,
    request: Request,
    session: TenantDatabaseSession,
    scope: ProfileEditorScope,
) -> FundProductDetail:
    product = _get_visible_product(session, product_id)
    changed_fields: list[str] = []
    if payload.restore_investment_manager_from_source:
        product.investment_manager_manual = False
        product.manual_investment_manager_info = None
        changed_fields.append("investment_manager_info:restore_source")
    elif "investment_manager_info" in payload.model_fields_set:
        product.manual_investment_manager_info = _clean_profile(
            payload.investment_manager_info
        )
        product.investment_manager_manual = True
        changed_fields.append("investment_manager_info:manual")

    if payload.restore_investment_strategy_from_source:
        product.investment_strategy_manual = False
        product.manual_investment_strategy_info = None
        changed_fields.append("investment_strategy_info:restore_source")
    elif "investment_strategy_info" in payload.model_fields_set:
        product.manual_investment_strategy_info = _clean_profile(
            payload.investment_strategy_info
        )
        product.investment_strategy_manual = True
        changed_fields.append("investment_strategy_info:manual")

    if "custodian_platform_url" in payload.model_fields_set:
        manual_profile = dict(product.manual_profile or {})
        if payload.custodian_platform_url:
            manual_profile["custodian_platform_url"] = payload.custodian_platform_url
        else:
            manual_profile.pop("custodian_platform_url", None)
        product.manual_profile = manual_profile
        changed_fields.append("custodian_platform_url:manual")

    AuditService(audit_signing_key(get_settings().security)).append(
        session,
        tenant_id=scope.tenant_id,
        actor_user_id=scope.user.id,
        actor_username=scope.user.username,
        action="fund_product.profile.update",
        resource_type="fund_product",
        resource_id=product.id,
        outcome="success",
        detail={"changed_fields": changed_fields},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    session.commit()
    return _detail(session, product)


def _visible_product():
    return exists(
        select(FundNav.id).where(
            FundNav.master_product_code == FundProduct.product_code,
            FundNav.tenant_id == FundProduct.tenant_id,
        )
    )


def _get_visible_product(session: Session, product_id: int) -> FundProduct:
    product = session.scalar(
        select(FundProduct).where(FundProduct.id == product_id, _visible_product())
    )
    if product is None:
        raise AppError("FUND_PRODUCT_NOT_FOUND", "未找到该基金产品", status_code=404)
    return product


def _latest_rows(session: Session, master_product_code: str) -> list[FundNav]:
    latest_date = session.scalar(
        select(func.max(FundNav.nav_date)).where(
            FundNav.master_product_code == master_product_code
        )
    )
    if latest_date is None:
        return []
    return list(
        session.scalars(
            select(FundNav)
            .where(
                FundNav.master_product_code == master_product_code,
                FundNav.nav_date == latest_date,
            )
            .order_by(FundNav.share_class, FundNav.product_code, FundNav.id)
        )
    )


def _reference_rows(
    session: Session, master_product_code: str, on_or_before: date
) -> list[FundNav]:
    reference_date = session.scalar(
        select(func.max(FundNav.nav_date)).where(
            FundNav.master_product_code == master_product_code,
            FundNav.nav_date < on_or_before,
        )
    )
    if reference_date is None:
        current_rows = list(
            session.scalars(
                select(FundNav).where(
                    FundNav.master_product_code == master_product_code,
                    FundNav.nav_date == on_or_before,
                )
            )
        )
        return current_rows or _latest_rows(session, master_product_code)
    return list(
        session.scalars(
            select(FundNav)
            .where(
                FundNav.master_product_code == master_product_code,
                FundNav.nav_date == reference_date,
            )
            .order_by(FundNav.share_class, FundNav.product_code, FundNav.id)
        )
    )


def _representative_row(rows: list[FundNav]) -> FundNav | None:
    if not rows:
        return None
    total = next((item for item in rows if item.share_class == "总份额"), None)
    return total or (rows[0] if len(rows) == 1 else None)


def _representative_value(rows: list[FundNav], field: str) -> Decimal | None:
    representative = _representative_row(rows)
    if representative is not None:
        return getattr(representative, field)
    values = [getattr(item, field) for item in rows if getattr(item, field) is not None]
    return sum(values, Decimal("0")) if values else None


def _list_item(session: Session, product: FundProduct) -> FundProductListItem:
    rows = _latest_rows(session, product.product_code)
    representative = _representative_row(rows)
    profile = product.effective_profile()
    return FundProductListItem(
        id=product.id,
        product_code=product.product_code,
        product_name=product.product_name,
        latest_source_date=product.latest_source_date,
        share_count=len(rows),
        unit_nav=_decimal_text(representative.unit_nav if representative else None),
        total_nav=_decimal_text(representative.total_nav if representative else None),
        asset_value=_decimal_text(_representative_value(rows, "asset_value")),
        paid_in_capital=_decimal_text(_representative_value(rows, "paid_in_capital")),
        total_assets=_decimal_text(_representative_value(rows, "total_assets")),
        investment_manager_info=product.investment_manager_info,
        investment_strategy_info=product.investment_strategy_info,
        investment_manager_manual=product.investment_manager_manual,
        investment_strategy_manual=product.investment_strategy_manual,
        latest_source_file=product.latest_source_file,
        inception_date=_profile_text(profile, "inception_date"),
        strategy_category=_profile_text(profile, "strategy_category"),
        manager_name=_profile_text(profile, "manager_name"),
        custodian_name=_profile_text(profile, "custodian_name"),
        risk_level=_profile_text(profile, "risk_level"),
        custodian_platform_url=_profile_text(profile, "custodian_platform_url"),
    )


def _detail(session: Session, product: FundProduct) -> FundProductDetail:
    base = _list_item(session, product)
    rows = _latest_rows(session, product.product_code)
    return FundProductDetail(
        **base.model_dump(),
        source_investment_manager_info=product.source_investment_manager_info,
        source_investment_strategy_info=product.source_investment_strategy_info,
        manual_investment_manager_info=product.manual_investment_manager_info,
        manual_investment_strategy_info=product.manual_investment_strategy_info,
        create_time=product.create_time,
        update_time=product.update_time,
        latest_snapshots=[_snapshot_item(item) for item in rows],
    )


def _snapshot_item(item: FundNav) -> FundProductSnapshotItem:
    values: dict[str, Any] = {
        field: getattr(item, field) for field in _SNAPSHOT_FIELDS
    }
    available = sum(value is not None and value != "" for value in values.values())
    return FundProductSnapshotItem(
        id=item.id,
        mailbox_account_id=item.mailbox_account_id,
        nav_date=item.nav_date,
        product_code=item.product_code,
        product_name=item.product_name,
        asset_code=item.asset_code,
        registration_code=item.registration_code,
        share_class=item.share_class,
        unit_nav=_decimal_text(item.unit_nav),
        total_nav=_decimal_text(item.total_nav),
        asset_value=_decimal_text(item.asset_value),
        asset_share=_decimal_text(item.asset_share),
        paid_in_capital=_decimal_text(item.paid_in_capital),
        holding_shares=_decimal_text(item.holding_shares),
        reference_market_value=_decimal_text(item.reference_market_value),
        total_assets=_decimal_text(item.total_assets),
        total_assets_nav_ratio=_decimal_text(item.total_assets_nav_ratio),
        investor_name=item.investor_name,
        investor_account=item.investor_account,
        parent_unit_nav=_decimal_text(item.parent_unit_nav),
        parent_total_nav=_decimal_text(item.parent_total_nav),
        parent_asset_value=_decimal_text(item.parent_asset_value),
        parent_product_code=item.parent_product_code,
        parent_product_name=item.parent_product_name,
        notes=item.notes,
        parent_paid_in_capital=_decimal_text(item.parent_paid_in_capital),
        source_file=item.source_file,
        available_field_count=available,
    )


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _clean_profile(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _profile_text(profile: dict, key: str) -> str | None:
    value = profile.get(key)
    return str(value).strip() if value is not None and str(value).strip() else None
