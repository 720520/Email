"""人工重新解析等运营动作。"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import TenantContext, TenantDatabaseSession, require_roles
from app.api.schemas.operations import ManualReparseResponse
from app.core.config import get_settings
from app.core.credential_security import dedicated_audit_key_configured
from app.core.errors import AppError
from app.db.models import UserRole
from app.db.session import get_database_manager
from app.services.mailbox_account_service import MailboxAccountNotFoundError, MailboxAccountService
from app.services.manual_reparse_service import ManualReparseService

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
        inserted_count=result.inserted_count,
        duplicate_count=result.duplicate_count,
        exception_count=result.exception_count,
        status=result.status.value,
        source_file=result.source_file,
    )
