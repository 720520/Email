"""阶段 2 公司资料、产品资料和旧材料人工归属。"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from app.api.deps import TenantDatabaseSession, TenantScope
from app.api.schemas.data_governance import (
    EntityItem,
    FieldDefinitionItem,
    FieldValueItem,
    ProductMaterialAssign,
    ProductMaterialAttributionItem,
    ProductProfileSummary,
    ProfileDetail,
    SourceDocumentItem,
)
from app.core.errors import AppError
from app.db.models import (
    DocumentRelation,
    Entity,
    FieldDefinition,
    FieldValue,
    FundProduct,
    FundProductProfile,
    OrganizationProfile,
    ProductMaterialAttribution,
    SourceDocument,
    UserRole,
)
from app.services.request_audit_service import RequestAuditService
from app.services.resource_permission_service import (
    ResourceAction,
    ResourcePermissionService,
    ResourceSensitivity,
)

router = APIRouter()
permissions = ResourcePermissionService()
audits = RequestAuditService()


@router.get("/profiles/company", response_model=ProfileDetail)
def get_company_profile(session: TenantDatabaseSession, scope: TenantScope) -> ProfileDetail:
    profile = session.scalar(select(OrganizationProfile).order_by(OrganizationProfile.id).limit(1))
    if profile is None:
        raise AppError("COMPANY_PROFILE_NOT_FOUND", "公司资料尚未初始化", status_code=404)
    entity = session.get(Entity, profile.entity_id)
    if entity is None:
        raise AppError("COMPANY_PROFILE_BROKEN", "公司主体关联缺失", status_code=500)
    permissions.require(session, scope, ResourceAction.READ, entity_id=entity.id)
    return _profile_detail(session, scope, entity)


@router.get("/profiles/products", response_model=list[ProductProfileSummary])
def list_product_profiles(
    session: TenantDatabaseSession, scope: TenantScope
) -> list[ProductProfileSummary]:
    permissions.require(session, scope, ResourceAction.READ)
    rows = session.execute(
        select(FundProductProfile, FundProduct, Entity)
        .join(FundProduct, FundProductProfile.fund_product_id == FundProduct.id)
        .join(Entity, FundProductProfile.entity_id == Entity.id)
        .order_by(FundProduct.product_name)
    )
    return [
        ProductProfileSummary(
            entity=EntityItem.model_validate(entity, from_attributes=True),
            fund_product_id=product.id,
            product_code=product.product_code,
            product_name=product.product_name,
            document_count=_product_document_count(session, entity.id),
        )
        for _, product, entity in rows
    ]


@router.get("/profiles/products/{entity_id}", response_model=ProfileDetail)
def get_product_profile(
    entity_id: int, session: TenantDatabaseSession, scope: TenantScope
) -> ProfileDetail:
    profile = session.scalar(
        select(FundProductProfile).where(FundProductProfile.entity_id == entity_id)
    )
    entity = session.get(Entity, entity_id)
    if profile is None or entity is None:
        raise AppError("PRODUCT_PROFILE_NOT_FOUND", "产品资料不存在", status_code=404)
    permissions.require(session, scope, ResourceAction.READ, entity_id=entity.id)
    return _profile_detail(session, scope, entity, relation_only=True)


@router.get("/product-material-attributions", response_model=list[ProductMaterialAttributionItem])
def list_product_material_attributions(
    session: TenantDatabaseSession,
    scope: TenantScope,
    status: str = Query(default="pending", pattern="^(pending|assigned)$"),
) -> list[ProductMaterialAttributionItem]:
    _require_admin(scope)
    rows = session.execute(
        select(ProductMaterialAttribution, SourceDocument)
        .join(SourceDocument, ProductMaterialAttribution.document_id == SourceDocument.id)
        .where(ProductMaterialAttribution.status == status)
        .order_by(ProductMaterialAttribution.id)
    )
    return [_attribution_item(item, document) for item, document in rows]


@router.post(
    "/product-material-attributions/{attribution_id}/assign",
    response_model=ProductMaterialAttributionItem,
)
def assign_product_material(
    attribution_id: int,
    payload: ProductMaterialAssign,
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> ProductMaterialAttributionItem:
    _require_admin(scope)
    item = session.get(ProductMaterialAttribution, attribution_id)
    if item is None:
        raise AppError("MATERIAL_ATTRIBUTION_NOT_FOUND", "待归属材料不存在", status_code=404)
    if item.status != "pending":
        raise AppError("MATERIAL_ALREADY_ASSIGNED", "该材料已经完成归属", status_code=409)
    product_profile = session.scalar(
        select(FundProductProfile).where(FundProductProfile.entity_id == payload.product_entity_id)
    )
    product_entity = session.get(Entity, payload.product_entity_id)
    if product_profile is None or product_entity is None:
        raise AppError("PRODUCT_PROFILE_NOT_FOUND", "目标产品资料不存在", status_code=404)
    item.status = "assigned"
    item.product_entity_id = product_entity.id
    item.assigned_by_user_id = scope.user.id
    item.assigned_at = datetime.now(UTC)
    item.notes = payload.notes.strip() if payload.notes else None
    session.add(
        DocumentRelation(
            tenant_id=scope.tenant_id,
            document_id=item.document_id,
            entity_id=product_entity.id,
            relation_type="product_material",
        )
    )
    audits.append(
        session,
        request,
        scope,
        action="product_material.assign",
        resource_type="product_material_attribution",
        resource_id=item.id,
        detail={
            "document_id": item.document_id,
            "product_entity_id": product_entity.id,
            "notes": item.notes,
        },
    )
    session.commit()
    document = session.get(SourceDocument, item.document_id)
    assert document is not None
    return _attribution_item(item, document)


def _profile_detail(
    session: TenantDatabaseSession,
    scope: TenantScope,
    entity: Entity,
    *,
    relation_only: bool = False,
) -> ProfileDetail:
    definitions = list(
        session.scalars(
            select(FieldDefinition)
            .where(
                FieldDefinition.entity_type == entity.entity_type,
                FieldDefinition.is_active.is_(True),
            )
            .order_by(FieldDefinition.sort_order, FieldDefinition.id)
        )
    )
    definition_by_id = {item.id: item for item in definitions}
    facts = [
        item
        for item in session.scalars(
            select(FieldValue)
            .where(FieldValue.entity_id == entity.id)
            .order_by(FieldValue.field_definition_id, FieldValue.valid_from.desc())
        )
        if item.field_definition_id in definition_by_id
        and permissions.allows(
            session,
            scope,
            ResourceAction.READ,
            entity_id=entity.id,
            sensitivity=ResourceSensitivity(definition_by_id[item.field_definition_id].sensitivity),
        )
    ]
    if relation_only:
        document_statement = (
            select(SourceDocument)
            .join(DocumentRelation, DocumentRelation.document_id == SourceDocument.id)
            .where(DocumentRelation.entity_id == entity.id)
        )
    else:
        document_statement = select(SourceDocument).where(
            (SourceDocument.entity_id == entity.id)
            | SourceDocument.id.in_(
                select(DocumentRelation.document_id).where(DocumentRelation.entity_id == entity.id)
            )
        )
    documents = [
        item
        for item in session.scalars(document_statement.order_by(SourceDocument.create_time.desc()))
        if permissions.allows(
            session,
            scope,
            ResourceAction.READ,
            entity_id=entity.id,
            sensitivity=ResourceSensitivity(item.sensitivity),
        )
    ]
    return ProfileDetail(
        entity=EntityItem.model_validate(entity, from_attributes=True),
        field_definitions=[
            FieldDefinitionItem.model_validate(item, from_attributes=True) for item in definitions
        ],
        facts=[_fact_item(item) for item in facts],
        documents=[_document_item(item) for item in documents],
    )


def _product_document_count(session: TenantDatabaseSession, entity_id: int) -> int:
    return (
        session.scalar(
            select(func.count(DocumentRelation.id)).where(
                DocumentRelation.entity_id == entity_id,
                DocumentRelation.relation_type == "product_material",
            )
        )
        or 0
    )


def _fact_item(item: FieldValue) -> FieldValueItem:
    return FieldValueItem(
        id=item.id,
        entity_id=item.entity_id,
        field_definition_id=item.field_definition_id,
        value=item.value_json,
        status=item.status,
        valid_from=item.valid_from,
        valid_to=item.valid_to,
        source_type=item.source_type,
        source_document_id=item.source_document_id,
        source_locator=item.source_locator_json,
        confidence=item.confidence,
        entered_by_user_id=item.entered_by_user_id,
        reviewed_by_user_id=item.reviewed_by_user_id,
        create_time=item.create_time,
    )


def _document_item(item: SourceDocument) -> SourceDocumentItem:
    return SourceDocumentItem(
        id=item.id,
        document_key=item.document_key,
        entity_id=item.entity_id,
        document_type=item.document_type,
        original_name=item.original_name,
        mime_type=item.mime_type,
        content_hash=item.content_hash,
        file_size=item.file_size,
        version=item.version,
        source_channel=item.source_channel,
        sensitivity=item.sensitivity,
        create_time=item.create_time,
        download_url=f"/api/v2/documents/{item.id}/download",
    )


def _attribution_item(
    item: ProductMaterialAttribution, document: SourceDocument
) -> ProductMaterialAttributionItem:
    return ProductMaterialAttributionItem(
        id=item.id,
        status=item.status,
        document=_document_item(document),
        product_entity_id=item.product_entity_id,
        assigned_by_user_id=item.assigned_by_user_id,
        assigned_at=item.assigned_at,
        notes=item.notes,
    )


def _require_admin(scope: TenantScope) -> None:
    if scope.role != UserRole.ADMIN:
        raise AppError("FORBIDDEN", "只有租户管理员可以执行该操作", status_code=403)
