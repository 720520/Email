"""归并同一产品主体的分类份额。

Revision ID: 20260825_0015
Revises: 20260824_0014
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FundNav, FundProduct
from app.domain.fund_identity import fund_display_identity, master_product_identity

revision: str = "20260825_0015"
down_revision: str | None = "20260824_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    session = Session(bind=op.get_bind(), expire_on_commit=False)
    session.info["skip_tenant_scope"] = True
    try:
        tenant_ids = session.scalars(select(FundNav.tenant_id).distinct()).all()
        for tenant_id in tenant_ids:
            _repair_tenant(session, tenant_id)
        session.flush()
    finally:
        session.close()


def _repair_tenant(session: Session, tenant_id: int) -> None:
    nav_rows = list(
        session.scalars(
            select(FundNav).where(FundNav.tenant_id == tenant_id).order_by(FundNav.id)
        )
    )
    grouped_rows: dict[str, list[tuple[FundNav, str, str | None]]] = {}
    for row in nav_rows:
        identity = fund_display_identity(row.product_name, row.product_code)
        grouped_rows.setdefault(identity.group_name.casefold(), []).append(
            (row, identity.group_name, identity.share_class)
        )

    for entries in grouped_rows.values():
        base_entry = next((entry for entry in entries if entry[2] is None), entries[0])
        base_row, group_name, _ = base_entry
        canonical_code, canonical_name = master_product_identity(
            product_name=base_row.product_name,
            product_code=base_row.product_code,
            registration_code=base_row.registration_code,
            parent_product_code=base_row.parent_product_code,
            parent_product_name=base_row.parent_product_name,
        )
        for row, _, share_class in entries:
            row.master_product_code = canonical_code
            row.share_class = share_class
        _merge_products(
            session,
            tenant_id=tenant_id,
            canonical_code=canonical_code,
            canonical_name=canonical_name or group_name,
            entries=entries,
        )


def _merge_products(
    session: Session,
    *,
    tenant_id: int,
    canonical_code: str,
    canonical_name: str,
    entries: list[tuple[FundNav, str, str | None]],
) -> None:
    codes = {row.master_product_code for row, _, _ in entries}
    codes.update(row.product_code for row, _, _ in entries)
    products = list(
        session.scalars(
            select(FundProduct).where(
                FundProduct.tenant_id == tenant_id,
                FundProduct.product_code.in_(codes),
            )
        )
    )
    canonical = next(
        (product for product in products if product.product_code == canonical_code), None
    )
    if canonical is None:
        canonical = FundProduct(
            tenant_id=tenant_id,
            product_code=canonical_code,
            product_name=canonical_name,
        )
        session.add(canonical)
        session.flush()
    canonical.product_name = canonical_name

    for product in products:
        if product is canonical:
            continue
        _merge_product_fields(canonical, product)
        # 历史报表、合同和批次可能仍引用旧主档。旧主档不再匹配任何 FundNav，
        # 会自然退出产品中心，同时保留既有外键和审计链。


def _merge_product_fields(target: FundProduct, source: FundProduct) -> None:
    for field in (
        "source_investment_manager_info",
        "source_investment_strategy_info",
        "manual_investment_manager_info",
        "manual_investment_strategy_info",
        "latest_source_file",
    ):
        if not getattr(target, field) and getattr(source, field):
            setattr(target, field, getattr(source, field))
    target.investment_manager_manual = (
        target.investment_manager_manual or source.investment_manager_manual
    )
    target.investment_strategy_manual = (
        target.investment_strategy_manual or source.investment_strategy_manual
    )
    target.source_profile = {**(source.source_profile or {}), **(target.source_profile or {})}
    target.source_profile_meta = {
        **(source.source_profile_meta or {}),
        **(target.source_profile_meta or {}),
    }
    target.manual_profile = {**(source.manual_profile or {}), **(target.manual_profile or {})}
    if source.latest_source_date and (
        target.latest_source_date is None or source.latest_source_date > target.latest_source_date
    ):
        target.latest_source_date = source.latest_source_date
        target.latest_source_file = source.latest_source_file


def downgrade() -> None:
    # 归并后的主体关系无法无损恢复为历史错误分组。
    pass
