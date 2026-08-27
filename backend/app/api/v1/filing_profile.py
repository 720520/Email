"""租户级动态开户与备案复用资料。"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, TenantDatabaseSession, TenantScope, require_roles
from app.api.schemas.filing_profile import (
    FilingFieldCreate,
    FilingFieldDefinition,
    FilingFieldUpdate,
    FilingFileVersionItem,
    FilingProfileResponse,
    FilingProfileUpdate,
)
from app.core.config import get_settings
from app.core.credential_security import audit_signing_key
from app.core.errors import AppError
from app.core.files import atomic_write_bytes
from app.db.models import AppUser, FilingField, FilingFileVersion, FilingProfile, UserRole
from app.services.archive_service import sanitize_filename
from app.services.audit_service import AuditService

router = APIRouter()
AdminScope = Annotated[TenantContext, Depends(require_roles(UserRole.ADMIN))]

# 首次进入时为租户建立起始模板。之后字段完全由管理员维护，软删除不会被重新创建。
TEXT_TEMPLATES = [
    ("company_name", "管理人全称", "公司基本信息", False, False, ["营业执照", "投资者信息表"]),
    ("unified_credit_code", "统一社会信用代码", "公司基本信息", False, False, ["营业执照"]),
    ("registration_address", "注册地址", "公司基本信息", False, True, ["营业执照"]),
    ("office_address", "办公地址", "公司基本信息", False, True, ["投资者信息表"]),
    ("legal_representative", "法定代表人", "公司基本信息", False, False, ["营业执照"]),
    ("registered_capital", "注册资本", "公司基本信息", False, False, ["营业执照"]),
    ("company_type", "公司类型", "公司基本信息", False, False, ["营业执照"]),
    ("business_scope", "经营范围", "公司基本信息", False, True, ["营业执照"]),
    ("established_date", "成立日期", "公司基本信息", False, False, ["营业执照"]),
    ("business_term", "营业期限", "公司基本信息", False, False, ["营业执照"]),
    ("manager_registration_code", "管理人登记编码", "牌照与联系信息", False, False, ["管理人公示"]),
    ("association_member_type", "协会会员类型", "牌照与联系信息", False, False, ["管理人公示"]),
    ("contact_name", "机构联系人", "牌照与联系信息", False, False, ["投资者信息表"]),
    ("contact_phone", "联系电话", "牌照与联系信息", True, False, ["投资者信息表"]),
    ("contact_email", "联系邮箱", "牌照与联系信息", True, False, ["投资者信息表"]),
    (
        "tax_resident_country",
        "税收居民国（地区）",
        "牌照与联系信息",
        False,
        False,
        ["税收居民声明"],
    ),
    ("agent_name", "开户代理人姓名", "人员与授权", False, False, ["授权委托书"]),
    ("agent_id_number", "开户代理人证件号码", "人员与授权", True, False, ["代理人身份证"]),
    ("agent_mobile", "开户代理人手机", "人员与授权", True, False, ["授权委托书"]),
    ("legal_id_number", "法定代表人证件号码", "人员与授权", True, False, ["法人身份证"]),
    (
        "beneficial_owner_summary",
        "受益所有人及控制关系",
        "人员与授权",
        True,
        True,
        ["受益所有人信息表"],
    ),
    ("instruction_sender", "指令下达人", "人员与授权", True, False, ["开户影像清单"]),
    ("fund_transfer_operator", "资金调拨人", "人员与授权", True, False, ["开户影像清单"]),
    ("settlement_confirmer", "结算单确认人", "人员与授权", True, False, ["开户影像清单"]),
    ("default_custodian", "常用托管机构", "账户与业务偏好", False, False, ["基金合同"]),
    ("default_broker", "常用证券经纪机构", "账户与业务偏好", False, False, ["佣金协议"]),
    ("invoice_title", "开票抬头", "账户与业务偏好", False, False, ["手续费申请"]),
    ("invoice_tax_number", "开票税号", "账户与业务偏好", True, False, ["手续费申请"]),
]
FILE_TEMPLATES = [
    ("business_license_file", "营业执照扫描件/盖章版", "公司证照", "租户长期复用"),
    ("articles_file", "公司章程（合伙企业为合伙协议）", "公司证照", "变更后更新"),
    ("manager_registration_file", "管理人登记证明/协会公示", "协会与备案", "租户长期复用"),
    ("internal_control_file", "内部控制制度", "制度文件", "版本化复用"),
    ("risk_management_file", "风险管理制度", "制度文件", "版本化复用"),
    ("suitability_rules_file", "投资者适当性及品种管理制度", "制度文件", "版本化复用"),
    ("legal_id_file", "法定代表人身份证正反面", "人员影像", "证件有效期内复用"),
    ("agent_id_file", "开户代理人身份证及头部照", "人员影像", "按代理人复用"),
    ("authorized_people_file", "指令/调拨/结算人员身份证", "人员影像", "按人员复用"),
    ("beneficial_owner_file", "受益所有人身份证明及控制关系", "人员影像", "结构变更后更新"),
    ("authorization_file", "授权委托书", "开户表单", "按机构模板更新"),
    ("tax_declaration_file", "机构税收居民声明文件", "开户表单", "信息不变时复用"),
    ("beneficial_owner_form_file", "受益所有人信息收集表", "开户表单", "按机构模板更新"),
    ("credit_checks_file", "征信/执行/工商公示查询材料", "尽调材料", "每次开户重新查询"),
    ("fund_filing_file", "基金备案证明/备案函", "产品材料", "按产品提供"),
    ("fund_contract_file", "基金合同或集合产品合同样本", "产品材料", "按产品提供"),
    ("custodian_account_file", "托管账户信息确认函", "产品材料", "按产品提供"),
    ("holder_register_file", "份额持有人名册/登记确认单", "产品材料", "按基准日提供"),
    ("securities_accounts_file", "证券账户业务确认文件", "产品材料", "按产品/账户提供"),
    ("commitment_file", "管理人承诺函", "产品材料", "按开户事项签署"),
    ("fund_agreement_file", "基金合同、三方备忘录及银期协议", "产品材料", "按产品提供"),
]


@router.get("", response_model=FilingProfileResponse)
def get_profile(session: TenantDatabaseSession, scope: TenantScope) -> FilingProfileResponse:
    _ensure_default_fields(session, scope)
    session.commit()
    return _response(session, scope)


@router.put("", response_model=FilingProfileResponse)
def update_profile(
    payload: FilingProfileUpdate,
    request: Request,
    session: TenantDatabaseSession,
    scope: AdminScope,
) -> FilingProfileResponse:
    _legacy_read_only()
    _ensure_default_fields(session, scope)
    valid_fields = {
        item.field_key
        for item in session.scalars(
            select(FilingField).where(
                FilingField.is_active.is_(True), FilingField.field_type == "text"
            )
        )
    }
    values = {
        key: str(value).strip()[:20_000]
        for key, value in payload.field_values.items()
        if key in valid_fields and str(value).strip()
    }
    item = _profile(session)
    old_values = item.field_values if item else {}
    inactive_values = {key: value for key, value in old_values.items() if key not in valid_fields}
    changed = sorted(key for key in valid_fields if old_values.get(key, "") != values.get(key, ""))
    if item is None:
        item = FilingProfile(
            tenant_id=scope.tenant_id, field_values={**inactive_values, **values}, document_notes={}
        )
        session.add(item)
    else:
        item.field_values = {**inactive_values, **values}
    _audit(
        session,
        request,
        scope,
        "filing_profile.values.update",
        "filing_profile",
        item.id or 0,
        {"changed_fields": changed, "changed_count": len(changed)},
    )
    session.commit()
    return _response(session, scope)


@router.post("/fields", response_model=FilingFieldDefinition)
def create_field(
    payload: FilingFieldCreate,
    request: Request,
    session: TenantDatabaseSession,
    scope: AdminScope,
) -> FilingFieldDefinition:
    _legacy_read_only()
    field = FilingField(
        tenant_id=scope.tenant_id,
        field_key=f"custom_{uuid.uuid4().hex}",
        label=payload.label,
        category=payload.category,
        field_type=payload.field_type,
        sensitive=payload.sensitive,
        multiline=payload.multiline if payload.field_type == "text" else False,
        source_forms=_clean_sources(payload.source_forms),
        sort_order=payload.sort_order,
        is_active=True,
        created_by_user_id=scope.user.id,
    )
    session.add(field)
    session.flush()
    _audit(
        session,
        request,
        scope,
        "filing_field.create",
        "filing_field",
        field.id,
        {"label": field.label, "category": field.category, "field_type": field.field_type},
    )
    session.commit()
    return _field_item(session, field)


@router.patch("/fields/{field_id}", response_model=FilingFieldDefinition)
def update_field(
    field_id: int,
    payload: FilingFieldUpdate,
    request: Request,
    session: TenantDatabaseSession,
    scope: AdminScope,
) -> FilingFieldDefinition:
    _legacy_read_only()
    field = _active_field(session, field_id)
    if payload.field_type != field.field_type:
        raise AppError(
            "FILING_FIELD_TYPE_LOCKED",
            "字段创建后不能切换文本/文件类型；请新建字段",
            status_code=409,
        )
    before = {
        "label": field.label,
        "category": field.category,
        "sensitive": field.sensitive,
        "multiline": field.multiline,
        "sort_order": field.sort_order,
    }
    field.label = payload.label
    field.category = payload.category
    field.sensitive = payload.sensitive
    field.multiline = payload.multiline if field.field_type == "text" else False
    field.source_forms = _clean_sources(payload.source_forms)
    field.sort_order = payload.sort_order
    _audit(
        session,
        request,
        scope,
        "filing_field.update",
        "filing_field",
        field.id,
        {
            "before": before,
            "after": {
                "label": field.label,
                "category": field.category,
                "sensitive": field.sensitive,
                "multiline": field.multiline,
                "sort_order": field.sort_order,
            },
        },
    )
    session.commit()
    return _field_item(session, field)


@router.delete("/fields/{field_id}", status_code=204)
def delete_field(
    field_id: int,
    request: Request,
    session: TenantDatabaseSession,
    scope: AdminScope,
) -> Response:
    _legacy_read_only()
    field = _active_field(session, field_id)
    version_count = (
        session.scalar(
            select(func.count(FilingFileVersion.id)).where(FilingFileVersion.field_id == field.id)
        )
        or 0
    )
    field.is_active = False
    _audit(
        session,
        request,
        scope,
        "filing_field.archive",
        "filing_field",
        field.id,
        {
            "label": field.label,
            "field_type": field.field_type,
            "preserved_file_versions": version_count,
        },
    )
    session.commit()
    return Response(status_code=204)


@router.post("/fields/{field_id}/files", response_model=FilingFileVersionItem)
async def upload_file_version(
    field_id: int,
    request: Request,
    session: TenantDatabaseSession,
    scope: AdminScope,
    file: Annotated[UploadFile, File(description="备案资料文件")],
) -> FilingFileVersionItem:
    _legacy_read_only()
    field = _active_field(session, field_id)
    if field.field_type != "file":
        raise AppError("FILING_FIELD_NOT_FILE", "只有文件字段可以上传附件", status_code=409)
    settings = get_settings()
    content = await file.read(settings.storage.max_filing_file_bytes + 1)
    if not content:
        raise AppError("FILING_FILE_EMPTY", "上传文件不能为空")
    if len(content) > settings.storage.max_filing_file_bytes:
        raise AppError("FILING_FILE_TOO_LARGE", "备案文件超过允许大小")
    filename = Path(file.filename or "filing-document").name
    safe_name = sanitize_filename(filename)
    next_version = (
        session.scalar(
            select(func.max(FilingFileVersion.version)).where(
                FilingFileVersion.field_id == field.id
            )
        )
        or 0
    ) + 1
    relative_path = (
        Path("tenants")
        / str(scope.tenant_id)
        / "filing"
        / str(field.id)
        / f"v{next_version}_{uuid.uuid4().hex}_{safe_name}"
    )
    atomic_write_bytes(settings.data_directory / relative_path, content)
    version = FilingFileVersion(
        tenant_id=scope.tenant_id,
        field_id=field.id,
        version=next_version,
        original_name=filename,
        stored_path=relative_path.as_posix(),
        content_hash=hashlib.sha256(content).hexdigest(),
        file_size=len(content),
        content_type=(file.content_type or "application/octet-stream")[:200],
        created_by_user_id=scope.user.id,
    )
    session.add(version)
    session.flush()
    _audit(
        session,
        request,
        scope,
        "filing_file.version.upload",
        "filing_file_version",
        version.id,
        {
            "field_id": field.id,
            "field_label": field.label,
            "version": next_version,
            "filename": filename,
            "file_size": len(content),
            "sha256": version.content_hash,
        },
    )
    session.commit()
    return _version_item(version, scope.user.username)


@router.get("/fields/{field_id}/files/{version_id}/download")
def download_file_version(
    field_id: int,
    version_id: int,
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> FileResponse:
    field = session.scalar(select(FilingField).where(FilingField.id == field_id))
    version = session.scalar(
        select(FilingFileVersion).where(
            FilingFileVersion.id == version_id, FilingFileVersion.field_id == field_id
        )
    )
    if field is None or version is None:
        raise AppError("FILING_FILE_NOT_FOUND", "备案文件版本不存在", status_code=404)
    path = _safe_data_path(version.stored_path)
    if not path.is_file():
        raise AppError("FILING_FILE_MISSING", "备案文件在存储中缺失", status_code=404)
    _audit(
        session,
        request,
        scope,
        "filing_file.version.download",
        "filing_file_version",
        version.id,
        {
            "field_id": field.id,
            "field_label": field.label,
            "version": version.version,
            "filename": version.original_name,
            "sha256": version.content_hash,
        },
    )
    session.commit()
    return FileResponse(
        path,
        filename=version.original_name,
        media_type=version.content_type or "application/octet-stream",
    )


@router.get("/export.txt", response_class=PlainTextResponse)
def export_profile(
    request: Request, session: TenantDatabaseSession, scope: TenantScope
) -> PlainTextResponse:
    _ensure_default_fields(session, scope)
    data = _response(session, scope)
    lines = [f"{data.tenant_name}｜开户与备案复用资料", ""]
    for category in dict.fromkeys(field.category for field in data.fields):
        lines.append(f"【{category}】")
        for field in (item for item in data.fields if item.category == category):
            if field.field_type == "text":
                lines.append(f"{field.label}：{data.field_values.get(field.key, '')}")
            else:
                latest = field.file_versions[0] if field.file_versions else None
                file_text = f"{latest.original_name}（v{latest.version}）" if latest else "未上传"
                lines.append(f"{field.label}：{file_text}")
        lines.append("")
    _audit(
        session,
        request,
        scope,
        "filing_profile.export",
        "filing_profile",
        0,
        {"field_count": len(data.fields), "format": "txt"},
    )
    session.commit()
    return PlainTextResponse(
        "\n".join(lines), headers={"Content-Disposition": "attachment; filename=filing-profile.txt"}
    )


def _ensure_default_fields(session: Session, scope: TenantContext) -> None:
    if session.scalar(select(func.count(FilingField.id))) or 0:
        return
    order = 0
    for key, label, category, sensitive, multiline, sources in TEXT_TEMPLATES:
        session.add(
            FilingField(
                tenant_id=scope.tenant_id,
                field_key=key,
                label=label,
                category=category,
                field_type="text",
                sensitive=sensitive,
                multiline=multiline,
                source_forms=sources,
                sort_order=order,
                is_active=True,
            )
        )
        order += 10
    for key, label, category, scope_note in FILE_TEMPLATES:
        session.add(
            FilingField(
                tenant_id=scope.tenant_id,
                field_key=key,
                label=label,
                category=category,
                field_type="file",
                sensitive=False,
                multiline=False,
                source_forms=[scope_note],
                sort_order=order,
                is_active=True,
            )
        )
        order += 10
    session.flush()


def _response(session: Session, scope: TenantContext) -> FilingProfileResponse:
    profile = _profile(session)
    fields = list(
        session.scalars(
            select(FilingField)
            .where(FilingField.is_active.is_(True))
            .order_by(FilingField.sort_order, FilingField.id)
        )
    )
    return FilingProfileResponse(
        tenant_name=scope.tenant_name,
        can_edit=scope.role == UserRole.ADMIN,
        fields=[_field_item(session, item) for item in fields],
        field_values=profile.field_values if profile else {},
        update_time=profile.update_time if profile else None,
    )


def _field_item(session: Session, field: FilingField) -> FilingFieldDefinition:
    versions = (
        list(
            session.scalars(
                select(FilingFileVersion)
                .where(FilingFileVersion.field_id == field.id)
                .order_by(FilingFileVersion.version.desc())
            )
        )
        if field.field_type == "file"
        else []
    )
    user_ids = {item.created_by_user_id for item in versions if item.created_by_user_id}
    usernames = (
        {
            item.id: item.username
            for item in session.scalars(select(AppUser).where(AppUser.id.in_(user_ids)))
        }
        if user_ids
        else {}
    )
    return FilingFieldDefinition(
        id=field.id,
        key=field.field_key,
        label=field.label,
        category=field.category,
        field_type=field.field_type,
        sensitive=field.sensitive,
        multiline=field.multiline,
        source_forms=list(field.source_forms or []),
        sort_order=field.sort_order,
        file_versions=[
            _version_item(item, usernames.get(item.created_by_user_id, "未知用户"))
            for item in versions
        ],
    )


def _version_item(version: FilingFileVersion, username: str) -> FilingFileVersionItem:
    return FilingFileVersionItem(
        id=version.id,
        version=version.version,
        original_name=version.original_name,
        file_size=version.file_size,
        content_type=version.content_type,
        content_hash=version.content_hash,
        created_by=username,
        create_time=version.create_time,
        download_url=f"/api/v1/filing-profile/fields/{version.field_id}/files/{version.id}/download",
    )


def _profile(session: Session) -> FilingProfile | None:
    return session.scalar(select(FilingProfile))


def _active_field(session: Session, field_id: int) -> FilingField:
    item = session.scalar(
        select(FilingField).where(FilingField.id == field_id, FilingField.is_active.is_(True))
    )
    if item is None:
        raise AppError("FILING_FIELD_NOT_FOUND", "备案字段不存在", status_code=404)
    return item


def _clean_sources(values: list[str]) -> list[str]:
    return [value.strip()[:200] for value in values if value.strip()][:20]


def _legacy_read_only() -> None:
    raise AppError(
        "FILING_PROFILE_READ_ONLY",
        "旧备案资料库已进入只读兼容模式，请使用公司资料和产品资料接口",
        status_code=410,
    )


def _safe_data_path(relative_path: str) -> Path:
    root = get_settings().data_directory.resolve()
    path = (root / relative_path).resolve()
    if path != root and root not in path.parents:
        raise AppError("FILING_FILE_PATH_INVALID", "备案文件路径无效", status_code=500)
    return path


def _audit(
    session: Session,
    request: Request,
    scope: TenantContext,
    action: str,
    resource_type: str,
    resource_id: int,
    detail: dict,
) -> None:
    AuditService(audit_signing_key(get_settings().security)).append(
        session,
        tenant_id=scope.tenant_id,
        actor_user_id=scope.user.id,
        actor_username=scope.user.username,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome="success",
        detail=detail,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
