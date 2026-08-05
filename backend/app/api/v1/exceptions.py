"""运营异常查询与处理状态更新。"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select

from app.api.deps import (
    TenantContext,
    TenantDatabaseSession,
    TenantScope,
    require_roles,
)
from app.api.schemas.common import PageResponse
from app.api.schemas.operations import ExceptionListItem, ExceptionStatusUpdate
from app.core.config import get_settings
from app.core.credential_security import audit_signing_key
from app.core.errors import AppError
from app.db.models import (
    AttachmentRecord,
    EmailRecord,
    ExceptionRecord,
    ExceptionSeverity,
    ExceptionStatus,
    MailboxAccount,
    UserRole,
)
from app.domain.exception_categories import (
    exception_category,
    exception_types_for_category,
    known_exception_types,
)
from app.services.audit_service import AuditService

router = APIRouter()
OperatorScope = Annotated[
    TenantContext,
    Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR)),
]


@router.get("", response_model=PageResponse[ExceptionListItem])
def list_exceptions(
    session: TenantDatabaseSession,
    scope: TenantScope,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category: str | None = Query(default=None, max_length=50),
    severity: ExceptionSeverity | None = None,
    status: ExceptionStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    mailbox_account_id: int | None = Query(default=None, ge=1),
) -> PageResponse[ExceptionListItem]:
    if date_from and date_to and date_from > date_to:
        raise AppError("INVALID_DATE_RANGE", "开始日期不能晚于结束日期")
    conditions = []
    if mailbox_account_id is not None:
        if mailbox_account_id not in scope.mailbox_ids:
            raise AppError("FORBIDDEN", "当前账号没有查看该邮箱的权限", status_code=403)
        conditions.append(ExceptionRecord.mailbox_account_id == mailbox_account_id)
    if severity is not None:
        conditions.append(ExceptionRecord.severity == severity)
    if status is not None:
        conditions.append(ExceptionRecord.status == status)
    start_time, end_time = _date_bounds(date_from, date_to)
    if start_time is not None:
        conditions.append(ExceptionRecord.create_time >= start_time)
    if end_time is not None:
        conditions.append(ExceptionRecord.create_time < end_time)

    count_statement = select(func.count(ExceptionRecord.id)).where(*conditions)
    if category:
        type_values = exception_types_for_category(category)
        if category == "其他异常":
            conditions.append(ExceptionRecord.exception_type.not_in(known_exception_types()))
        elif type_values:
            conditions.append(ExceptionRecord.exception_type.in_(type_values))
        else:
            return PageResponse(items=[], total=0, page=page, page_size=page_size)
        count_statement = select(func.count(ExceptionRecord.id)).where(*conditions)
    total = session.scalar(count_statement) or 0

    statement = (
        select(
            ExceptionRecord,
            AttachmentRecord.original_name,
            EmailRecord.subject,
            MailboxAccount.display_name,
        )
        .outerjoin(
            AttachmentRecord,
            ExceptionRecord.attachment_id == AttachmentRecord.id,
        )
        .outerjoin(EmailRecord, ExceptionRecord.email_id == EmailRecord.id)
        .join(MailboxAccount, MailboxAccount.id == ExceptionRecord.mailbox_account_id)
        .where(*conditions)
        .order_by(ExceptionRecord.create_time.desc(), ExceptionRecord.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        _exception_item(exception, attachment_name, subject, mailbox_name)
        for exception, attachment_name, subject, mailbox_name in session.execute(statement)
    ]
    return PageResponse(items=items, total=total, page=page, page_size=page_size)


@router.patch("/{exception_id}/status", response_model=ExceptionListItem)
def update_exception_status(
    exception_id: int,
    payload: ExceptionStatusUpdate,
    request: Request,
    session: TenantDatabaseSession,
    scope: OperatorScope,
) -> ExceptionListItem:
    exception = session.get(ExceptionRecord, exception_id)
    if exception is None:
        raise AppError("EXCEPTION_NOT_FOUND", "异常记录不存在", status_code=404)
    if not scope.can_operate(exception.mailbox_account_id):
        raise AppError("FORBIDDEN", "当前账号没有处置该邮箱异常的权限", status_code=403)
    exception.status = payload.status
    exception.resolved_time = None if payload.status == ExceptionStatus.OPEN else datetime.now(UTC)
    AuditService(audit_signing_key(get_settings().security)).append(
        session,
        tenant_id=scope.tenant_id,
        actor_user_id=scope.user.id,
        actor_username=scope.user.username,
        mailbox_account_id=exception.mailbox_account_id,
        action="exception.status.update",
        resource_type="exception_record",
        resource_id=exception.id,
        outcome="success",
        detail={"new_status": payload.status.value},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    session.commit()
    session.refresh(exception)
    attachment_name = None
    subject = None
    if exception.attachment_id:
        attachment = session.get(AttachmentRecord, exception.attachment_id)
        attachment_name = attachment.original_name if attachment else None
    if exception.email_id:
        email = session.get(EmailRecord, exception.email_id)
        subject = email.subject if email else None
    mailbox = session.scalar(
        select(MailboxAccount).where(
            MailboxAccount.id == exception.mailbox_account_id,
            MailboxAccount.tenant_id == scope.tenant_id,
        )
    )
    return _exception_item(
        exception,
        attachment_name,
        subject,
        mailbox.display_name if mailbox else "未知邮箱",
    )


def _exception_item(
    exception: ExceptionRecord,
    attachment_name: str | None,
    subject: str | None,
    mailbox_name: str,
) -> ExceptionListItem:
    raw_data = exception.raw_data if isinstance(exception.raw_data, dict) else {}
    return ExceptionListItem(
        id=exception.id,
        mailbox_account_id=exception.mailbox_account_id,
        mailbox_name=mailbox_name,
        email_id=exception.email_id,
        category=exception_category(exception.exception_type),
        exception_type=exception.exception_type,
        severity=exception.severity,
        product_code=_raw_text(raw_data, "product_code"),
        product_name=_raw_text(raw_data, "product_name"),
        source=attachment_name or subject or "系统",
        sheet_name=exception.sheet_name,
        row_number=exception.row_number,
        field_name=exception.field_name,
        raw_value=exception.raw_value,
        message=exception.message,
        status=exception.status,
        create_time=exception.create_time,
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


def _raw_text(raw_data: dict[str, object], key: str) -> str | None:
    value = raw_data.get(key)
    return None if value is None else str(value)
