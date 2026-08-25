"""多邮箱账户配置、连接、同步和邮箱级用户授权。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from app.api.deps import TenantContext, TenantDatabaseSession, TenantScope, require_roles
from app.api.schemas.email_connection import EmailConnectionTestResponse, EmailSyncResponse
from app.api.schemas.mailbox import (
    MailboxAccountCreate,
    MailboxAccountItem,
    MailboxAccountUpdate,
    MailboxGrantItem,
    MailboxGrantUpdate,
    MailboxPermissions,
    MailboxSecurityStatus,
    TenantMemberItem,
)
from app.core.config import get_settings
from app.core.credential_security import (
    CredentialDecryptionError,
    audit_signing_key,
    dedicated_audit_key_configured,
    dedicated_credential_key_configured,
)
from app.core.errors import AppError
from app.db.models import (
    AppUser,
    AttachmentParseTask,
    MailboxAccount,
    MailboxUserGrant,
    TenantMembership,
    TriggerType,
    UserRole,
)
from app.db.session import get_database_manager
from app.services.audit_service import AuditService
from app.services.email_connection_service import EmailConnectionService
from app.services.mail_sync_runner import MailSyncAlreadyRunningError, MailSyncRunner
from app.services.mailbox_account_service import (
    DedicatedCredentialKeyRequiredError,
    MailboxAccountConflictError,
    MailboxAccountNotFoundError,
    MailboxAccountService,
)

router = APIRouter()
AdminScope = Annotated[TenantContext, Depends(require_roles(UserRole.ADMIN))]
OperatorScope = Annotated[
    TenantContext,
    Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR)),
]


@router.get("/security-status", response_model=MailboxSecurityStatus)
def mailbox_security_status(scope: TenantScope) -> MailboxSecurityStatus:
    del scope
    security = get_settings().security
    credential_ready = dedicated_credential_key_configured(security)
    audit_ready = dedicated_audit_key_configured(security)
    return MailboxSecurityStatus(
        credential_key_configured=credential_ready,
        audit_key_configured=audit_ready,
        ready_for_credentials=credential_ready and audit_ready,
    )


@router.get("", response_model=list[MailboxAccountItem])
def list_mailboxes(
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> list[MailboxAccountItem]:
    service = MailboxAccountService(get_settings())
    allowed_ids = None if scope.role == UserRole.ADMIN else scope.mailbox_ids
    accounts = service.list_accounts(
        session,
        tenant_id=scope.tenant_id,
        allowed_mailbox_ids=allowed_ids,
    )
    grants = {
        item.mailbox_account_id: item
        for item in session.scalars(
            select(MailboxUserGrant).where(
                MailboxUserGrant.tenant_id == scope.tenant_id,
                MailboxUserGrant.user_id == scope.user.id,
                MailboxUserGrant.is_active.is_(True),
            )
        )
    }
    return [_mailbox_item(account, grants.get(account.id)) for account in accounts]


@router.post("", response_model=MailboxAccountItem, status_code=201)
def create_mailbox(
    payload: MailboxAccountCreate,
    request: Request,
    session: TenantDatabaseSession,
    scope: AdminScope,
) -> MailboxAccountItem:
    _require_security_ready()
    service = MailboxAccountService(get_settings())
    values = _clean_values(payload.model_dump(exclude={"credential"}))
    credential = payload.credential.get_secret_value() if payload.credential else None
    try:
        mailbox = service.create_account(
            session,
            tenant_id=scope.tenant_id,
            creator_user_id=scope.user.id,
            values=values,
            credential=credential,
        )
    except (MailboxAccountConflictError, DedicatedCredentialKeyRequiredError) as exc:
        raise AppError("MAILBOX_CONFIGURATION_INVALID", str(exc), status_code=409) from exc
    _audit(
        session,
        scope,
        request,
        mailbox_id=mailbox.id,
        action="mailbox.create",
        outcome="success",
        detail={"credential_configured": bool(credential)},
    )
    session.commit()
    grant = session.scalar(
        select(MailboxUserGrant).where(
            MailboxUserGrant.mailbox_account_id == mailbox.id,
            MailboxUserGrant.user_id == scope.user.id,
        )
    )
    return _mailbox_item(mailbox, grant)


@router.patch("/{mailbox_id}", response_model=MailboxAccountItem)
def update_mailbox(
    mailbox_id: int,
    payload: MailboxAccountUpdate,
    request: Request,
    session: TenantDatabaseSession,
    scope: AdminScope,
) -> MailboxAccountItem:
    _require_security_ready()
    mailbox = _manageable_mailbox(session, scope, mailbox_id)
    service = MailboxAccountService(get_settings())
    credential_supplied = "credential" in payload.model_fields_set
    credential = payload.credential.get_secret_value() if payload.credential else None
    values = _clean_values(
        payload.model_dump(
            exclude={"credential", "clear_credential"},
            exclude_unset=True,
        )
    )
    try:
        mailbox = service.update_account(
            session,
            mailbox=mailbox,
            values=values,
            credential=credential,
            credential_supplied=credential_supplied,
            clear_credential=payload.clear_credential,
        )
    except (MailboxAccountConflictError, DedicatedCredentialKeyRequiredError) as exc:
        raise AppError("MAILBOX_CONFIGURATION_INVALID", str(exc), status_code=409) from exc
    _audit(
        session,
        scope,
        request,
        mailbox_id=mailbox.id,
        action="mailbox.update",
        outcome="success",
        detail={
            "changed_fields": sorted(payload.model_fields_set - {"credential"}),
            "credential_changed": credential_supplied or payload.clear_credential,
        },
    )
    session.commit()
    grant = session.scalar(
        select(MailboxUserGrant).where(
            MailboxUserGrant.mailbox_account_id == mailbox.id,
            MailboxUserGrant.user_id == scope.user.id,
        )
    )
    return _mailbox_item(mailbox, grant)


@router.post("/{mailbox_id}/connection-test", response_model=EmailConnectionTestResponse)
def test_mailbox_connection(
    mailbox_id: int,
    request: Request,
    session: TenantDatabaseSession,
    scope: OperatorScope,
) -> EmailConnectionTestResponse:
    _require_security_ready()
    mailbox, runtime = _operable_runtime_mailbox(session, scope, mailbox_id)
    result = EmailConnectionService(runtime).test_connection()
    MailboxAccountService.update_connection_result(
        mailbox,
        success=result.success,
        error_message=result.message,
    )
    _audit(
        session,
        scope,
        request,
        mailbox_id=mailbox.id,
        action="mailbox.connection.test",
        outcome="success" if result.success else "failure",
        detail={"latency_ms": result.latency_ms, "message_count": result.message_count},
    )
    session.commit()
    return EmailConnectionTestResponse(
        success=result.success,
        message=result.message,
        checked_at=result.checked_at,
        latency_ms=result.latency_ms,
        uid_validity=result.uid_validity,
        message_count=result.message_count,
    )


@router.post("/{mailbox_id}/sync", response_model=EmailSyncResponse)
def sync_mailbox(
    mailbox_id: int,
    session: TenantDatabaseSession,
    scope: OperatorScope,
) -> EmailSyncResponse:
    _require_security_ready()
    mailbox, runtime = _operable_runtime_mailbox(session, scope, mailbox_id)
    try:
        execution = MailSyncRunner(
            get_settings(),
            get_database_manager().session_factory,
            tenant_id=scope.tenant_id,
            mailbox_account_id=mailbox.id,
            email_settings=runtime,
            actor_user_id=scope.user.id,
            actor_username=scope.user.username,
        ).run(trigger_type=TriggerType.MANUAL)
    except MailSyncAlreadyRunningError as exc:
        raise AppError("MAIL_SYNC_RUNNING", str(exc), status_code=409) from exc
    queued_attachment_count = session.scalar(
        select(func.count(AttachmentParseTask.id)).where(
            AttachmentParseTask.source_job_run_id == execution.job_run_id,
            AttachmentParseTask.status == "queued",
        )
    ) or 0
    return _sync_response(execution.job_run_id, execution.result, queued_attachment_count)


@router.get("/members", response_model=list[TenantMemberItem])
def list_tenant_members(
    session: TenantDatabaseSession,
    scope: AdminScope,
) -> list[TenantMemberItem]:
    statement = (
        select(TenantMembership, AppUser)
        .join(AppUser, TenantMembership.user_id == AppUser.id)
        .where(TenantMembership.tenant_id == scope.tenant_id)
        .order_by(AppUser.username)
    )
    return [
        TenantMemberItem(
            user_id=user.id,
            username=user.username,
            role=membership.role,
            is_active=membership.is_active and user.is_active,
        )
        for membership, user in session.execute(statement)
    ]


@router.get("/{mailbox_id}/grants", response_model=list[MailboxGrantItem])
def list_mailbox_grants(
    mailbox_id: int,
    session: TenantDatabaseSession,
    scope: AdminScope,
) -> list[MailboxGrantItem]:
    _manageable_mailbox(session, scope, mailbox_id)
    statement = (
        select(TenantMembership, AppUser, MailboxUserGrant)
        .join(AppUser, TenantMembership.user_id == AppUser.id)
        .outerjoin(
            MailboxUserGrant,
            (MailboxUserGrant.user_id == AppUser.id)
            & (MailboxUserGrant.mailbox_account_id == mailbox_id)
            & (MailboxUserGrant.tenant_id == scope.tenant_id),
        )
        .where(TenantMembership.tenant_id == scope.tenant_id)
        .order_by(AppUser.username)
    )
    return [
        _grant_item(membership, user, grant)
        for membership, user, grant in session.execute(statement)
    ]


@router.put("/{mailbox_id}/grants/{user_id}", response_model=MailboxGrantItem)
def update_mailbox_grant(
    mailbox_id: int,
    user_id: int,
    payload: MailboxGrantUpdate,
    request: Request,
    session: TenantDatabaseSession,
    scope: AdminScope,
) -> MailboxGrantItem:
    _require_security_ready()
    _manageable_mailbox(session, scope, mailbox_id)
    values = payload.model_dump()
    if user_id == scope.user.id and not (
        values["is_active"] and values["can_manage_credentials"]
    ):
        other_manager = session.scalar(
            select(MailboxUserGrant.id).where(
                MailboxUserGrant.tenant_id == scope.tenant_id,
                MailboxUserGrant.mailbox_account_id == mailbox_id,
                MailboxUserGrant.user_id != scope.user.id,
                MailboxUserGrant.is_active.is_(True),
                MailboxUserGrant.can_manage_credentials.is_(True),
            )
        )
        if other_manager is None:
            raise AppError(
                "MAILBOX_LAST_MANAGER",
                "必须先授权另一名凭据管理员，不能移除邮箱最后一名管理员",
                status_code=409,
            )
    try:
        grant = MailboxAccountService(get_settings()).upsert_grant(
            session,
            tenant_id=scope.tenant_id,
            mailbox_account_id=mailbox_id,
            user_id=user_id,
            values=values,
        )
    except MailboxAccountNotFoundError as exc:
        raise AppError("MAILBOX_GRANT_INVALID", str(exc), status_code=404) from exc
    except MailboxAccountConflictError as exc:
        raise AppError("MAILBOX_GRANT_INVALID", str(exc), status_code=409) from exc
    _audit(
        session,
        scope,
        request,
        mailbox_id=mailbox_id,
        action="mailbox.grant.update",
        outcome="success",
        detail={"target_user_id": user_id, **values},
    )
    session.commit()
    membership, user = session.execute(
        select(TenantMembership, AppUser)
        .join(AppUser, TenantMembership.user_id == AppUser.id)
        .where(
            TenantMembership.tenant_id == scope.tenant_id,
            TenantMembership.user_id == user_id,
        )
    ).one()
    return _grant_item(membership, user, grant)


def _manageable_mailbox(
    session,
    scope: TenantContext,
    mailbox_id: int,
) -> MailboxAccount:
    if mailbox_id not in scope.manageable_mailbox_ids:
        raise AppError("FORBIDDEN", "当前账号没有管理该邮箱凭据的权限", status_code=403)
    try:
        return MailboxAccountService(get_settings()).get_account(
            session,
            tenant_id=scope.tenant_id,
            mailbox_account_id=mailbox_id,
        )
    except MailboxAccountNotFoundError as exc:
        raise AppError("MAILBOX_NOT_FOUND", str(exc), status_code=404) from exc


def _operable_runtime_mailbox(session, scope: TenantContext, mailbox_id: int):
    if not scope.can_operate(mailbox_id):
        raise AppError("FORBIDDEN", "当前账号没有操作该邮箱的权限", status_code=403)
    service = MailboxAccountService(get_settings())
    try:
        mailbox = service.get_account(
            session,
            tenant_id=scope.tenant_id,
            mailbox_account_id=mailbox_id,
            allowed_mailbox_ids=scope.operable_mailbox_ids,
            require_enabled=True,
        )
        return mailbox, service.runtime_settings(mailbox)
    except MailboxAccountNotFoundError as exc:
        raise AppError("MAILBOX_NOT_FOUND", str(exc), status_code=404) from exc
    except CredentialDecryptionError as exc:
        raise AppError(
            "MAILBOX_CREDENTIAL_INVALID",
            "邮箱凭据无法解密，请重新配置",
            status_code=409,
        ) from exc


def _mailbox_item(
    account: MailboxAccount,
    grant: MailboxUserGrant | None,
) -> MailboxAccountItem:
    return MailboxAccountItem(
        id=account.id,
        display_name=account.display_name,
        provider_type=account.provider_type,
        host=account.host,
        port=account.port,
        username=account.username,
        auth_mode=account.auth_mode,
        use_ssl=account.use_ssl,
        start_tls=account.start_tls,
        timeout_seconds=account.timeout_seconds,
        folder=account.folder,
        lookback_days=account.lookback_days,
        max_messages_per_run=account.max_messages_per_run,
        max_attachment_bytes=account.max_attachment_bytes,
        is_default=account.is_default,
        is_enabled=account.is_enabled,
        credential_configured=bool(account.credential_ciphertext),
        configuration_source=account.configuration_source,
        last_connection_status=account.last_connection_status,
        last_connection_at=account.last_connection_at,
        last_connection_error=account.last_connection_error,
        last_sync_status=account.last_sync_status,
        last_sync_at=account.last_sync_at,
        permissions=MailboxPermissions(
            can_read_metadata=bool(grant and grant.can_read_metadata and grant.is_active),
            can_read_content=bool(grant and grant.can_read_content and grant.is_active),
            can_operate=bool(grant and grant.can_operate and grant.is_active),
            can_manage_credentials=bool(
                grant and grant.can_manage_credentials and grant.is_active
            ),
        ),
    )


def _grant_item(membership, user: AppUser, grant: MailboxUserGrant | None) -> MailboxGrantItem:
    return MailboxGrantItem(
        user_id=user.id,
        username=user.username,
        role=membership.role,
        can_read_metadata=bool(grant and grant.can_read_metadata),
        can_read_content=bool(grant and grant.can_read_content),
        can_operate=bool(grant and grant.can_operate),
        can_manage_credentials=bool(grant and grant.can_manage_credentials),
        is_active=bool(grant and grant.is_active),
    )


def _sync_response(job_run_id: int, result, queued_attachment_count: int) -> EmailSyncResponse:
    success = result.fatal_error is None and not result.failed_uids
    message = (
        f"同步完成：发现 {len(result.discovered_uids)} 封，"
        f"新增 {len(result.archived_uids)} 封，"
        f"已处理 {len(result.duplicate_uids)} 封，"
        f"{queued_attachment_count} 个 Excel 附件已进入解析队列"
        if success
        else result.fatal_error or "部分邮件同步失败，请查看日志"
    )
    return EmailSyncResponse(
        success=success,
        message=message,
        job_run_id=job_run_id,
        attempts=result.attempts,
        discovered_count=len(result.discovered_uids),
        archived_count=len(result.archived_uids),
        ignored_count=len(result.ignored_uids),
        duplicate_count=len(result.duplicate_uids),
        failed_count=len(result.failed_uids),
        queued_attachment_count=queued_attachment_count,
    )


def _audit(
    session,
    scope: TenantContext,
    request: Request,
    *,
    mailbox_id: int,
    action: str,
    outcome: str,
    detail: dict[str, Any] | None = None,
) -> None:
    AuditService(audit_signing_key(get_settings().security)).append(
        session,
        tenant_id=scope.tenant_id,
        actor_user_id=scope.user.id,
        actor_username=scope.user.username,
        mailbox_account_id=mailbox_id,
        action=action,
        resource_type="mailbox_account",
        resource_id=mailbox_id,
        outcome=outcome,
        detail=detail,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


def _clean_values(values: dict[str, Any]) -> dict[str, Any]:
    values = {key: value for key, value in values.items() if value is not None}
    for key in ("display_name", "host", "username", "folder"):
        if key in values and isinstance(values[key], str):
            values[key] = values[key].strip()
    return values


def _require_security_ready() -> None:
    security = get_settings().security
    if not (
        dedicated_credential_key_configured(security)
        and dedicated_audit_key_configured(security)
    ):
        raise AppError(
            "MAILBOX_SECURITY_NOT_READY",
            "请先配置独立邮箱凭据密钥和审计签名密钥，再开放邮箱写入或连接操作",
            status_code=503,
        )
