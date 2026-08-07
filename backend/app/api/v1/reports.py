"""报表模板、自定义定义、合同要素和 PPTX 生成接口。"""

from __future__ import annotations

import io
import uuid
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from pptx import Presentation
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, TenantDatabaseSession, TenantScope, require_roles
from app.api.schemas.reporting import (
    ContractUploadResponse,
    ReportDefinitionCreate,
    ReportDefinitionItem,
    ReportFieldUpdate,
    ReportGenerateRequest,
    ReportGenerateResponse,
    ReportPreviewRequest,
    ReportPreviewResponse,
    ReportProductFieldsResponse,
    ReportRunItem,
    ReportTemplateItem,
)
from app.core.config import get_settings
from app.core.credential_security import audit_signing_key
from app.core.errors import AppError
from app.core.files import atomic_write_bytes
from app.db.models import (
    FundProduct,
    ProductDocument,
    ReportDefinition,
    ReportRun,
    ReportTemplate,
    UserRole,
)
from app.services.archive_service import sanitize_filename
from app.services.audit_service import AuditService
from app.services.report_presentation_service import ReportPresentationService
from app.services.reporting_service import (
    DEFAULT_REPORT_SECTIONS,
    ReportDataService,
    content_sha256,
    extract_contract_fields,
    extract_contract_text,
)

router = APIRouter()
OperatorScope = Annotated[
    TenantContext,
    Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR)),
]
_data_service = ReportDataService()


