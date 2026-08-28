"""阶段 3 机构模板、开户清单、补件和状态流转。"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import TenantDatabaseSession, TenantScope
from app.api.schemas.account_opening import (
    AccountApplicationCreate,
    AccountApplicationDetail,
    AccountApplicationSummary,
    AccountApplicationUpdate,
    ApplicationEventOut,
    ApplicationRequirementOut,
    ApplicationReview,
    ApplicationSupplementCreate,
    ApplicationSupplementOut,
    InstitutionCreate,
    InstitutionItem,
    InstitutionUpdate,
    RequirementDocumentAttach,
    RequirementTemplateCreate,
    RequirementTemplateItemOut,
    RequirementTemplateOut,
    RequirementTemplateStateUpdate,
)
from app.api.schemas.data_governance import SourceDocumentItem
from app.core.errors import AppError
from app.db.models import (
    AccountApplication,
    ApplicationEvent,
    ApplicationRequirement,
    ApplicationSupplement,
    CounterpartyInstitution,
    DocumentRelation,
    Entity,
    FundProduct,
    OrganizationProfile,
    RequirementTemplate,
    RequirementTemplateItem,
    SourceDocument,
    TenantMembership,
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

EDITABLE_APPLICATION_STATUSES = {"draft", "preparing", "pending_seal"}


@router.get("/institutions", response_model=list[InstitutionItem])
def list_institutions(
    session: TenantDatabaseSession,
    scope: TenantScope,
    include_inactive: bool = Query(default=False),
) -> list[InstitutionItem]:
    permissions.require(session, scope, ResourceAction.READ)
    statement = select(CounterpartyInstitution).order_by(CounterpartyInstitution.full_name)
    if not include_inactive:
        statement = statement.where(CounterpartyInstitution.is_active.is_(True))
    return [_institution_item(item) for item in session.scalars(statement)]


@router.post("/institutions", response_model=InstitutionItem, status_code=201)
def create_institution(
    payload: InstitutionCreate,
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> InstitutionItem:
    _require_admin(scope)
    entity = Entity(
        tenant_id=scope.tenant_id,
        entity_type="institution",
        display_name=payload.full_name,
        external_code=None,
        status="active",
        created_by_user_id=scope.user.id,
    )
    session.add(entity)
    session.flush()
    item = CounterpartyInstitution(
        tenant_id=scope.tenant_id,
        entity_id=entity.id,
        **payload.model_dump(),
        is_active=True,
    )
    session.add(item)
    try:
        session.flush()
    except IntegrityError as exc:
        raise AppError("INSTITUTION_EXISTS", "同名开户机构已存在", status_code=409) from exc
    audits.append(
        session,
        request,
        scope,
        action="institution.create",
        resource_type="counterparty_institution",
        resource_id=item.id,
        detail={"entity_id": entity.id, "institution_type": item.institution_type},
    )
    session.commit()
    return _institution_item(item)


@router.patch("/institutions/{institution_id}", response_model=InstitutionItem)
def update_institution(
    institution_id: int,
    payload: InstitutionUpdate,
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> InstitutionItem:
    _require_admin(scope)
    item = _institution(session, institution_id)
    changes = payload.model_dump(exclude_unset=True)
    if "full_name" in changes:
        changes["full_name"] = changes["full_name"].strip()
    for key, value in changes.items():
        setattr(item, key, value)
    entity = session.get(Entity, item.entity_id)
    if entity is not None:
        entity.display_name = item.full_name
        entity.status = "active" if item.is_active else "inactive"
    try:
        session.flush()
    except IntegrityError as exc:
        raise AppError("INSTITUTION_EXISTS", "同名开户机构已存在", status_code=409) from exc
    audits.append(
        session,
        request,
        scope,
        action="institution.update",
        resource_type="counterparty_institution",
        resource_id=item.id,
        detail={"changed_fields": sorted(changes)},
    )
    session.commit()
    return _institution_item(item)


@router.get("/requirement-templates", response_model=list[RequirementTemplateOut])
def list_requirement_templates(
    session: TenantDatabaseSession,
    scope: TenantScope,
    institution_id: int | None = Query(default=None),
    account_type: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
) -> list[RequirementTemplateOut]:
    permissions.require(session, scope, ResourceAction.READ)
    statement = select(RequirementTemplate).order_by(
        RequirementTemplate.account_type,
        RequirementTemplate.name,
        RequirementTemplate.version.desc(),
    )
    if institution_id is not None:
        _institution(session, institution_id)
        statement = statement.where(RequirementTemplate.institution_id == institution_id)
    if account_type:
        statement = statement.where(RequirementTemplate.account_type == account_type)
    if not include_inactive:
        statement = statement.where(RequirementTemplate.is_active.is_(True))
    return [_template_out(session, item) for item in session.scalars(statement)]


@router.post("/requirement-templates", response_model=RequirementTemplateOut, status_code=201)
def create_requirement_template(
    payload: RequirementTemplateCreate,
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> RequirementTemplateOut:
    _require_admin(scope)
    if payload.institution_id is not None:
        _institution(session, payload.institution_id)
    duplicate = session.scalar(
        select(RequirementTemplate.id).where(
            RequirementTemplate.institution_id == payload.institution_id,
            RequirementTemplate.account_type == payload.account_type,
            RequirementTemplate.fund_type == payload.fund_type,
            RequirementTemplate.name == payload.name,
            RequirementTemplate.version == payload.version,
        )
    )
    if duplicate is not None:
        raise AppError("REQUIREMENT_TEMPLATE_EXISTS", "该模板版本已存在", status_code=409)
    item = RequirementTemplate(
        tenant_id=scope.tenant_id,
        **payload.model_dump(exclude={"items"}),
        is_active=True,
    )
    session.add(item)
    session.flush()
    for template_item in payload.items:
        session.add(
            RequirementTemplateItem(
                tenant_id=scope.tenant_id,
                template_id=item.id,
                requirement_code=template_item.requirement_code,
                name=template_item.name.strip(),
                source_scope=template_item.source_scope,
                required=template_item.required,
                condition_json=template_item.condition,
                seal_requirement=(
                    template_item.seal_requirement.strip()
                    if template_item.seal_requirement
                    else None
                ),
                original_required=template_item.original_required,
                sort_order=template_item.sort_order,
            )
        )
    audits.append(
        session,
        request,
        scope,
        action="requirement_template.create",
        resource_type="requirement_template",
        resource_id=item.id,
        detail={
            "scope": item.template_scope,
            "institution_id": item.institution_id,
            "account_type": item.account_type,
            "version": item.version,
            "item_count": len(payload.items),
        },
    )
    session.commit()
    return _template_out(session, item)


@router.patch("/requirement-templates/{template_id}/state", response_model=RequirementTemplateOut)
def update_requirement_template_state(
    template_id: int,
    payload: RequirementTemplateStateUpdate,
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> RequirementTemplateOut:
    _require_admin(scope)
    item = _template(session, template_id)
    if payload.effective_to and payload.effective_to < item.effective_from:
        raise AppError("TEMPLATE_DATE_INVALID", "失效日期不能早于生效日期", status_code=422)
    item.is_active = payload.is_active
    item.effective_to = payload.effective_to
    audits.append(
        session,
        request,
        scope,
        action="requirement_template.state.update",
        resource_type="requirement_template",
        resource_id=item.id,
        detail={"is_active": item.is_active, "effective_to": str(item.effective_to)},
    )
    session.commit()
    return _template_out(session, item)


@router.get("/account-applications", response_model=list[AccountApplicationSummary])
def list_account_applications(
    session: TenantDatabaseSession,
    scope: TenantScope,
    status: str | None = Query(default=None),
    product_id: int | None = Query(default=None),
) -> list[AccountApplicationSummary]:
    permissions.require(session, scope, ResourceAction.READ)
    statement = select(AccountApplication).order_by(
        AccountApplication.application_date.desc(), AccountApplication.id.desc()
    )
    if status:
        statement = statement.where(AccountApplication.status == status)
    if product_id is not None:
        _product(session, product_id)
        statement = statement.where(AccountApplication.product_id == product_id)
    return [_application_summary(session, item) for item in session.scalars(statement)]


@router.post("/account-applications", response_model=AccountApplicationDetail, status_code=201)
def create_account_application(
    payload: AccountApplicationCreate,
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> AccountApplicationDetail:
    permissions.require(session, scope, ResourceAction.CREATE)
    product = _product(session, payload.product_id)
    institution = _institution(session, payload.institution_id)
    if not institution.is_active:
        raise AppError("INSTITUTION_INACTIVE", "开户机构已停用", status_code=409)
    owner_user_id = payload.owner_user_id or scope.user.id
    if owner_user_id != scope.user.id and scope.role != UserRole.ADMIN:
        raise AppError("OWNER_ASSIGN_FORBIDDEN", "只有管理员可以指定其他负责人", status_code=403)
    _membership(session, owner_user_id)
    template_items = _matching_template_items(
        session,
        institution_id=institution.id,
        account_type=payload.account_type,
        fund_type=payload.fund_type,
        effective_date=payload.application_date,
    )
    if not template_items:
        raise AppError(
            "REQUIREMENT_TEMPLATE_NOT_FOUND",
            "当前机构、账户类型和基金类型没有生效的材料模板",
            status_code=409,
        )
    item = AccountApplication(
        tenant_id=scope.tenant_id,
        product_id=product.id,
        institution_id=institution.id,
        account_type=payload.account_type.strip(),
        settlement_mode=payload.settlement_mode.strip(),
        fund_type=payload.fund_type.strip(),
        status="draft",
        application_date=payload.application_date,
        owner_user_id=owner_user_id,
    )
    session.add(item)
    session.flush()
    for sort_order, template_item in enumerate(template_items.values(), start=1):
        session.add(
            ApplicationRequirement(
                tenant_id=scope.tenant_id,
                application_id=item.id,
                source_template_id=template_item.template_id,
                requirement_code=template_item.requirement_code,
                name=template_item.name,
                source_scope=template_item.source_scope,
                required=template_item.required,
                condition_json=template_item.condition_json,
                seal_requirement=template_item.seal_requirement,
                original_required=template_item.original_required,
                status="missing",
                sort_order=sort_order,
            )
        )
    _event(session, scope, item, "created", None, "draft")
    audits.append(
        session,
        request,
        scope,
        action="account_application.create",
        resource_type="account_application",
        resource_id=item.id,
        detail={
            "product_id": product.id,
            "institution_id": institution.id,
            "account_type": item.account_type,
            "requirement_count": len(template_items),
        },
    )
    session.commit()
    return _application_detail(session, item)


@router.get("/account-applications/{application_id}", response_model=AccountApplicationDetail)
def get_account_application(
    application_id: int, session: TenantDatabaseSession, scope: TenantScope
) -> AccountApplicationDetail:
    item = _application(session, application_id)
    product = _product(session, item.product_id)
    permissions.require(session, scope, ResourceAction.READ, entity_id=product.entity_id)
    return _application_detail(session, item)


@router.patch("/account-applications/{application_id}", response_model=AccountApplicationDetail)
def update_account_application(
    application_id: int,
    payload: AccountApplicationUpdate,
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> AccountApplicationDetail:
    item = _application(session, application_id)
    _require_application_editor(session, scope, item)
    if item.status not in EDITABLE_APPLICATION_STATUSES:
        raise AppError("APPLICATION_LOCKED", "申请提交后基础信息不可修改", status_code=409)
    changes = payload.model_dump(exclude_unset=True)
    new_status = changes.pop("status", None)
    if "owner_user_id" in changes:
        if scope.role != UserRole.ADMIN:
            raise AppError("OWNER_ASSIGN_FORBIDDEN", "只有管理员可以更换负责人", status_code=403)
        _membership(session, changes["owner_user_id"])
    for key, value in changes.items():
        setattr(item, key, value)
    if new_status and new_status != item.status:
        allowed = {
            "draft": {"preparing"},
            "preparing": {"draft", "pending_seal"},
            "pending_seal": {"preparing"},
        }
        if new_status not in allowed.get(item.status, set()):
            raise AppError(
                "APPLICATION_TRANSITION_INVALID", "当前状态不能执行该流转", status_code=409
            )
        _transition(session, scope, item, new_status, "status_changed")
    audits.append(
        session,
        request,
        scope,
        action="account_application.update",
        resource_type="account_application",
        resource_id=item.id,
        detail={"changed_fields": sorted(payload.model_fields_set)},
    )
    session.commit()
    return _application_detail(session, item)


@router.put(
    "/account-applications/{application_id}/requirements/{requirement_id}",
    response_model=AccountApplicationDetail,
)
def attach_requirement_document(
    application_id: int,
    requirement_id: int,
    payload: RequirementDocumentAttach,
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> AccountApplicationDetail:
    item = _application(session, application_id)
    _require_application_editor(session, scope, item)
    if item.status not in EDITABLE_APPLICATION_STATUSES:
        raise AppError("APPLICATION_MATERIAL_FROZEN", "申请提交后材料版本不可替换", status_code=409)
    requirement = _requirement(session, item.id, requirement_id)
    document = _document_for_requirement(session, scope, item, requirement, payload.document_id)
    requirement.document_id = document.id
    requirement.status = "provided"
    requirement.review_comment = None
    _event(
        session,
        scope,
        item,
        "material_attached",
        item.status,
        item.status,
        detail={"requirement_id": requirement.id, "document_id": document.id},
    )
    audits.append(
        session,
        request,
        scope,
        action="account_application.material.attach",
        resource_type="account_application",
        resource_id=item.id,
        detail={"requirement_id": requirement.id, "document_id": document.id},
    )
    session.commit()
    return _application_detail(session, item)


@router.post(
    "/account-applications/{application_id}/submit", response_model=AccountApplicationDetail
)
def submit_account_application(
    application_id: int,
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> AccountApplicationDetail:
    item = _application(session, application_id)
    _require_application_editor(session, scope, item)
    if item.status not in EDITABLE_APPLICATION_STATUSES | {"supplement_required"}:
        raise AppError("APPLICATION_TRANSITION_INVALID", "当前状态不能提交", status_code=409)
    requirements = _requirements(session, item.id)
    missing = [
        requirement.name
        for requirement in requirements
        if requirement.required
        and (
            requirement.document_id is None
            or requirement.status not in {"provided", "submitted", "accepted"}
        )
    ]
    if missing:
        raise AppError(
            "APPLICATION_MATERIAL_INCOMPLETE",
            "必需材料尚未齐备",
            status_code=409,
            details={"missing": missing},
        )
    for requirement in requirements:
        if requirement.status == "provided":
            requirement.status = "submitted"
    if item.submitted_at is None:
        item.submitted_at = datetime.now(UTC)
    _transition(session, scope, item, "submitted", "submitted")
    audits.append(
        session,
        request,
        scope,
        action="account_application.submit",
        resource_type="account_application",
        resource_id=item.id,
        detail={"fixed_document_ids": [req.document_id for req in requirements if req.document_id]},
    )
    session.commit()
    return _application_detail(session, item)


@router.post(
    "/account-applications/{application_id}/supplements",
    response_model=AccountApplicationDetail,
    status_code=201,
)
def add_application_supplement(
    application_id: int,
    payload: ApplicationSupplementCreate,
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> AccountApplicationDetail:
    item = _application(session, application_id)
    _require_application_editor(session, scope, item)
    if item.status != "supplement_required":
        raise AppError("SUPPLEMENT_NOT_REQUESTED", "当前申请不在补件状态", status_code=409)
    requirement = _requirement(session, item.id, payload.requirement_id)
    if requirement.status != "supplement_required":
        raise AppError(
            "REQUIREMENT_SUPPLEMENT_NOT_REQUESTED", "该材料未被要求补件", status_code=409
        )
    document = _document_for_requirement(session, scope, item, requirement, payload.document_id)
    supplement = ApplicationSupplement(
        tenant_id=scope.tenant_id,
        application_id=item.id,
        requirement_id=requirement.id,
        document_id=document.id,
        comment=payload.comment.strip() if payload.comment else None,
        submitted_by_user_id=scope.user.id,
    )
    session.add(supplement)
    requirement.status = "provided"
    _event(
        session,
        scope,
        item,
        "supplement_added",
        item.status,
        item.status,
        comment=supplement.comment,
        detail={"requirement_id": requirement.id, "document_id": document.id},
    )
    audits.append(
        session,
        request,
        scope,
        action="account_application.supplement.add",
        resource_type="account_application",
        resource_id=item.id,
        detail={"requirement_id": requirement.id, "document_id": document.id},
    )
    session.commit()
    return _application_detail(session, item)


@router.post(
    "/account-applications/{application_id}/review", response_model=AccountApplicationDetail
)
def review_account_application(
    application_id: int,
    payload: ApplicationReview,
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> AccountApplicationDetail:
    _require_admin(scope)
    item = _application(session, application_id)
    requirements = _requirements(session, item.id)
    from_status = item.status
    if payload.action == "request_supplement":
        if item.status != "submitted" or not payload.requirement_ids:
            raise AppError(
                "APPLICATION_REVIEW_INVALID", "请选择需要补充的已提交材料", status_code=409
            )
        selected = {req.id: req for req in requirements if req.id in set(payload.requirement_ids)}
        if len(selected) != len(set(payload.requirement_ids)):
            raise AppError("APPLICATION_REQUIREMENT_NOT_FOUND", "补件材料不存在", status_code=404)
        for requirement in selected.values():
            requirement.status = "supplement_required"
            requirement.review_comment = payload.comment.strip() if payload.comment else None
        _transition(
            session,
            scope,
            item,
            "supplement_required",
            "supplement_requested",
            comment=payload.comment,
            detail={"requirement_ids": sorted(selected)},
        )
    elif payload.action == "approve":
        if item.status != "submitted":
            raise AppError("APPLICATION_REVIEW_INVALID", "只有已提交申请可以审批", status_code=409)
        if item.owner_user_id == scope.user.id:
            raise AppError(
                "APPLICATION_SELF_APPROVAL", "申请负责人不能审批自己的申请", status_code=409
            )
        if any(
            req.required and req.status not in {"submitted", "accepted"} for req in requirements
        ):
            raise AppError("APPLICATION_MATERIAL_INCOMPLETE", "材料复核尚未完成", status_code=409)
        for requirement in requirements:
            if requirement.status == "submitted":
                requirement.status = "accepted"
                requirement.review_comment = payload.comment.strip() if payload.comment else None
        item.reviewer_user_id = scope.user.id
        _transition(session, scope, item, "approved", "approved", comment=payload.comment)
    elif payload.action == "reject":
        if item.status != "submitted":
            raise AppError("APPLICATION_REVIEW_INVALID", "只有已提交申请可以拒绝", status_code=409)
        item.reviewer_user_id = scope.user.id
        _transition(session, scope, item, "rejected", "rejected", comment=payload.comment)
    elif payload.action == "open":
        if item.status != "approved":
            raise AppError(
                "APPLICATION_REVIEW_INVALID", "只有已批准申请可以确认开户", status_code=409
            )
        item.completed_date = date.today()
        _transition(session, scope, item, "opened", "opened", comment=payload.comment)
    else:
        if item.status != "opened":
            raise AppError("APPLICATION_REVIEW_INVALID", "只有已开户账户可以销户", status_code=409)
        item.closed_date = date.today()
        _transition(session, scope, item, "closed", "closed", comment=payload.comment)
    audits.append(
        session,
        request,
        scope,
        action=f"account_application.{payload.action}",
        resource_type="account_application",
        resource_id=item.id,
        detail={"from_status": from_status, "to_status": item.status},
    )
    session.commit()
    return _application_detail(session, item)


@router.get(
    "/account-applications/{application_id}/available-documents",
    response_model=list[SourceDocumentItem],
)
def list_available_documents(
    application_id: int,
    session: TenantDatabaseSession,
    scope: TenantScope,
    source_scope: str = Query(pattern="^(organization|product|account_application)$"),
) -> list[SourceDocumentItem]:
    item = _application(session, application_id)
    product = _product(session, item.product_id)
    entity_id: int | None
    if source_scope == "organization":
        profile = session.scalar(select(OrganizationProfile).limit(1))
        entity_id = profile.entity_id if profile else None
    elif source_scope == "product":
        entity_id = product.entity_id
    else:
        entity_id = None
    statement = select(SourceDocument)
    if entity_id is None:
        statement = statement.where(SourceDocument.entity_id.is_(None))
    else:
        statement = statement.where(
            (SourceDocument.entity_id == entity_id)
            | SourceDocument.id.in_(
                select(DocumentRelation.document_id).where(DocumentRelation.entity_id == entity_id)
            )
        )
    documents = [
        document
        for document in session.scalars(statement.order_by(SourceDocument.create_time.desc()))
        if permissions.allows(
            session,
            scope,
            ResourceAction.READ,
            entity_id=entity_id,
            sensitivity=ResourceSensitivity(document.sensitivity),
        )
    ]
    return [_source_document_item(document) for document in documents]


def _matching_template_items(
    session: TenantDatabaseSession,
    *,
    institution_id: int,
    account_type: str,
    fund_type: str,
    effective_date: date,
) -> dict[str, RequirementTemplateItem]:
    matching_templates = list(
        session.scalars(
            select(RequirementTemplate)
            .where(
                RequirementTemplate.is_active.is_(True),
                RequirementTemplate.account_type == account_type,
                RequirementTemplate.fund_type.in_(["all", fund_type]),
                RequirementTemplate.effective_from <= effective_date,
                or_(
                    RequirementTemplate.effective_to.is_(None),
                    RequirementTemplate.effective_to >= effective_date,
                ),
                or_(
                    RequirementTemplate.institution_id.is_(None),
                    RequirementTemplate.institution_id == institution_id,
                ),
            )
            .order_by(RequirementTemplate.id)
        )
    )
    latest_templates: dict[tuple, RequirementTemplate] = {}
    for template in matching_templates:
        identity = (
            template.template_scope,
            template.institution_id,
            template.account_type,
            template.fund_type,
            template.name,
        )
        current = latest_templates.get(identity)
        if current is None or (template.version, template.id) > (current.version, current.id):
            latest_templates[identity] = template
    templates = sorted(
        latest_templates.values(),
        key=lambda template: (
            template.institution_id is not None,
            template.fund_type != "all",
            template.id,
        ),
    )
    merged: dict[str, RequirementTemplateItem] = {}
    for template in templates:
        for item in session.scalars(
            select(RequirementTemplateItem)
            .where(RequirementTemplateItem.template_id == template.id)
            .order_by(RequirementTemplateItem.sort_order, RequirementTemplateItem.id)
        ):
            merged[item.requirement_code] = item
    return merged


def _document_for_requirement(
    session: TenantDatabaseSession,
    scope: TenantScope,
    application: AccountApplication,
    requirement: ApplicationRequirement,
    document_id: int,
) -> SourceDocument:
    document = session.get(SourceDocument, document_id)
    if document is None:
        raise AppError("SOURCE_DOCUMENT_NOT_FOUND", "来源文件不存在", status_code=404)
    product = _product(session, application.product_id)
    if requirement.source_scope == "organization":
        profile = session.scalar(select(OrganizationProfile).limit(1))
        expected_entity_id = profile.entity_id if profile else None
    elif requirement.source_scope == "product":
        expected_entity_id = product.entity_id
    else:
        expected_entity_id = None
    if expected_entity_id is None:
        allowed = requirement.source_scope == "account_application" and document.entity_id is None
    else:
        allowed = (
            document.entity_id == expected_entity_id
            or session.scalar(
                select(DocumentRelation.id).where(
                    DocumentRelation.document_id == document.id,
                    DocumentRelation.entity_id == expected_entity_id,
                )
            )
            is not None
        )
    if not allowed:
        raise AppError(
            "APPLICATION_DOCUMENT_SCOPE_INVALID", "文件不属于材料要求的主体", status_code=409
        )
    permissions.require(
        session,
        scope,
        ResourceAction.READ,
        entity_id=expected_entity_id,
        sensitivity=ResourceSensitivity(document.sensitivity),
    )
    return document


def _application_summary(
    session: TenantDatabaseSession, item: AccountApplication
) -> AccountApplicationSummary:
    product = _product(session, item.product_id)
    institution = _institution(session, item.institution_id)
    requirements = _requirements(session, item.id)
    return AccountApplicationSummary(
        id=item.id,
        product_id=product.id,
        product_name=product.product_name,
        product_code=product.product_code,
        institution_id=institution.id,
        institution_name=institution.full_name,
        institution_type=institution.institution_type,
        account_type=item.account_type,
        settlement_mode=item.settlement_mode,
        fund_type=item.fund_type,
        status=item.status,
        application_date=item.application_date,
        completed_date=item.completed_date,
        closed_date=item.closed_date,
        owner_user_id=item.owner_user_id,
        reviewer_user_id=item.reviewer_user_id,
        submitted_at=item.submitted_at,
        requirement_count=len(requirements),
        completed_requirement_count=sum(
            requirement.status in {"provided", "submitted", "accepted"}
            for requirement in requirements
        ),
        create_time=item.create_time,
        update_time=item.update_time,
    )


def _application_detail(
    session: TenantDatabaseSession, item: AccountApplication
) -> AccountApplicationDetail:
    summary = _application_summary(session, item)
    requirements = _requirements(session, item.id)
    documents = {
        document.id: document
        for document in session.scalars(
            select(SourceDocument).where(
                SourceDocument.id.in_(
                    [req.document_id for req in requirements if req.document_id is not None]
                )
            )
        )
    }
    supplements = list(
        session.scalars(
            select(ApplicationSupplement)
            .where(ApplicationSupplement.application_id == item.id)
            .order_by(ApplicationSupplement.create_time, ApplicationSupplement.id)
        )
    )
    supplement_documents = {
        document.id: document
        for document in session.scalars(
            select(SourceDocument).where(
                SourceDocument.id.in_([supplement.document_id for supplement in supplements])
            )
        )
    }
    events = list(
        session.scalars(
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id == item.id)
            .order_by(ApplicationEvent.create_time, ApplicationEvent.id)
        )
    )
    return AccountApplicationDetail(
        **summary.model_dump(),
        requirements=[
            _requirement_out(requirement, documents.get(requirement.document_id))
            for requirement in requirements
        ],
        supplements=[
            _supplement_out(supplement, supplement_documents[supplement.document_id])
            for supplement in supplements
        ],
        events=[
            ApplicationEventOut(
                id=event.id,
                event_type=event.event_type,
                from_status=event.from_status,
                to_status=event.to_status,
                comment=event.comment,
                actor_user_id=event.actor_user_id,
                detail=event.detail_json,
                create_time=event.create_time,
            )
            for event in events
        ],
    )


def _requirement_out(
    item: ApplicationRequirement, document: SourceDocument | None
) -> ApplicationRequirementOut:
    return ApplicationRequirementOut(
        id=item.id,
        requirement_code=item.requirement_code,
        name=item.name,
        source_scope=item.source_scope,
        required=item.required,
        condition=item.condition_json,
        seal_requirement=item.seal_requirement,
        original_required=item.original_required,
        status=item.status,
        document_id=item.document_id,
        document_name=document.original_name if document else None,
        document_version=document.version if document else None,
        document_hash=document.content_hash if document else None,
        review_comment=item.review_comment,
        sort_order=item.sort_order,
    )


def _supplement_out(
    item: ApplicationSupplement, document: SourceDocument
) -> ApplicationSupplementOut:
    return ApplicationSupplementOut(
        id=item.id,
        requirement_id=item.requirement_id,
        document_id=document.id,
        document_name=document.original_name,
        document_version=document.version,
        document_hash=document.content_hash,
        comment=item.comment,
        submitted_by_user_id=item.submitted_by_user_id,
        create_time=item.create_time,
    )


def _template_out(
    session: TenantDatabaseSession, item: RequirementTemplate
) -> RequirementTemplateOut:
    institution = (
        session.get(CounterpartyInstitution, item.institution_id)
        if item.institution_id is not None
        else None
    )
    template_items = list(
        session.scalars(
            select(RequirementTemplateItem)
            .where(RequirementTemplateItem.template_id == item.id)
            .order_by(RequirementTemplateItem.sort_order, RequirementTemplateItem.id)
        )
    )
    return RequirementTemplateOut(
        id=item.id,
        template_scope=item.template_scope,
        institution_id=item.institution_id,
        institution_name=institution.full_name if institution else None,
        account_type=item.account_type,
        fund_type=item.fund_type,
        name=item.name,
        version=item.version,
        effective_from=item.effective_from,
        effective_to=item.effective_to,
        is_active=item.is_active,
        items=[
            RequirementTemplateItemOut(
                id=template_item.id,
                requirement_code=template_item.requirement_code,
                name=template_item.name,
                source_scope=template_item.source_scope,
                required=template_item.required,
                condition=template_item.condition_json,
                seal_requirement=template_item.seal_requirement,
                original_required=template_item.original_required,
                sort_order=template_item.sort_order,
            )
            for template_item in template_items
        ],
        create_time=item.create_time,
        update_time=item.update_time,
    )


def _institution_item(item: CounterpartyInstitution) -> InstitutionItem:
    return InstitutionItem.model_validate(item, from_attributes=True)


def _source_document_item(item: SourceDocument) -> SourceDocumentItem:
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


def _event(
    session: TenantDatabaseSession,
    scope: TenantScope,
    application: AccountApplication,
    event_type: str,
    from_status: str | None,
    to_status: str | None,
    *,
    comment: str | None = None,
    detail: dict | None = None,
) -> None:
    session.add(
        ApplicationEvent(
            tenant_id=scope.tenant_id,
            application_id=application.id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            comment=comment.strip() if comment else None,
            actor_user_id=scope.user.id,
            detail_json=detail or {},
        )
    )


def _transition(
    session: TenantDatabaseSession,
    scope: TenantScope,
    application: AccountApplication,
    status: str,
    event_type: str,
    *,
    comment: str | None = None,
    detail: dict | None = None,
) -> None:
    previous = application.status
    application.status = status
    _event(
        session,
        scope,
        application,
        event_type,
        previous,
        status,
        comment=comment,
        detail=detail,
    )


def _requirements(
    session: TenantDatabaseSession, application_id: int
) -> list[ApplicationRequirement]:
    return list(
        session.scalars(
            select(ApplicationRequirement)
            .where(ApplicationRequirement.application_id == application_id)
            .order_by(ApplicationRequirement.sort_order, ApplicationRequirement.id)
        )
    )


def _institution(session: TenantDatabaseSession, institution_id: int) -> CounterpartyInstitution:
    item = session.get(CounterpartyInstitution, institution_id)
    if item is None:
        raise AppError("INSTITUTION_NOT_FOUND", "开户机构不存在", status_code=404)
    return item


def _template(session: TenantDatabaseSession, template_id: int) -> RequirementTemplate:
    item = session.get(RequirementTemplate, template_id)
    if item is None:
        raise AppError("REQUIREMENT_TEMPLATE_NOT_FOUND", "材料模板不存在", status_code=404)
    return item


def _product(session: TenantDatabaseSession, product_id: int) -> FundProduct:
    item = session.get(FundProduct, product_id)
    if item is None:
        raise AppError("PRODUCT_NOT_FOUND", "基金产品不存在", status_code=404)
    return item


def _application(session: TenantDatabaseSession, application_id: int) -> AccountApplication:
    item = session.get(AccountApplication, application_id)
    if item is None:
        raise AppError("ACCOUNT_APPLICATION_NOT_FOUND", "开户申请不存在", status_code=404)
    return item


def _requirement(
    session: TenantDatabaseSession, application_id: int, requirement_id: int
) -> ApplicationRequirement:
    item = session.scalar(
        select(ApplicationRequirement).where(
            ApplicationRequirement.id == requirement_id,
            ApplicationRequirement.application_id == application_id,
        )
    )
    if item is None:
        raise AppError("APPLICATION_REQUIREMENT_NOT_FOUND", "申请材料不存在", status_code=404)
    return item


def _membership(session: TenantDatabaseSession, user_id: int) -> TenantMembership:
    item = session.scalar(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.is_active.is_(True),
        )
    )
    if item is None:
        raise AppError("TENANT_MEMBER_NOT_FOUND", "负责人不是当前租户有效成员", status_code=404)
    return item


def _require_application_editor(
    session: TenantDatabaseSession, scope: TenantScope, item: AccountApplication
) -> None:
    product = _product(session, item.product_id)
    permissions.require(session, scope, ResourceAction.UPDATE, entity_id=product.entity_id)
    if scope.role != UserRole.ADMIN and item.owner_user_id != scope.user.id:
        raise AppError(
            "APPLICATION_OWNER_REQUIRED", "只有申请负责人或管理员可以修改", status_code=403
        )


def _require_admin(scope: TenantScope) -> None:
    if scope.role != UserRole.ADMIN:
        raise AppError("ADMIN_REQUIRED", "仅租户管理员可以执行该操作", status_code=403)
