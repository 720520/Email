"""公司与产品资料主体的初始化服务。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Entity,
    FundProduct,
    FundProductProfile,
    OrganizationProfile,
    Tenant,
)


class ProfileService:
    """确保业务主档和统一主体一一对应。"""

    @staticmethod
    def ensure_organization(
        session: Session,
        tenant: Tenant,
        *,
        created_by_user_id: int | None = None,
    ) -> OrganizationProfile:
        profile = session.scalar(
            select(OrganizationProfile).where(OrganizationProfile.tenant_id == tenant.id)
        )
        if profile is not None:
            return profile
        entity = Entity(
            tenant_id=tenant.id,
            entity_type="organization",
            display_name=tenant.name,
            external_code=f"tenant:{tenant.id}:organization",
            created_by_user_id=created_by_user_id,
        )
        session.add(entity)
        session.flush()
        profile = OrganizationProfile(tenant_id=tenant.id, entity_id=entity.id)
        session.add(profile)
        session.flush()
        return profile

    @staticmethod
    def ensure_product(session: Session, product: FundProduct) -> FundProductProfile:
        session.flush()
        entity = session.get(Entity, product.entity_id) if product.entity_id is not None else None
        if entity is None:
            entity = Entity(
                tenant_id=product.tenant_id,
                entity_type="product",
                display_name=product.product_name,
                external_code=f"fund-product:{product.id}",
            )
            session.add(entity)
            session.flush()
            product.entity_id = entity.id
        else:
            entity.display_name = product.product_name
        profile = session.scalar(
            select(FundProductProfile).where(FundProductProfile.fund_product_id == product.id)
        )
        if profile is None:
            profile = FundProductProfile(
                tenant_id=product.tenant_id,
                entity_id=entity.id,
                fund_product_id=product.id,
            )
            session.add(profile)
        return profile
