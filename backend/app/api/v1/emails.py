"""邮件记录分页查询。"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DatabaseSession, require_roles
from app.api.schemas.common import PageResponse
from app.api.schemas.email_connection import (
    EmailConnectionInfoResponse,
    EmailConnectionTestResponse,
    EmailSyncResponse,
)
from app.api.schemas.email_detail import EmailAttachmentDetail, EmailDetailResponse
from app.api.schemas.operations import EmailListItem
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import AppUser, EmailRecord, EmailStatus, TriggerType, UserRole
from app.db.session import get_database_manager
from app.services.archive_service import sanitize_filename
from app.services.email_connection_service import EmailConnectionService
from app.services.email_detail_service import (
    EmailDetailService,
    EmailPreviewTooLargeError,
    InvalidEmailArchivePathError,
)
from app.services.mail_sync_runner import MailSyncAlreadyRunningError, MailSyncRunner

router = APIRouter()
OperatorUser = Annotated[
    AppUser,
    Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR)),
]


@router.get("/connection", response_model=EmailConnectionInfoResponse)
def email_connection_info(user: CurrentUser) -> EmailConnectionInfoResponse:
    del user
    settings = get_settings().email
    service = EmailConnectionService(settings)
    return EmailConnectionInfoResponse(
        host=settings.host,
        port=settings.port,
        username=settings.username,
        auth_mode=settings.auth_mode,
        folder=settings.folder,
        transport=service.transport,
        timeout_seconds=settings.timeout_seconds,
        credential_configured=service.credential_configured,
        configured=service.configured,
    )


@router.post("/connection/test", response_model=EmailConnectionTestResponse)
def test_email_connection(user: OperatorUser) -> EmailConnectionTestResponse:
    del user
    result = EmailConnectionService(get_settings().email).test_connection()
    return EmailConnectionTestResponse(
        success=result.success,
        message=result.message,
        checked_at=result.checked_at,
        latency_ms=result.latency_ms,
        uid_validity=result.uid_validity,
        message_count=result.message_count,
    )


@router.post("/sync", response_model=EmailSyncResponse)
def sync_email_now(user: OperatorUser) -> EmailSyncResponse:
    del user
    settings = get_settings()
    try:
        execution = MailSyncRunner(
            settings,
            get_database_manager().session_factory,
        ).run(trigger_type=TriggerType.MANUAL)
    except MailSyncAlreadyRunningError as exc:
        raise AppError("MAIL_SYNC_RUNNING", str(exc), status_code=409) from exc
    result = execution.result
    success = result.fatal_error is None and not result.failed_uids
    message = (
        f"同步完成：发现 {len(result.discovered_uids)} 封，"
        f"新增 {len(result.archived_uids)} 封，"
        f"已处理 {len(result.duplicate_uids)} 封"
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
    )


@router.get("", response_model=PageResponse[EmailListItem])
def list_emails(
    session: DatabaseSession,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None, max_length=200),
    status: EmailStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> PageResponse[EmailListItem]:
    del user
    if date_from and date_to and date_from > date_to:
        raise AppError("INVALID_DATE_RANGE", "开始日期不能晚于结束日期")

    conditions = []
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
        select(EmailRecord)
        .where(*conditions)
        .order_by(EmailRecord.receive_time.desc(), EmailRecord.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        EmailListItem(
            id=item.id,
            subject=item.subject,
            sender=item.sender,
            receive_time=item.receive_time,
            attachment_count=item.attachment_count,
            status=item.status,
            error_message=item.error_message,
        )
        for item in session.scalars(statement)
    ]
    return PageResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{email_id}", response_model=EmailDetailResponse)
def get_email_detail(
    email_id: int,
    session: DatabaseSession,
    user: CurrentUser,
) -> EmailDetailResponse:
    del user
    email = session.get(EmailRecord, email_id)
    if email is None:
        raise AppError("EMAIL_NOT_FOUND", "邮件记录不存在", status_code=404)

    service = EmailDetailService(get_settings().data_directory)
    try:
        archive_path = service.resolve_archive_path(email.eml_path)
        preview = service.body_preview(archive_path)
    except InvalidEmailArchivePathError as exc:
        raise AppError("EMAIL_ARCHIVE_INVALID", "原始邮件归档路径无效", status_code=409) from exc
    except EmailPreviewTooLargeError:
        archive_path = service.resolve_archive_path(email.eml_path)
        preview_text = "原始邮件较大，正文无法在线预览，请下载 EML 文件查看。"
        return _email_detail_response(email, preview_text, False, archive_path is not None)
    except (OSError, ValueError) as exc:
        raise AppError("EMAIL_PREVIEW_FAILED", "原始邮件正文读取失败", status_code=422) from exc

    return _email_detail_response(
        email,
        preview.text,
        preview.truncated,
        archive_path is not None,
    )


@router.get("/{email_id}/raw", response_class=FileResponse)
def download_raw_email(
    email_id: int,
    session: DatabaseSession,
    user: CurrentUser,
) -> FileResponse:
    del user
    email = session.get(EmailRecord, email_id)
    if email is None:
        raise AppError("EMAIL_NOT_FOUND", "邮件记录不存在", status_code=404)
    try:
        archive_path = EmailDetailService(get_settings().data_directory).resolve_archive_path(
            email.eml_path
        )
    except InvalidEmailArchivePathError as exc:
        raise AppError("EMAIL_ARCHIVE_INVALID", "原始邮件归档路径无效", status_code=409) from exc
    if archive_path is None:
        raise AppError("EMAIL_ARCHIVE_NOT_FOUND", "该邮件没有可下载的原始归档", status_code=404)

    filename = sanitize_filename(f"{email.subject or 'email'}_{email.id}.eml")
    return FileResponse(archive_path, media_type="message/rfc822", filename=filename)


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
