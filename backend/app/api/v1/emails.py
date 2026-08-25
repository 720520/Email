"""邮件记录分页查询。"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select

from app.api.deps import (
    TenantContext,
    TenantDatabaseSession,
    TenantScope,
    require_roles,
)
from app.api.schemas.common import PageResponse
from app.api.schemas.email_connection import (
    EmailConnectionInfoResponse,
    EmailConnectionTestResponse,
    EmailSyncResponse,
)
from app.api.schemas.email_detail import EmailAttachmentDetail, EmailDetailResponse
from app.api.schemas.operations import EmailListItem
from app.core.config import EmailSettings, get_settings
from app.core.credential_security import (
    CredentialDecryptionError,
    audit_signing_key,
    dedicated_audit_key_configured,
    dedicated_credential_key_configured,
)
from app.core.errors import AppError
from app.db.models import (
    AttachmentParseTask,
    EmailRecord,
    EmailStatus,
    MailboxAccount,
    TriggerType,
    UserRole,
)
from app.db.session import get_database_manager
from app.services.archive_service import sanitize_filename
from app.services.audit_service import AuditService
from app.services.email_connection_service import EmailConnectionService
from app.services.email_detail_service import (
    EmailDetailService,
    EmailPreviewTooLargeError,
    InvalidEmailArchivePathError,
)
from app.services.mail_sync_runner import MailSyncAlreadyRunningError, MailSyncRunner
from app.services.mailbox_account_service import (
    MailboxAccountNotFoundError,
    MailboxAccountService,
)

router = APIRouter()
OperatorScope = Annotated[
    TenantContext,
    Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR)),
]


@router.get("/connection", response_model=EmailConnectionInfoResponse)
def email_connection_info(
    session: TenantDatabaseSession,
    scope: TenantScope,
    mailbox_account_id: int | None = Query(default=None, ge=1),
) -> EmailConnectionInfoResponse:
    account = _selected_account(
        session,
        scope,
        mailbox_account_id=mailbox_account_id,
        allowed_mailbox_ids=scope.mailbox_ids,
    )
    credential_configured = bool(account.credential_ciphertext)
    return EmailConnectionInfoResponse(
        mailbox_account_id=account.id,
        display_name=account.display_name,
        host=account.host,
        port=account.port,
        username=account.username,
        auth_mode=account.auth_mode,
        folder=account.folder,
        transport=(
            "SSL/TLS" if account.use_ssl else "STARTTLS" if account.start_tls else "未加密"
        ),
        timeout_seconds=account.timeout_seconds,
        credential_configured=credential_configured,
        configured=bool(
            account.is_enabled
            and account.host.strip()
            and account.username.strip()
            and credential_configured
        ),
    )


@router.post("/connection/test", response_model=EmailConnectionTestResponse)
def test_email_connection(
    request: Request,
    session: TenantDatabaseSession,
    scope: OperatorScope,
    mailbox_account_id: int | None = Query(default=None, ge=1),
) -> EmailConnectionTestResponse:
    _require_security_ready()
    account, settings = _selected_mailbox(
        session,
        scope,
        mailbox_account_id=mailbox_account_id,
        allowed_mailbox_ids=scope.operable_mailbox_ids,
    )
    result = EmailConnectionService(settings).test_connection()
    MailboxAccountService.update_connection_result(
        account,
        success=result.success,
        error_message=result.message,
    )
    _audit_email_action(
        session,
        scope,
        request,
        mailbox_id=account.id,
        action="mailbox.connection.test",
        resource_type="mailbox_account",
        resource_id=account.id,
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


@router.post("/sync", response_model=EmailSyncResponse)
def sync_email_now(
    session: TenantDatabaseSession,
    scope: OperatorScope,
    mailbox_account_id: int | None = Query(default=None, ge=1),
) -> EmailSyncResponse:
    _require_security_ready()
    settings = get_settings()
    account, email_settings = _selected_mailbox(
        session,
        scope,
        mailbox_account_id=mailbox_account_id,
        allowed_mailbox_ids=scope.operable_mailbox_ids,
    )
    try:
        execution = MailSyncRunner(
            settings,
            get_database_manager().session_factory,
            tenant_id=scope.tenant_id,
            mailbox_account_id=account.id,
            email_settings=email_settings,
            actor_user_id=scope.user.id,
            actor_username=scope.user.username,
        ).run(trigger_type=TriggerType.MANUAL)
    except MailSyncAlreadyRunningError as exc:
        raise AppError("MAIL_SYNC_RUNNING", str(exc), status_code=409) from exc
    result = execution.result
    queued_attachment_count = session.scalar(
        select(func.count(AttachmentParseTask.id)).where(
            AttachmentParseTask.source_job_run_id == execution.job_run_id,
            AttachmentParseTask.status == "queued",
        )
    ) or 0
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
        job_run_id=execution.job_run_id,
        attempts=result.attempts,
        discovered_count=len(result.discovered_uids),
        archived_count=len(result.archived_uids),
        ignored_count=len(result.ignored_uids),
        duplicate_count=len(result.duplicate_uids),
        failed_count=len(result.failed_uids),
        queued_attachment_count=queued_attachment_count,
    )


@router.get("", response_model=PageResponse[EmailListItem])
def list_emails(
    session: TenantDatabaseSession,
    scope: TenantScope,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None, max_length=200),
    status: EmailStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    mailbox_account_id: int | None = Query(default=None, ge=1),
) -> PageResponse[EmailListItem]:
    if date_from and date_to and date_from > date_to:
        raise AppError("INVALID_DATE_RANGE", "开始日期不能晚于结束日期")

    conditions = []
    if mailbox_account_id is not None:
        if mailbox_account_id not in scope.mailbox_ids:
            raise AppError("FORBIDDEN", "当前账号没有查看该邮箱的权限", status_code=403)
        conditions.append(EmailRecord.mailbox_account_id == mailbox_account_id)
    if keyword and keyword.strip():
        search = keyword.strip()
        conditions.append(
            or_(
                EmailRecord.subject.contains(search, autoescape=True),
                EmailRecord.sender.contains(search, autoescape=True),
            )
        )
    if status is not None:
        conditions.append(EmailRecord.status == status)
    start_time, end_time = _date_bounds(date_from, date_to)
    if start_time is not None:
        conditions.append(EmailRecord.receive_time >= start_time)
    if end_time is not None:
        conditions.append(EmailRecord.receive_time < end_time)

    total = session.scalar(select(func.count(EmailRecord.id)).where(*conditions)) or 0
    statement = (
        select(EmailRecord, MailboxAccount.display_name)
        .join(MailboxAccount, MailboxAccount.id == EmailRecord.mailbox_account_id)
        .where(*conditions)
        .order_by(EmailRecord.receive_time.desc(), EmailRecord.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        EmailListItem(
            id=item.id,
            mailbox_account_id=item.mailbox_account_id,
            mailbox_name=mailbox_name,
            subject=item.subject,
            sender=item.sender,
            receive_time=item.receive_time,
            attachment_count=item.attachment_count,
            status=item.status,
            error_message=item.error_message,
        )
        for item, mailbox_name in session.execute(statement)
    ]
    return PageResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{email_id}", response_model=EmailDetailResponse)
def get_email_detail(
    email_id: int,
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> EmailDetailResponse:
    email = session.get(EmailRecord, email_id)
    if email is None:
        raise AppError("EMAIL_NOT_FOUND", "邮件记录不存在", status_code=404)
    if not scope.can_read_content(email.mailbox_account_id):
        raise AppError("FORBIDDEN", "当前账号没有查看邮件正文的权限", status_code=403)

    service = EmailDetailService(get_settings().data_directory)
    try:
        archive_path = service.resolve_archive_path(email.eml_path)
        preview = service.body_preview(archive_path)
    except InvalidEmailArchivePathError as exc:
        raise AppError("EMAIL_ARCHIVE_INVALID", "原始邮件归档路径无效", status_code=409) from exc
    except EmailPreviewTooLargeError:
        archive_path = service.resolve_archive_path(email.eml_path)
        preview_text = "原始邮件较大，正文无法在线预览，请下载 EML 文件查看。"
        response = _email_detail_response(email, preview_text, False, archive_path is not None)
        _audit_email_action(
            session, scope, request, mailbox_id=email.mailbox_account_id,
            action="email.content.view", resource_type="email_record",
            resource_id=email.id, outcome="success", detail={"preview_too_large": True},
        )
        session.commit()
        return response
    except (OSError, ValueError) as exc:
        raise AppError("EMAIL_PREVIEW_FAILED", "原始邮件正文读取失败", status_code=422) from exc

    response = _email_detail_response(
        email,
        preview.text,
        preview.truncated,
        archive_path is not None,
    )
    _audit_email_action(
        session, scope, request, mailbox_id=email.mailbox_account_id,
        action="email.content.view", resource_type="email_record",
        resource_id=email.id, outcome="success", detail={"body_truncated": preview.truncated},
    )
    session.commit()
    return response


@router.get("/{email_id}/raw", response_class=FileResponse)
def download_raw_email(
    email_id: int,
    request: Request,
    session: TenantDatabaseSession,
    scope: TenantScope,
) -> FileResponse:
    email = session.get(EmailRecord, email_id)
    if email is None:
        raise AppError("EMAIL_NOT_FOUND", "邮件记录不存在", status_code=404)
    if not scope.can_read_content(email.mailbox_account_id):
        raise AppError("FORBIDDEN", "当前账号没有下载原始邮件的权限", status_code=403)
    try:
        archive_path = EmailDetailService(get_settings().data_directory).resolve_archive_path(
            email.eml_path
        )
    except InvalidEmailArchivePathError as exc:
        raise AppError("EMAIL_ARCHIVE_INVALID", "原始邮件归档路径无效", status_code=409) from exc
    if archive_path is None:
        raise AppError("EMAIL_ARCHIVE_NOT_FOUND", "该邮件没有可下载的原始归档", status_code=404)

    filename = sanitize_filename(f"{email.subject or 'email'}_{email.id}.eml")
    _audit_email_action(
        session, scope, request, mailbox_id=email.mailbox_account_id,
        action="email.raw.download", resource_type="email_record",
        resource_id=email.id, outcome="success",
    )
    session.commit()
    return FileResponse(archive_path, media_type="message/rfc822", filename=filename)


def _selected_mailbox(
    session,
    scope: TenantContext,
    *,
    mailbox_account_id: int | None,
    allowed_mailbox_ids: tuple[int, ...],
) -> tuple[MailboxAccount, EmailSettings]:
    account = _selected_account(
        session,
        scope,
        mailbox_account_id=mailbox_account_id,
        allowed_mailbox_ids=allowed_mailbox_ids,
    )
    service = MailboxAccountService(get_settings())
    try:
        return account, service.runtime_settings(account)
    except CredentialDecryptionError as exc:
        raise AppError(
            "MAILBOX_CREDENTIAL_INVALID",
            "邮箱凭据无法解密，请由管理员重新配置",
            status_code=409,
        ) from exc


def _selected_account(
    session,
    scope: TenantContext,
    *,
    mailbox_account_id: int | None,
    allowed_mailbox_ids: tuple[int, ...],
) -> MailboxAccount:
    service = MailboxAccountService(get_settings())
    try:
        if mailbox_account_id is None:
            return service.get_default(
                session,
                tenant_id=scope.tenant_id,
                allowed_mailbox_ids=allowed_mailbox_ids,
            )
        return service.get_account(
            session,
            tenant_id=scope.tenant_id,
            mailbox_account_id=mailbox_account_id,
            allowed_mailbox_ids=allowed_mailbox_ids,
            require_enabled=True,
        )
    except MailboxAccountNotFoundError as exc:
        raise AppError("MAILBOX_NOT_AVAILABLE", str(exc), status_code=409) from exc


def _audit_email_action(
    session,
    scope: TenantContext,
    request: Request,
    *,
    mailbox_id: int,
    action: str,
    resource_type: str,
    resource_id: int,
    outcome: str,
    detail: dict | None = None,
) -> None:
    AuditService(audit_signing_key(get_settings().security)).append(
        session,
        tenant_id=scope.tenant_id,
        actor_user_id=scope.user.id,
        actor_username=scope.user.username,
        mailbox_account_id=mailbox_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        detail=detail,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


def _email_detail_response(
    email: EmailRecord,
    body_text: str,
    body_truncated: bool,
    original_available: bool,
) -> EmailDetailResponse:
    return EmailDetailResponse(
        id=email.id,
        subject=email.subject,
        sender=email.sender,
        receive_time=email.receive_time,
        status=email.status,
        error_message=email.error_message,
        attachments=[
            EmailAttachmentDetail(
                id=attachment.id,
                original_name=attachment.original_name,
                file_type=attachment.file_type,
                parse_status=attachment.parse_status,
                error_message=attachment.error_message,
            )
            for attachment in email.attachments
        ],
        body_text=body_text,
        body_truncated=body_truncated,
        original_available=original_available,
    )


def _date_bounds(
    date_from: date | None,
    date_to: date | None,
) -> tuple[datetime | None, datetime | None]:
    timezone = ZoneInfo(get_settings().storage.archive_timezone)
    start = (
        datetime.combine(date_from, time.min, tzinfo=timezone).astimezone(UTC)
        if date_from
        else None
    )
    end = (
        datetime.combine(date_to, time.min, tzinfo=timezone).astimezone(UTC)
        + timedelta(days=1)
        if date_to
        else None
    )
    return start, end


def _require_security_ready() -> None:
    security = get_settings().security
    if not (
        dedicated_credential_key_configured(security)
        and dedicated_audit_key_configured(security)
    ):
        raise AppError(
            "MAILBOX_SECURITY_NOT_READY",
            "请先配置独立邮箱凭据密钥和审计签名密钥",
            status_code=503,
        )
