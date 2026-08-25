"""人工重新解析等运营动作。"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import func, select

from app.api.deps import TenantContext, TenantDatabaseSession, require_roles
from app.api.schemas.operations import (
    ManualReparseResponse,
    ParseCommitResponse,
    ParseReviewRowResponse,
    ParseReviewRowUpdate,
    ParseReviewSessionResponse,
    ParseTaskItem,
    ParseTaskSummaryResponse,
)
from app.core.config import get_settings
from app.core.credential_security import audit_signing_key, dedicated_audit_key_configured
from app.core.errors import AppError
from app.db.models import (
    AttachmentParseTask,
    AttachmentRecord,
    AttachmentStatus,
    MailboxAccount,
    ParseResultRow,
    ParseSession,
    UserRole,
)
from app.db.session import get_database_manager
from app.services.audit_service import AuditService
from app.services.mailbox_account_service import MailboxAccountNotFoundError, MailboxAccountService
from app.services.manual_reparse_service import ManualReparseService
from app.services.parse_review_service import (
    ParseReviewConflictError,
    ParseReviewError,
    ParseReviewService,
)

router = APIRouter()
OperatorScope = Annotated[
    TenantContext,
    Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR)),
]


@router.post("/manual-reparse", response_model=ManualReparseResponse)
async def manual_reparse(
    scope: OperatorScope,
    session: TenantDatabaseSession,
    file: Annotated[UploadFile, File(description="待重新解析的 .xls 或 .xlsx 文件")],
    source_attachment_id: Annotated[int | None, Form()] = None,
    mailbox_account_id: Annotated[int | None, Form()] = None,
) -> ManualReparseResponse:
    settings = get_settings()
    if not dedicated_audit_key_configured(settings.security):
        raise AppError(
            "AUDIT_SECURITY_NOT_READY",
            "请先配置独立审计签名密钥，再执行人工解析",
            status_code=503,
        )
    mailbox_service = MailboxAccountService(settings)
    try:
        if mailbox_account_id is None:
            mailbox = mailbox_service.get_default(
                session,
                tenant_id=scope.tenant_id,
                allowed_mailbox_ids=scope.operable_mailbox_ids,
            )
        else:
            mailbox = mailbox_service.get_account(
                session,
                tenant_id=scope.tenant_id,
                mailbox_account_id=mailbox_account_id,
                allowed_mailbox_ids=scope.operable_mailbox_ids,
                require_enabled=True,
            )
    except MailboxAccountNotFoundError as exc:
        raise AppError("MAILBOX_NOT_AVAILABLE", str(exc), status_code=409) from exc
    content = await file.read(settings.email.max_attachment_bytes + 1)
    try:
        result = ManualReparseService(
            settings,
            get_database_manager().session_factory,
            tenant_id=scope.tenant_id,
            mailbox_account_id=mailbox.id,
            actor_user_id=scope.user.id,
            actor_username=scope.user.username,
        ).process(
            filename=file.filename or "manual-upload.xlsx",
            content=content,
            username=scope.user.username,
            source_attachment_id=source_attachment_id,
        )
    except ValueError as exc:
        raise AppError("MANUAL_REPARSE_INVALID", str(exc)) from exc
    return ManualReparseResponse(
        email_id=result.email_id,
        attachment_id=result.attachment_id,
        parse_session_id=result.parse_session_id,
        inserted_count=result.inserted_count,
        duplicate_count=result.duplicate_count,
        exception_count=result.exception_count,
        valid_count=result.valid_count,
        invalid_count=result.invalid_count,
        status=result.status,
        source_file=result.source_file,
        message=result.message,
        records=[_row_response(item) for item in result.records],
        issues=list(result.issues),
    )


@router.get("/parse-sessions/recent", response_model=list[ParseReviewSessionResponse])
def recent_parse_sessions(
    session: TenantDatabaseSession,
    scope: OperatorScope,
) -> list[ParseReviewSessionResponse]:
    reviews = list(
        session.scalars(
            select(ParseSession)
            .where(ParseSession.mailbox_account_id.in_(scope.operable_mailbox_ids))
            .order_by(ParseSession.update_time.desc())
            .limit(20)
        )
    )
    return [_session_response(session, item, include_rows=False) for item in reviews]


@router.get("/parse-sessions/{parse_session_id}", response_model=ParseReviewSessionResponse)
def get_parse_session(
    parse_session_id: int,
    session: TenantDatabaseSession,
    scope: OperatorScope,
) -> ParseReviewSessionResponse:
    review = _operable_review(session, scope, parse_session_id)
    return _session_response(session, review, include_rows=True)


@router.patch(
    "/parse-sessions/{parse_session_id}/rows/{row_id}",
    response_model=ParseReviewSessionResponse,
)
def update_parse_result_row(
    parse_session_id: int,
    row_id: int,
    payload: ParseReviewRowUpdate,
    session: TenantDatabaseSession,
    scope: OperatorScope,
) -> ParseReviewSessionResponse:
    review = _operable_review(session, scope, parse_session_id)
    service = _review_service(scope, review.mailbox_account_id)
    excluded = {"ignored", "conflict_action", "edit_reason", "expected_version"}
    values = payload.model_dump(exclude_unset=True, exclude=excluded)
    try:
        service.update_row(
            parse_session_id=parse_session_id,
            row_id=row_id,
            values=values,
            ignored=payload.ignored if "ignored" in payload.model_fields_set else None,
            conflict_action=(
                payload.conflict_action if "conflict_action" in payload.model_fields_set else None
            ),
            edit_reason=payload.edit_reason,
            expected_version=payload.expected_version,
        )
        updated, rows = service.get_session(parse_session_id)
    except ParseReviewConflictError as exc:
        raise AppError("PARSE_REVIEW_CONFLICT", str(exc), status_code=409) from exc
    except ParseReviewError as exc:
        raise AppError("PARSE_REVIEW_INVALID", str(exc)) from exc
    return _detached_session_response(
        updated, rows, _attachment_name(session, updated.attachment_id)
    )


@router.post(
    "/parse-sessions/{parse_session_id}/validate",
    response_model=ParseReviewSessionResponse,
)
def validate_parse_session(
    parse_session_id: int,
    session: TenantDatabaseSession,
    scope: OperatorScope,
) -> ParseReviewSessionResponse:
    review = _operable_review(session, scope, parse_session_id)
    service = _review_service(scope, review.mailbox_account_id)
    try:
        updated, rows = service.validate(parse_session_id)
    except ParseReviewError as exc:
        raise AppError("PARSE_REVIEW_INVALID", str(exc), status_code=409) from exc
    return _detached_session_response(
        updated, rows, _attachment_name(session, updated.attachment_id)
    )


@router.post(
    "/parse-sessions/{parse_session_id}/confirm",
    response_model=ParseCommitResponse,
)
def confirm_parse_session(
    parse_session_id: int,
    session: TenantDatabaseSession,
    scope: OperatorScope,
) -> ParseCommitResponse:
    review = _operable_review(session, scope, parse_session_id)
    try:
        result = _review_service(scope, review.mailbox_account_id).confirm(
            parse_session_id,
            role=scope.role,
        )
    except ParseReviewConflictError as exc:
        raise AppError("PARSE_REVIEW_CONFLICT", str(exc), status_code=409) from exc
    except ParseReviewError as exc:
        raise AppError("PARSE_REVIEW_INVALID", str(exc)) from exc
    return ParseCommitResponse(
        parse_session_id=parse_session_id,
        status=result.status.value,
        inserted_count=result.inserted_count,
        duplicate_count=result.duplicate_count,
        exception_count=result.exception_count,
        message=(
            "人工修正结果已确认并写入正式净值台账"
            if result.status == AttachmentStatus.SUCCESS
            else "确认完成，请检查重复或异常记录"
        ),
    )


@router.get("/parse-tasks/summary", response_model=ParseTaskSummaryResponse)
def parse_task_summary(
    session: TenantDatabaseSession,
    scope: OperatorScope,
) -> ParseTaskSummaryResponse:
    counts = dict(
        session.execute(
            select(AttachmentParseTask.status, func.count(AttachmentParseTask.id))
            .where(AttachmentParseTask.mailbox_account_id.in_(scope.operable_mailbox_ids))
            .group_by(AttachmentParseTask.status)
        ).all()
    )
    recent_rows = session.execute(
        select(AttachmentParseTask, AttachmentRecord.original_name, MailboxAccount.display_name)
        .join(AttachmentRecord, AttachmentRecord.id == AttachmentParseTask.attachment_id)
        .join(MailboxAccount, MailboxAccount.id == AttachmentParseTask.mailbox_account_id)
        .where(AttachmentParseTask.mailbox_account_id.in_(scope.operable_mailbox_ids))
        .order_by(AttachmentParseTask.update_time.desc())
        .limit(20)
    ).all()
    return ParseTaskSummaryResponse(
        **{
            name: counts.get(name, 0)
            for name in ("queued", "running", "success", "partial_success", "duplicate", "failed")
        },
        recent=[
            ParseTaskItem(
                id=task.id,
                attachment_id=task.attachment_id,
                source_file=source_file,
                mailbox_name=mailbox_name,
                status=task.status,
                attempt_count=task.attempt_count,
                max_attempts=task.max_attempts,
                parser_version=task.parser_version,
                inserted_count=task.inserted_count,
                duplicate_count=task.duplicate_count,
                exception_count=task.exception_count,
                error_message=task.error_message,
                queued_at=task.queued_at,
                started_at=task.started_at,
                finished_at=task.finished_at,
            )
            for task, source_file, mailbox_name in recent_rows
        ],
    )


@router.post("/parse-tasks/{task_id}/retry", response_model=ParseTaskItem)
def retry_parse_task(
    task_id: int,
    session: TenantDatabaseSession,
    scope: OperatorScope,
) -> ParseTaskItem:
    task = session.get(AttachmentParseTask, task_id)
    if task is None:
        raise AppError("PARSE_TASK_NOT_FOUND", "解析任务不存在", status_code=404)
    if task.mailbox_account_id not in scope.operable_mailbox_ids:
        raise AppError("FORBIDDEN", "当前账号没有操作该邮箱的权限", status_code=403)
    if task.status in {"queued", "running"}:
        raise AppError("PARSE_TASK_RUNNING", "任务已经在队列中或正在运行", status_code=409)
    task.status = "queued"
    task.trigger_type = "manual"
    task.attempt_count = 0
    task.next_attempt_at = None
    task.started_at = task.finished_at = None
    task.locked_by = None
    task.error_message = None
    attachment = session.get(AttachmentRecord, task.attachment_id)
    if attachment is None:
        raise AppError("ATTACHMENT_NOT_FOUND", "附件记录不存在", status_code=404)
    attachment.parse_status = AttachmentStatus.PENDING
    attachment.error_message = None
    AuditService(audit_signing_key(get_settings().security)).append(
        session,
        tenant_id=scope.tenant_id,
        actor_user_id=scope.user.id,
        actor_username=scope.user.username,
        mailbox_account_id=task.mailbox_account_id,
        action="attachment.parse.retry.request",
        resource_type="attachment_parse_task",
        resource_id=task.id,
        outcome="queued",
        detail={"attachment_id": attachment.id},
    )
    session.commit()
    mailbox_name = (
        session.scalar(
            select(MailboxAccount.display_name).where(MailboxAccount.id == task.mailbox_account_id)
        )
        or "—"
    )
    return ParseTaskItem(
        id=task.id,
        attachment_id=task.attachment_id,
        source_file=attachment.original_name,
        mailbox_name=mailbox_name,
        status=task.status,
        attempt_count=task.attempt_count,
        max_attempts=task.max_attempts,
        parser_version=task.parser_version,
        inserted_count=task.inserted_count,
        duplicate_count=task.duplicate_count,
        exception_count=task.exception_count,
        error_message=task.error_message,
        queued_at=task.queued_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
    )


def _operable_review(session, scope, parse_session_id: int) -> ParseSession:
    review = session.get(ParseSession, parse_session_id)
    if review is None:
        raise AppError("PARSE_SESSION_NOT_FOUND", "解析会话不存在", status_code=404)
    if review.mailbox_account_id not in scope.operable_mailbox_ids:
        raise AppError("FORBIDDEN", "当前账号没有操作该邮箱的权限", status_code=403)
    return review


def _review_service(scope, mailbox_account_id: int) -> ParseReviewService:
    return ParseReviewService(
        get_settings(),
        get_database_manager().session_factory,
        tenant_id=scope.tenant_id,
        mailbox_account_id=mailbox_account_id,
        actor_user_id=scope.user.id,
        actor_username=scope.user.username,
    )


def _attachment_name(session, attachment_id: int) -> str:
    return (
        session.scalar(
            select(AttachmentRecord.original_name).where(AttachmentRecord.id == attachment_id)
        )
        or "—"
    )


def _session_response(
    session, review: ParseSession, *, include_rows: bool
) -> ParseReviewSessionResponse:
    rows = (
        tuple(
            session.scalars(
                select(ParseResultRow)
                .where(ParseResultRow.parse_session_id == review.id)
                .order_by(ParseResultRow.source_sheet, ParseResultRow.source_row, ParseResultRow.id)
            )
        )
        if include_rows
        else ()
    )
    return _detached_session_response(review, rows, _attachment_name(session, review.attachment_id))


def _detached_session_response(review, rows, source_file: str) -> ParseReviewSessionResponse:
    return ParseReviewSessionResponse(
        id=review.id,
        attachment_id=review.attachment_id,
        source_attachment_id=review.source_attachment_id,
        status=review.status,
        parser_version=review.parser_version,
        source_file=source_file,
        row_count=review.row_count,
        valid_count=review.valid_count,
        invalid_count=review.invalid_count,
        ignored_count=review.ignored_count,
        duplicate_count=review.duplicate_count,
        inserted_count=review.inserted_count,
        error_message=review.error_message,
        create_time=review.create_time,
        update_time=review.update_time,
        confirmed_at=review.confirmed_at,
        file_issues=review.file_issues,
        rows=[_row_response(row) for row in rows],
    )


def _row_response(item) -> ParseReviewRowResponse:
    decimal_fields = {
        "unit_nav",
        "total_nav",
        "asset_value",
        "asset_share",
        "paid_in_capital",
        "holding_shares",
        "reference_market_value",
        "total_assets",
        "total_assets_nav_ratio",
        "parent_unit_nav",
        "parent_total_nav",
        "parent_asset_value",
        "parent_paid_in_capital",
    }
    payload = {
        name: (None if getattr(item, name) is None else str(getattr(item, name)))
        for name in decimal_fields
    }
    return ParseReviewRowResponse(
        **payload,
        id=item.id,
        status=item.status,
        source_sheet=item.source_sheet,
        source_row=item.source_row,
        source_type=item.source_type,
        product_name=item.product_name,
        product_code=item.product_code,
        asset_code=item.asset_code,
        registration_code=item.registration_code,
        share_class=item.share_class,
        nav_date=item.nav_date,
        investor_name=item.investor_name,
        investor_account=item.investor_account,
        parent_product_code=item.parent_product_code,
        parent_product_name=item.parent_product_name,
        notes=item.notes,
        investment_manager_info=item.investment_manager_info,
        investment_strategy_info=item.investment_strategy_info,
        issues=item.issues,
        original_data=item.original_data,
        validation_message=item.validation_message,
        is_edited=item.is_edited,
        edit_reason=item.edit_reason,
        row_version=item.row_version,
        conflict_action=item.conflict_action,
        existing_nav_id=item.existing_nav_id,
        committed_nav_id=item.committed_nav_id,
    )
