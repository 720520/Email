"""统一主体、事实、来源文件和授权 API。"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import TenantDatabaseSession, TenantScope
from app.api.schemas.data_governance import (
    EntityCreate,
    EntityItem,
    FieldDefinitionCreate,
    FieldDefinitionItem,
    FieldValueCreate,
    FieldValueItem,
    ResourceGrantItem,
    ResourceGrantUpsert,
    SourceDocumentItem,
)
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.files import atomic_write_bytes
from app.db.models import (
    AppUser,
    DocumentRelation,
    Entity,
    FieldDefinition,
    FieldValue,
    ResourceGrant,
    SourceDocument,
    TenantMembership,
    UserRole,
)
from app.services.archive_service import sanitize_filename
from app.services.request_audit_service import RequestAuditService
from app.services.resource_permission_service import (
    ResourceAction,
    ResourcePermissionService,
    ResourceSensitivity,
)

router = APIRouter()
permissions = ResourcePermissionService()
audits = RequestAuditService()


@router.get("/entities", response_model=list[EntityItem])
def list_entities(
    session: TenantDatabaseSession,
    scope: TenantScope,
    entity_type: str | None = Query(default=None),
) -> list[EntityItem]:
    permissions.require(session, scope, ResourceAction.READ)
    statement = select(Entity).where(Entity.status == "active")
    if entity_type:
        statement = statement.where(Entity.entity_type == entity_type)
    return [_entity_item(item) for item in session.scalars(statement.order_by(Entity.id))]


@router.post("/entities", response_model=EntityItem, status_code=201)
def create_entity(
    payload: EntityCreate,
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> EntityItem:
    permissions.require(session, scope, ResourceAction.CREATE)
    item = Entity(
        tenant_id=scope.tenant_id,
        entity_type=payload.entity_type,
        display_name=payload.display_name,
        external_code=payload.external_code.strip() if payload.external_code else None,
        status="active",
        created_by_user_id=scope.user.id,
    )
    session.add(item)
    try:
        session.flush()
    except IntegrityError as exc:
        raise AppError("ENTITY_CODE_EXISTS", "主体外部编码已存在", status_code=409) from exc
    audits.append(
        session,
        request,
        scope,
        action="entity.create",
        resource_type="entity",
        resource_id=item.id,
        detail={"entity_type": item.entity_type, "external_code": item.external_code},
    )
    session.commit()
    return _entity_item(item)


@router.get("/entities/{entity_id}", response_model=EntityItem)
def get_entity(entity_id: int, session: TenantDatabaseSession, scope: TenantScope) -> EntityItem:
    item = _entity(session, entity_id)
    permissions.require(session, scope, ResourceAction.READ, entity_id=item.id)
    return _entity_item(item)


@router.get("/field-definitions", response_model=list[FieldDefinitionItem])
def list_field_definitions(
    session: TenantDatabaseSession,
    scope: TenantScope,
    entity_type: str | None = Query(default=None),
) -> list[FieldDefinitionItem]:
    permissions.require(session, scope, ResourceAction.READ)
    statement = select(FieldDefinition).where(FieldDefinition.is_active.is_(True))
    if entity_type:
        statement = statement.where(FieldDefinition.entity_type == entity_type)
    return [
        _definition_item(item)
        for item in session.scalars(
            statement.order_by(FieldDefinition.sort_order, FieldDefinition.id)
        )
    ]


@router.post("/field-definitions", response_model=FieldDefinitionItem, status_code=201)
def create_field_definition(
    payload: FieldDefinitionCreate,
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> FieldDefinitionItem:
    _require_admin(scope)
    item = FieldDefinition(
        tenant_id=scope.tenant_id,
        **payload.model_dump(),
        is_system=False,
        is_active=True,
    )
    session.add(item)
    try:
        session.flush()
    except IntegrityError as exc:
        raise AppError("FIELD_DEFINITION_EXISTS", "字段编码已存在", status_code=409) from exc
    audits.append(
        session,
        request,
        scope,
        action="field_definition.create",
        resource_type="field_definition",
        resource_id=item.id,
        detail={"entity_type": item.entity_type, "field_code": item.field_code},
    )
    session.commit()
    return _definition_item(item)


@router.get("/entities/{entity_id}/facts", response_model=list[FieldValueItem])
def list_field_values(
    entity_id: int, session: TenantDatabaseSession, scope: TenantScope
) -> list[FieldValueItem]:
    entity = _entity(session, entity_id)
    permissions.require(session, scope, ResourceAction.READ, entity_id=entity.id)
    rows = session.execute(
        select(FieldValue, FieldDefinition)
        .join(FieldDefinition, FieldValue.field_definition_id == FieldDefinition.id)
        .where(FieldValue.entity_id == entity.id)
        .order_by(
            FieldValue.field_definition_id,
            FieldValue.valid_from.desc(),
            FieldValue.id.desc(),
        )
    )
    return [
        _value_item(value)
        for value, definition in rows
        if permissions.allows(
            session,
            scope,
            ResourceAction.READ,
            entity_id=entity.id,
            sensitivity=ResourceSensitivity(definition.sensitivity),
        )
    ]


@router.post("/entities/{entity_id}/facts", response_model=FieldValueItem, status_code=201)
def create_field_value(
    entity_id: int,
    payload: FieldValueCreate,
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> FieldValueItem:
    entity = _entity(session, entity_id)
    definition = session.get(FieldDefinition, payload.field_definition_id)
    if (
        definition is None
        or not definition.is_active
        or definition.entity_type != entity.entity_type
    ):
        raise AppError("FIELD_DEFINITION_NOT_FOUND", "主体类型没有该字段定义", status_code=404)
    sensitivity = ResourceSensitivity(definition.sensitivity)
    permissions.require(
        session,
        scope,
        ResourceAction.UPDATE,
        entity_id=entity.id,
        sensitivity=sensitivity,
    )
    if payload.valid_to is not None and payload.valid_to <= payload.valid_from:
        raise AppError("FIELD_VALIDITY_INVALID", "失效时间必须晚于生效时间", status_code=422)
    source_document = None
    if payload.source_document_id is not None:
        source_document = session.get(SourceDocument, payload.source_document_id)
        if source_document is None:
            raise AppError("SOURCE_DOCUMENT_NOT_FOUND", "来源文件不存在", status_code=404)
    item = FieldValue(
        tenant_id=scope.tenant_id,
        entity_id=entity.id,
        field_definition_id=definition.id,
        value_json=payload.value,
        status=payload.status,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        source_type=payload.source_type,
        source_document_id=source_document.id if source_document else None,
        source_locator_json=payload.source_locator,
        confidence=payload.confidence,
        entered_by_user_id=scope.user.id,
        reviewed_by_user_id=scope.user.id if payload.status == "confirmed" else None,
    )
    session.add(item)
    session.flush()
    audits.append(
        session,
        request,
        scope,
        action="field_value.append",
        resource_type="field_value",
        resource_id=item.id,
        detail={
            "entity_id": entity.id,
            "field_definition_id": definition.id,
            "status": item.status,
            "source_document_id": item.source_document_id,
        },
    )
    session.commit()
    return _value_item(item)


@router.get("/documents", response_model=list[SourceDocumentItem])
def list_documents(
    session: TenantDatabaseSession,
    scope: TenantScope,
    entity_id: int | None = Query(default=None),
) -> list[SourceDocumentItem]:
    permissions.require(session, scope, ResourceAction.READ, entity_id=entity_id)
    statement = select(SourceDocument)
    if entity_id is not None:
        _entity(session, entity_id)
        statement = statement.where(SourceDocument.entity_id == entity_id)
    items = list(session.scalars(statement.order_by(SourceDocument.create_time.desc())))
    return [
        _document_item(item)
        for item in items
        if permissions.allows(
            session,
            scope,
            ResourceAction.READ,
            entity_id=item.entity_id,
            sensitivity=ResourceSensitivity(item.sensitivity),
        )
    ]


@router.post("/documents", response_model=SourceDocumentItem, status_code=201)
async def upload_document(
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
    file: Annotated[UploadFile, File(description="不可变来源文件")],
    document_type: Annotated[str, Form(min_length=1, max_length=100)],
    source_channel: Annotated[
        str,
        Form(pattern="^(manual_upload|email_attachment|batch_import|api_sync|system_generated)$"),
    ] = "manual_upload",
    sensitivity: Annotated[str, Form(pattern="^(normal|sensitive|highly_sensitive)$")] = "normal",
    entity_id: Annotated[int | None, Form()] = None,
    document_key: Annotated[str | None, Form(max_length=64)] = None,
    relation_type: Annotated[str, Form(max_length=64)] = "evidence_for",
    effective_date: Annotated[date | None, Form()] = None,
    expiry_date: Annotated[date | None, Form()] = None,
) -> SourceDocumentItem:
    entity = _entity(session, entity_id) if entity_id is not None else None
    sensitivity_value = ResourceSensitivity(sensitivity)
    permissions.require(
        session,
        scope,
        ResourceAction.CREATE,
        entity_id=entity.id if entity else None,
        sensitivity=sensitivity_value,
    )
    if expiry_date and effective_date and expiry_date < effective_date:
        raise AppError("DOCUMENT_DATE_INVALID", "文件失效日期不能早于生效日期", status_code=422)
    content = await file.read(get_settings().storage.max_filing_file_bytes + 1)
    if not content:
        raise AppError("SOURCE_DOCUMENT_EMPTY", "来源文件不能为空", status_code=422)
    if len(content) > get_settings().storage.max_filing_file_bytes:
        raise AppError("SOURCE_DOCUMENT_TOO_LARGE", "来源文件超过允许大小", status_code=413)
    key = document_key or uuid.uuid4().hex
    if not key.replace("-", "").replace("_", "").isalnum():
        raise AppError("DOCUMENT_KEY_INVALID", "文件版本键格式无效", status_code=422)
    previous = session.scalar(
        select(SourceDocument)
        .where(SourceDocument.document_key == key)
        .order_by(SourceDocument.version.desc())
        .limit(1)
    )
    if previous is not None and (
        previous.entity_id != (entity.id if entity else None)
        or previous.document_type != document_type.strip()
        or previous.sensitivity != sensitivity
    ):
        raise AppError(
            "DOCUMENT_VERSION_IDENTITY_MISMATCH",
            "同一文件版本键不能变更所属主体、文件类型或敏感等级",
            status_code=409,
        )
    version = (previous.version if previous else 0) + 1
    filename = Path(file.filename or "source-document").name
    safe_name = sanitize_filename(filename)
    relative_path = (
        Path("tenants")
        / str(scope.tenant_id)
        / "sources"
        / key
        / f"v{version}_{uuid.uuid4().hex}_{safe_name}"
    )
    absolute_path = get_settings().data_directory / relative_path
    atomic_write_bytes(absolute_path, content)
    item = SourceDocument(
        tenant_id=scope.tenant_id,
        document_key=key,
        entity_id=entity.id if entity else None,
        document_type=document_type.strip(),
        original_name=filename,
        mime_type=(file.content_type or "application/octet-stream")[:200],
        content_hash=hashlib.sha256(content).hexdigest(),
        storage_path=relative_path.as_posix(),
        file_size=len(content),
        version=version,
        effective_date=effective_date,
        expiry_date=expiry_date,
        source_channel=source_channel,
        sensitivity=sensitivity,
        uploaded_by_user_id=scope.user.id,
    )
    session.add(item)
    try:
        session.flush()
        if entity:
            session.add(
                DocumentRelation(
                    tenant_id=scope.tenant_id,
                    document_id=item.id,
                    entity_id=entity.id,
                    relation_type=relation_type,
                )
            )
        audits.append(
            session,
            request,
            scope,
            action="source_document.version.upload",
            resource_type="source_document",
            resource_id=item.id,
            detail={
                "document_key": key,
                "version": version,
                "entity_id": item.entity_id,
                "sha256": item.content_hash,
                "sensitivity": item.sensitivity,
            },
        )
        session.commit()
    except Exception:
        session.rollback()
        absolute_path.unlink(missing_ok=True)
        raise
    return _document_item(item)


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: int,
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> FileResponse:
    item = session.get(SourceDocument, document_id)
    if item is None:
        raise AppError("SOURCE_DOCUMENT_NOT_FOUND", "来源文件不存在", status_code=404)
    sensitivity = ResourceSensitivity(item.sensitivity)
    permissions.require(
        session, scope, ResourceAction.DOWNLOAD, entity_id=item.entity_id, sensitivity=sensitivity
    )
    if sensitivity != ResourceSensitivity.NORMAL:
        permissions.require(
            session,
            scope,
            ResourceAction.SENSITIVE_READ,
            entity_id=item.entity_id,
            sensitivity=sensitivity,
        )
    path = _safe_document_path(item.storage_path)
    if not path.is_file():
        raise AppError("SOURCE_DOCUMENT_MISSING", "来源文件在存储中缺失", status_code=404)
    if hashlib.sha256(path.read_bytes()).hexdigest() != item.content_hash:
        raise AppError("SOURCE_DOCUMENT_INTEGRITY", "来源文件完整性校验失败", status_code=409)
    audits.append(
        session,
        request,
        scope,
        action="source_document.download",
        resource_type="source_document",
        resource_id=item.id,
        detail={"sha256": item.content_hash, "sensitivity": item.sensitivity},
    )
    session.commit()
    return FileResponse(path, filename=item.original_name, media_type=item.mime_type)


@router.post("/permissions/grants", response_model=ResourceGrantItem)
def upsert_resource_grant(
    payload: ResourceGrantUpsert,
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> ResourceGrantItem:
    _require_admin(scope)
    user = session.get(AppUser, payload.user_id)
    membership = session.scalar(
        select(TenantMembership).where(TenantMembership.user_id == payload.user_id)
    )
    if user is None or membership is None or not membership.is_active:
        raise AppError("GRANT_USER_NOT_FOUND", "授权用户不属于当前租户", status_code=404)
    if payload.entity_id is not None:
        _entity(session, payload.entity_id)
    grant = session.scalar(
        select(ResourceGrant).where(
            ResourceGrant.user_id == payload.user_id,
            ResourceGrant.entity_id == payload.entity_id,
        )
    )
    if grant is None:
        grant = ResourceGrant(
            tenant_id=scope.tenant_id,
            user_id=payload.user_id,
            entity_id=payload.entity_id,
            granted_by_user_id=scope.user.id,
        )
        session.add(grant)
    grant.permissions = sorted(set(payload.permissions))
    grant.sensitivity_ceiling = payload.sensitivity_ceiling
    grant.is_active = True
    session.flush()
    audits.append(
        session,
        request,
        scope,
        action="resource_grant.upsert",
        resource_type="resource_grant",
        resource_id=grant.id,
        detail={
            "user_id": grant.user_id,
            "entity_id": grant.entity_id,
            "permissions": grant.permissions,
            "sensitivity_ceiling": grant.sensitivity_ceiling,
        },
    )
    session.commit()
    return _grant_item(grant)


def _require_admin(scope: TenantScope) -> None:
    if scope.role != UserRole.ADMIN:
        raise AppError("FORBIDDEN", "只有租户管理员可以执行该操作", status_code=403)


def _entity(session: TenantDatabaseSession, entity_id: int) -> Entity:
    item = session.get(Entity, entity_id)
    if item is None:
        raise AppError("ENTITY_NOT_FOUND", "主体不存在", status_code=404)
    return item


def _safe_document_path(relative_path: str) -> Path:
    root = get_settings().data_directory.resolve()
    path = (root / relative_path).resolve()
    if root not in path.parents:
        raise AppError("SOURCE_DOCUMENT_PATH_INVALID", "来源文件路径无效", status_code=500)
    return path


def _entity_item(item: Entity) -> EntityItem:
    return EntityItem.model_validate(item, from_attributes=True)


def _definition_item(item: FieldDefinition) -> FieldDefinitionItem:
    return FieldDefinitionItem.model_validate(item, from_attributes=True)


def _value_item(item: FieldValue) -> FieldValueItem:
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


def _grant_item(item: ResourceGrant) -> ResourceGrantItem:
    return ResourceGrantItem(
        id=item.id,
        user_id=item.user_id,
        entity_id=item.entity_id,
        permissions=list(item.permissions or []),
        sensitivity_ceiling=item.sensitivity_ceiling,
        is_active=item.is_active,
    )