@router.get("/templates", response_model=list[ReportTemplateItem])
def list_report_templates(
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> list[ReportTemplateItem]:
    del scope
    uploaded = session.scalars(
        select(ReportTemplate)
        .where(ReportTemplate.is_active.is_(True))
        .order_by(ReportTemplate.name, ReportTemplate.id)
    )
    return [
        ReportTemplateItem(
            key="builtin:weekly",
            name="标准基金周报",
            description="竖版单页周报，包含产品信息、收益指标、净值曲线、策略及合同要素",
            kind="builtin",
        ),
        *[
            ReportTemplateItem(
                key=f"uploaded:{item.id}",
                id=item.id,
                name=item.name,
                description=item.description,
                kind="uploaded",
                original_name=item.original_name,
                is_active=item.is_active,
                create_time=item.create_time,
            )
            for item in uploaded
        ],
    ]


@router.post("/templates", response_model=ReportTemplateItem)
async def upload_report_template(
    request: Request,
    session: TenantDatabaseSession,
    scope: OperatorScope,
    file: Annotated[UploadFile, File(description="带占位符或已知表格结构的 PPTX 模板")],
    name: Annotated[str, Form(min_length=2, max_length=200)],
    description: Annotated[str | None, Form(max_length=1000)] = None,
) -> ReportTemplateItem:
    settings = get_settings()
    filename = file.filename or "report-template.pptx"
    if Path(filename).suffix.casefold() != ".pptx":
        raise AppError("REPORT_TEMPLATE_FORMAT", "报表模板必须是 .pptx 文件")
    content = await file.read(settings.reports.max_template_bytes + 1)
    if len(content) > settings.reports.max_template_bytes:
        raise AppError("REPORT_TEMPLATE_TOO_LARGE", "报表模板超过允许大小")
    try:
        Presentation(io.BytesIO(content))
    except Exception as exc:
        raise AppError("REPORT_TEMPLATE_INVALID", "PPTX 模板无法打开或结构已损坏") from exc
    if session.scalar(select(ReportTemplate.id).where(ReportTemplate.name == name.strip())):
        raise AppError("REPORT_TEMPLATE_NAME_EXISTS", "当前租户已存在同名模板", status_code=409)
    safe_name = sanitize_filename(filename)
    relative_path = Path("tenants") / str(scope.tenant_id) / "reporting" / "templates" / (
        f"{uuid.uuid4().hex}_{safe_name}"
    )
    atomic_write_bytes(settings.data_directory / relative_path, content)
    template = ReportTemplate(
        tenant_id=scope.tenant_id,
        name=name.strip(),
        description=description.strip() if description else None,
        original_name=filename,
        stored_path=relative_path.as_posix(),
        content_hash=content_sha256(content),
        is_active=True,
        created_by_user_id=scope.user.id,
    )
    session.add(template)
    session.flush()
    _audit(
        session, request, scope,
        action="report_template.upload",
        resource_type="report_template",
        resource_id=template.id,
        detail={"name": template.name, "original_name": filename, "sha256": template.content_hash},
    )
    session.commit()
    return ReportTemplateItem(
        key=f"uploaded:{template.id}", id=template.id, name=template.name,
        description=template.description, kind="uploaded", original_name=template.original_name,
        is_active=True, create_time=template.create_time,
    )


@router.get("/product-fields/{product_id}", response_model=ReportProductFieldsResponse)
def get_report_product_fields(
    product_id: int,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> ReportProductFieldsResponse:
    del scope
    product = _data_service.get_product(session, product_id)
    return ReportProductFieldsResponse(
        product_id=product.id,
        product_code=product.product_code,
        product_name=product.product_name,
        fields=_data_service.fields(session, product),
    )


@router.patch(
    "/product-fields/{product_id}/{field_key}", response_model=ReportProductFieldsResponse
)
def update_report_product_field(
    product_id: int,
    field_key: str,
    payload: ReportFieldUpdate,
    request: Request,
    session: TenantDatabaseSession,
    scope: OperatorScope,
) -> ReportProductFieldsResponse:
    product = _data_service.get_product(session, product_id)
    before, after = _data_service.update_field(
        product,
        field_key=field_key,
        value=payload.value,
        restore_source=payload.restore_source,
    )
    _audit(
        session, request, scope,
        action=(
            "report_product_field.restore"
            if payload.restore_source
            else "report_product_field.update"
        ),
        resource_type="fund_product",
        resource_id=product.id,
        detail={
            "field_key": field_key,
            "before": before,
            "after": after,
            "reason": payload.reason,
        },
    )
    session.commit()
    return ReportProductFieldsResponse(
        product_id=product.id,
        product_code=product.product_code,
        product_name=product.product_name,
        fields=_data_service.fields(session, product),
    )


@router.post("/contracts/{product_id}", response_model=ContractUploadResponse)
async def upload_product_contract(
    product_id: int,
    request: Request,
    session: TenantDatabaseSession,
    scope: OperatorScope,
    file: Annotated[UploadFile, File(description="PDF、DOCX 或 TXT 产品合同")],
) -> ContractUploadResponse:
    settings = get_settings()
    product = _data_service.get_product(session, product_id)
    filename = file.filename or "contract.pdf"
    content = await file.read(settings.reports.max_contract_bytes + 1)
    if len(content) > settings.reports.max_contract_bytes:
        raise AppError("CONTRACT_TOO_LARGE", "合同文件超过允许大小")
    digest = content_sha256(content)
    existing = session.scalar(
        select(ProductDocument).where(
            ProductDocument.fund_product_id == product.id,
            ProductDocument.content_hash == digest,
        )
    )
    if existing is not None:
        raise AppError("CONTRACT_ALREADY_ARCHIVED", "该合同已经归档", status_code=409)
    text = extract_contract_text(filename, content)
    fields = extract_contract_fields(text)
    safe_name = sanitize_filename(filename)
    today = date.today()
    relative_path = (
        Path("tenants") / str(scope.tenant_id) / "reporting" / "contracts"
        / product.product_code / f"{today.year:04d}" / f"{today.month:02d}"
        / f"{uuid.uuid4().hex}_{safe_name}"
    )
    atomic_write_bytes(settings.data_directory / relative_path, content)
    document = ProductDocument(
        tenant_id=scope.tenant_id,
        fund_product_id=product.id,
        document_type="contract",
        original_name=filename,
        stored_path=relative_path.as_posix(),
        content_hash=digest,
        extracted_fields=fields,
        created_by_user_id=scope.user.id,
    )
    session.add(document)
    session.flush()
    _data_service.apply_contract_fields(
        product, fields, document_id=document.id, filename=filename
    )
    _audit(
        session, request, scope,
        action="product_contract.upload",
        resource_type="product_document",
        resource_id=document.id,
        detail={
            "product_id": product.id,
            "original_name": filename,
            "sha256": digest,
            "extracted_fields": sorted(fields),
        },
    )
    session.commit()
    return ContractUploadResponse(
        document_id=document.id,
        original_name=filename,
        extracted_fields=fields,
        extracted_count=len(fields),
    )


@router.get("/definitions", response_model=list[ReportDefinitionItem])
def list_report_definitions(
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> list[ReportDefinitionItem]:
    del scope
    return [
        ReportDefinitionItem.model_validate(item, from_attributes=True)
        for item in session.scalars(
            select(ReportDefinition).order_by(ReportDefinition.update_time.desc())
        )
    ]


@router.post("/definitions", response_model=ReportDefinitionItem)
def create_report_definition(
    payload: ReportDefinitionCreate,
    request: Request,
    session: TenantDatabaseSession,
    scope: OperatorScope,
) -> ReportDefinitionItem:
    _data_service.get_product(session, payload.fund_product_id)
    _resolve_template(session, payload.template_key)
    existing_id = session.scalar(
        select(ReportDefinition.id).where(ReportDefinition.name == payload.name.strip())
    )
    if existing_id:
        raise AppError("REPORT_DEFINITION_NAME_EXISTS", "当前租户已存在同名报表", status_code=409)
    sections = _validated_sections(payload.sections)
    definition = ReportDefinition(
        tenant_id=scope.tenant_id,
        name=payload.name.strip(),
        fund_product_id=payload.fund_product_id,
        template_key=payload.template_key,
        report_type=payload.report_type,
        sections=sections,
        settings=payload.settings,
        created_by_user_id=scope.user.id,
    )
    session.add(definition)
    session.flush()
    _audit(
        session, request, scope,
        action="report_definition.create",
        resource_type="report_definition",
        resource_id=definition.id,
        detail={
            "name": definition.name,
            "template_key": definition.template_key,
            "sections": sections,
        },
    )
    session.commit()
    return ReportDefinitionItem.model_validate(definition, from_attributes=True)


@router.post("/preview", response_model=ReportPreviewResponse)
def preview_report(
    payload: ReportPreviewRequest,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> ReportPreviewResponse:
    del scope
    product = _data_service.get_product(session, payload.fund_product_id)
    snapshot = _data_service.build_snapshot(
        session,
        product,
        report_date=payload.report_date,
        share_product_code=_share_code(payload.settings),
    )
    return ReportPreviewResponse.model_validate(snapshot)


@router.post("/generate", response_model=ReportGenerateResponse)
def generate_report(
    payload: ReportGenerateRequest,
    request: Request,
    session: TenantDatabaseSession,
    scope: OperatorScope,
) -> ReportGenerateResponse:
    definition = None
    settings_payload = dict(payload.settings)
    if payload.definition_id is not None:
        definition = session.get(ReportDefinition, payload.definition_id)
        if definition is None:
            raise AppError("REPORT_DEFINITION_NOT_FOUND", "未找到报表定义", status_code=404)
        product_id = definition.fund_product_id
        template_key = definition.template_key
        sections = list(definition.sections)
        settings_payload = {**(definition.settings or {}), **settings_payload}
    else:
        product_id = payload.fund_product_id
        template_key = payload.template_key or "builtin:weekly"
        sections = payload.sections or list(DEFAULT_REPORT_SECTIONS)
    assert product_id is not None
    product = _data_service.get_product(session, product_id)
    template = _resolve_template(session, template_key)
    sections = _validated_sections(sections)
    snapshot = _data_service.build_snapshot(
        session,
        product,
        report_date=payload.report_date,
        share_product_code=_share_code(settings_payload),
    )
    actual_date = date.fromisoformat(snapshot["report_date"])
    run = ReportRun(
        tenant_id=scope.tenant_id,
        definition_id=definition.id if definition else None,
        fund_product_id=product.id,
        template_key=template_key,
        report_date=actual_date,
        status="processing",
        input_snapshot={**snapshot, "sections": sections, "settings": settings_payload},
        created_by_user_id=scope.user.id,
    )
    session.add(run)
    session.flush()
    safe_product = sanitize_filename(product.product_name, max_length=100)
    filename = f"{safe_product}_{actual_date.isoformat()}_基金周报.pptx"
    relative_path = (
        Path("tenants") / str(scope.tenant_id) / "reporting" / "exports"
        / f"{actual_date.year:04d}" / f"{actual_date.month:02d}"
        / f"{run.id}_{filename}"
    )
    output_path = get_settings().data_directory / relative_path
    template_path = _stored_template_path(template) if template else None
    try:
        ReportPresentationService().generate(
            snapshot,
            output_path=output_path,
            sections=sections,
            template_path=template_path,
        )
        run.status = "success"
        run.output_filename = filename
        run.output_path = relative_path.as_posix()
        outcome = "success"
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)[:2000]
        outcome = "failed"
    _audit(
        session, request, scope,
        action="report.generate",
        resource_type="report_run",
        resource_id=run.id,
        outcome=outcome,
        detail={
            "product_id": product.id,
            "template_key": template_key,
            "report_date": actual_date.isoformat(),
            "sections": sections,
            "output_filename": run.output_filename,
            "error": run.error_message,
        },
    )
    session.commit()
    item = _run_item(run, product.product_name)
    if run.status != "success":
        raise AppError("REPORT_GENERATION_FAILED", "报表生成失败，请查看生成记录", status_code=500)
    return ReportGenerateResponse(run=item, download_url=f"/api/v1/reports/runs/{run.id}/download")


@router.get("/runs", response_model=list[ReportRunItem])
def list_report_runs(
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> list[ReportRunItem]:
    del scope
    rows = session.execute(
        select(ReportRun, FundProduct.product_name)
        .join(FundProduct, FundProduct.id == ReportRun.fund_product_id)
        .order_by(ReportRun.id.desc())
        .limit(100)
    )
    return [_run_item(run, product_name) for run, product_name in rows]


@router.get("/runs/{run_id}/download")
def download_report(
    run_id: int,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> FileResponse:
    del scope
    run = session.get(ReportRun, run_id)
    if run is None or run.status != "success" or not run.output_path:
        raise AppError("REPORT_OUTPUT_NOT_FOUND", "报表文件不存在", status_code=404)
    path = _safe_data_path(run.output_path)
    if not path.is_file():
        raise AppError("REPORT_OUTPUT_NOT_FOUND", "报表文件已丢失", status_code=404)
    return FileResponse(
        path,
        filename=run.output_filename or path.name,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


def _resolve_template(session: Session, template_key: str) -> ReportTemplate | None:
    if template_key == "builtin:weekly":
        return None
    if not template_key.startswith("uploaded:"):
        raise AppError("REPORT_TEMPLATE_NOT_FOUND", "未找到报表模板", status_code=404)
    try:
        template_id = int(template_key.split(":", 1)[1])
    except ValueError as exc:
        raise AppError("REPORT_TEMPLATE_NOT_FOUND", "报表模板编号无效", status_code=404) from exc
    template = session.get(ReportTemplate, template_id)
    if template is None or not template.is_active:
        raise AppError("REPORT_TEMPLATE_NOT_FOUND", "未找到报表模板", status_code=404)
    return template


def _stored_template_path(template: ReportTemplate) -> Path:
    path = _safe_data_path(template.stored_path)
    if not path.is_file():
        raise AppError("REPORT_TEMPLATE_FILE_MISSING", "模板文件已丢失")
    return path


def _safe_data_path(relative_path: str) -> Path:
    root = get_settings().data_directory.resolve()
    path = (root / relative_path).resolve()
    if path != root and root not in path.parents:
        raise AppError("REPORT_PATH_INVALID", "报表文件路径无效")
    return path


def _validated_sections(sections: list[str]) -> list[str]:
    selected = list(dict.fromkeys(sections or DEFAULT_REPORT_SECTIONS))
    unknown = set(selected) - set(DEFAULT_REPORT_SECTIONS)
    if unknown:
        invalid = ", ".join(sorted(unknown))
        raise AppError("REPORT_SECTION_INVALID", f"存在不支持的报表区域：{invalid}")
    return selected


def _share_code(settings_payload: dict) -> str | None:
    value = settings_payload.get("share_product_code")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _run_item(run: ReportRun, product_name: str) -> ReportRunItem:
    return ReportRunItem(
        id=run.id,
        definition_id=run.definition_id,
        fund_product_id=run.fund_product_id,
        product_name=product_name,
        template_key=run.template_key,
        report_date=run.report_date,
        status=run.status,
        output_filename=run.output_filename,
        error_message=run.error_message,
        create_time=run.create_time,
    )


def _audit(
    session: Session,
    request: Request,
    scope: TenantContext,
    *,
    action: str,
    resource_type: str,
    resource_id: int,
    detail: dict,
    outcome: str = "success",
) -> None:
    AuditService(audit_signing_key(get_settings().security)).append(
        session,
        tenant_id=scope.tenant_id,
        actor_user_id=scope.user.id,
        actor_username=scope.user.username,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        detail=detail,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
