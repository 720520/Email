"""动态报表字段管理、取值和产品自定义值。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.api.deps import TenantContext, TenantDatabaseSession, TenantScope, require_roles
from app.api.schemas.report_field import (
    ReportFieldDefinitionCreate,
    ReportFieldDefinitionItem,
    ReportFieldDefinitionUpdate,
    ReportFieldResolveRequest,
    ReportFieldResolveResponse,
    ReportFieldValueItem,
    ReportFieldValueUpdate,
    ResolvedReportField,
)
from app.core.config import get_settings
from app.core.credential_security import audit_signing_key
from app.core.errors import AppError
from app.db.models import (
    FundProduct,
    ReportFieldDefinition,
    ReportFieldDefinitionVersion,
    ReportFieldValue,
    ReportTemplate,
    ReportTemplateVersion,
    UserRole,
)
from app.services.audit_service import AuditService
from app.services.report_field_service import (
    SYSTEM_FIELD_CATALOG,
    FieldContext,
    ReportFieldResolver,
)

router = APIRouter()
AdminScope = Annotated[TenantContext, Depends(require_roles(UserRole.ADMIN))]
EditorScope = Annotated[TenantContext, Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))]
_resolver = ReportFieldResolver()


@router.get("", response_model=list[ReportFieldDefinitionItem])
def list_fields(
    session: TenantDatabaseSession,
    scope: TenantScope,
    include_inactive: bool = False,
) -> list[ReportFieldDefinitionItem]:
    del scope
    system = [
        _definition_item(
            {
                "field_key": key,
                **value,
                "id": None,
                "is_system": True,
                "is_active": True,
                "version": 1,
            }
        )
        for key, value in SYSTEM_FIELD_CATALOG.items()
    ]
    query = select(ReportFieldDefinition)
    if not include_inactive:
        query = query.where(ReportFieldDefinition.is_active.is_(True))
    custom = [
        _definition_item(_resolver.custom_definition(row))
        for row in session.scalars(query.order_by(ReportFieldDefinition.field_key))
    ]
    return sorted([*system, *custom], key=lambda item: item.field_key)


@router.post("", response_model=ReportFieldDefinitionItem, status_code=201)
def create_field(
    payload: ReportFieldDefinitionCreate,
    request: Request,
    session: TenantDatabaseSession,
    scope: AdminScope,
) -> ReportFieldDefinitionItem:
    if payload.field_key in SYSTEM_FIELD_CATALOG or session.scalar(
        select(ReportFieldDefinition.id).where(ReportFieldDefinition.field_key == payload.field_key)
    ):
        raise AppError("REPORT_FIELD_KEY_EXISTS", "当前租户已存在该字段标识", status_code=409)
    _validate_kind(payload.data_type, payload.value_kind)
    if payload.default_value is not None:
        _resolver.coerce(payload.data_type, payload.default_value)
    row = ReportFieldDefinition(
        tenant_id=scope.tenant_id,
        field_key=payload.field_key,
        label=payload.label,
        description=payload.description,
        data_type=payload.data_type,
        value_kind=payload.value_kind,
        source_type="custom",
        source_config={},
        format_config=payload.format_config,
        default_value=payload.default_value,
        is_required=payload.is_required,
        is_sensitive=payload.is_sensitive,
        created_by_user_id=scope.user.id,
    )
    session.add(row)
    session.flush()
    _record_version(session, row, "create", scope.user.id)
    _audit(
        session,
        request,
        scope,
        "report_field.create",
        row.id,
        {"field_key": row.field_key, "data_type": row.data_type},
    )
    session.commit()
    return _definition_item(_resolver.custom_definition(row))


@router.patch("/{field_id}", response_model=ReportFieldDefinitionItem)
def update_field(
    field_id: int,
    payload: ReportFieldDefinitionUpdate,
    request: Request,
    session: TenantDatabaseSession,
    scope: AdminScope,
) -> ReportFieldDefinitionItem:
    row = _custom_field(session, field_id)
    if "data_type" in payload.model_fields_set and payload.data_type != row.data_type:
        has_values = session.scalar(
            select(ReportFieldValue.id)
            .where(ReportFieldValue.field_definition_id == row.id)
            .limit(1)
        )
        if has_values is not None:
            raise AppError(
                "REPORT_FIELD_TYPE_IN_USE",
                "字段已有产品值，不能直接修改数据类型",
                status_code=409,
            )
    before = {name: getattr(row, name) for name in payload.model_fields_set}
    for name in payload.model_fields_set:
        setattr(row, name, getattr(payload, name))
    _validate_kind(row.data_type, row.value_kind)
    if row.default_value is not None:
        _resolver.coerce(row.data_type, row.default_value)
    row.version += 1
    _record_version(session, row, "update", scope.user.id)
    _audit(
        session,
        request,
        scope,
        "report_field.update",
        row.id,
        {
            "field_key": row.field_key,
            "before": before,
            "changed_fields": sorted(payload.model_fields_set),
            "version": row.version,
        },
    )
    session.commit()
    return _definition_item(_resolver.custom_definition(row))


@router.post("/{field_id}/disable", response_model=ReportFieldDefinitionItem)
def disable_field(
    field_id: int,
    request: Request,
    session: TenantDatabaseSession,
    scope: AdminScope,
) -> ReportFieldDefinitionItem:
    row = _custom_field(session, field_id)
    row.is_active = False
    row.version += 1
    _record_version(session, row, "disable", scope.user.id)
    _audit(
        session,
        request,
        scope,
        "report_field.disable",
        row.id,
        {"field_key": row.field_key, "version": row.version},
    )
    session.commit()
    return _definition_item(_resolver.custom_definition(row))


@router.get("/{field_key}/usages")
def field_usages(
    field_key: str, session: TenantDatabaseSession, scope: TenantScope
) -> dict[str, Any]:
    del scope
    definition = _resolver.definition(session, field_key)
    value_count = 0
    if definition["id"] is not None:
        value_count = len(
            list(
                session.scalars(
                    select(ReportFieldValue.id).where(
                        ReportFieldValue.field_definition_id == definition["id"]
                    )
                )
            )
        )
    templates = []
    for version, template in session.execute(
        select(ReportTemplateVersion, ReportTemplate)
        .join(ReportTemplate, ReportTemplate.id == ReportTemplateVersion.template_id)
        .where(ReportTemplateVersion.status.in_(("draft", "validating", "published")))
        .order_by(ReportTemplate.name, ReportTemplateVersion.version.desc())
    ):
        if field_key in (version.required_fields or []):
            templates.append(
                {
                    "template_id": template.id,
                    "template_name": template.name,
                    "version_id": version.id,
                    "version": version.version,
                    "status": version.status,
                }
            )
    return {
        "field_key": field_key,
        "value_count": value_count,
        "template_count": len(templates),
        "templates": templates,
    }


@router.post("/resolve", response_model=ReportFieldResolveResponse)
def resolve_fields(
    payload: ReportFieldResolveRequest,
    session: TenantDatabaseSession,
    scope: EditorScope,
) -> ReportFieldResolveResponse:
    rows = _resolver.resolve_many(
        session,
        payload.field_keys,
        FieldContext(scope.tenant_id, scope.tenant_name, payload.product_id, payload.report_date),
    )
    return ReportFieldResolveResponse(
        fields={
            key: ResolvedReportField(
                field_key=key,
                value=value.value,
                data_type=definition["data_type"],
                source_type=value.source_type,
                source_reference=value.source_reference,
                used_default=value.used_default,
            )
            for key, (definition, value) in rows.items()
        }
    )


@router.get("/products/{product_id}/values", response_model=list[ReportFieldValueItem])
def list_product_values(
    product_id: int, session: TenantDatabaseSession, scope: EditorScope
) -> list[ReportFieldValueItem]:
    del scope
    _product(session, product_id)
    definitions = list(
        session.scalars(
            select(ReportFieldDefinition)
            .where(ReportFieldDefinition.is_active.is_(True))
            .order_by(ReportFieldDefinition.field_key)
        )
    )
    result: list[ReportFieldValueItem] = []
    for definition in definitions:
        row = session.scalar(
            select(ReportFieldValue)
            .where(
                ReportFieldValue.field_definition_id == definition.id,
                ReportFieldValue.entity_type == "fund_product",
                ReportFieldValue.entity_id == product_id,
            )
            .order_by(
                ReportFieldValue.effective_date.desc().nullslast(), ReportFieldValue.id.desc()
            )
        )
        result.append(
            ReportFieldValueItem(
                field_key=definition.field_key,
                label=definition.label,
                data_type=definition.data_type,
                value=(
                    row.value_json
                    if row and row.value_json is not None
                    else row.value_text
                    if row
                    else None
                ),
                effective_date=row.effective_date if row else None,
                source_type=row.source_type if row else None,
                source_reference=row.source_reference if row else None,
                version=row.version if row else 0,
            )
        )
    return result


@router.put("/products/{product_id}/values/{field_key}", response_model=ReportFieldValueItem)
def set_product_value(
    product_id: int,
    field_key: str,
    payload: ReportFieldValueUpdate,
    request: Request,
    session: TenantDatabaseSession,
    scope: EditorScope,
) -> ReportFieldValueItem:
    _product(session, product_id)
    definition = session.scalar(
        select(ReportFieldDefinition).where(
            ReportFieldDefinition.field_key == field_key, ReportFieldDefinition.is_active.is_(True)
        )
    )
    if definition is None:
        raise AppError("REPORT_FIELD_NOT_FOUND", "自定义字段不存在或已停用", status_code=404)
    value = _resolver.coerce(definition.data_type, payload.value)
    row = session.scalar(
        select(ReportFieldValue).where(
            ReportFieldValue.field_definition_id == definition.id,
            ReportFieldValue.entity_type == "fund_product",
            ReportFieldValue.entity_id == product_id,
            ReportFieldValue.effective_date.is_(None)
            if payload.effective_date is None
            else ReportFieldValue.effective_date == payload.effective_date,
        )
    )
    before = None
    if row is None:
        row = ReportFieldValue(
            tenant_id=scope.tenant_id,
            field_definition_id=definition.id,
            entity_type="fund_product",
            entity_id=product_id,
            effective_date=payload.effective_date,
            source_type="manual",
            created_by_user_id=scope.user.id,
        )
        session.add(row)
    else:
        before = row.value_json if row.value_json is not None else row.value_text
        row.version += 1
    if definition.data_type in {"list", "table", "chart", "json"}:
        row.value_json, row.value_text = value, None
    else:
        row.value_text, row.value_json = None if value is None else str(value), None
    row.source_reference = payload.source_reference
    session.flush()
    audit_before = "***" if definition.is_sensitive and before is not None else before
    audit_after = "***" if definition.is_sensitive and value is not None else value
    _audit(
        session,
        request,
        scope,
        "report_field_value.update",
        row.id,
        {
            "field_key": field_key,
            "product_id": product_id,
            "before": audit_before,
            "after": audit_after,
            "effective_date": str(payload.effective_date) if payload.effective_date else None,
        },
    )
    session.commit()
    return ReportFieldValueItem(
        field_key=field_key,
        label=definition.label,
        data_type=definition.data_type,
        value=value,
        effective_date=row.effective_date,
        source_type=row.source_type,
        source_reference=row.source_reference,
        version=row.version,
    )


def _definition_item(data: dict[str, Any]) -> ReportFieldDefinitionItem:
    return ReportFieldDefinitionItem(
        id=data.get("id"),
        field_key=data["field_key"],
        label=data["label"],
        description=data.get("description"),
        data_type=data["data_type"],
        value_kind=data.get("value_kind", "scalar"),
        source_type=data["source_type"],
        format_config=data.get("format_config", {}),
        default_value=data.get("default_value"),
        is_required=data.get("is_required", False),
        is_sensitive=data.get("is_sensitive", False),
        is_active=data.get("is_active", True),
        is_system=data.get("is_system", False),
        version=data.get("version", 1),
        create_time=data.get("create_time"),
        update_time=data.get("update_time"),
    )


def _custom_field(session: TenantDatabaseSession, field_id: int) -> ReportFieldDefinition:
    row = session.get(ReportFieldDefinition, field_id)
    if row is None:
        raise AppError("REPORT_FIELD_NOT_FOUND", "自定义字段不存在", status_code=404)
    return row


def _product(session: TenantDatabaseSession, product_id: int) -> FundProduct:
    product = session.get(FundProduct, product_id)
    if product is None:
        raise AppError("FUND_PRODUCT_NOT_FOUND", "未找到该基金产品", status_code=404)
    return product


def _validate_kind(data_type: str, value_kind: str) -> None:
    expected = {
        "image": "image",
        "list": "list",
        "table": "table",
        "chart": "chart",
        "json": "json",
    }.get(data_type, "scalar")
    if value_kind != expected:
        raise AppError(
            "REPORT_FIELD_KIND_INVALID", f"{data_type} 字段的 value_kind 必须是 {expected}"
        )


def _record_version(
    session,
    row: ReportFieldDefinition,
    action: str,
    user_id: int | None,
) -> None:
    session.add(
        ReportFieldDefinitionVersion(
            tenant_id=row.tenant_id,
            field_definition_id=row.id,
            version=row.version,
            action=action,
            snapshot={
                "field_key": row.field_key,
                "label": row.label,
                "description": row.description,
                "data_type": row.data_type,
                "value_kind": row.value_kind,
                "source_type": row.source_type,
                "source_config": row.source_config or {},
                "format_config": row.format_config or {},
                "default_value": (
                    "***" if row.is_sensitive and row.default_value else row.default_value
                ),
                "is_required": row.is_required,
                "is_sensitive": row.is_sensitive,
                "is_active": row.is_active,
            },
            created_by_user_id=user_id,
        )
    )


def _audit(
    session,
    request: Request,
    scope: TenantContext,
    action: str,
    resource_id: int,
    detail: dict[str, Any],
) -> None:
    AuditService(audit_signing_key(get_settings().security)).append(
        session,
        tenant_id=scope.tenant_id,
        actor_user_id=scope.user.id,
        actor_username=scope.user.username,
        action=action,
        resource_type="report_field",
        resource_id=resource_id,
        outcome="success",
        detail=detail,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
