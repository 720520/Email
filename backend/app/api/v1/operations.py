"""人工重新解析等运营动作。"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import require_roles
from app.api.schemas.operations import ManualReparseResponse
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import AppUser, UserRole
from app.db.session import get_database_manager
from app.services.manual_reparse_service import ManualReparseService

router = APIRouter()
OperatorUser = Annotated[
    AppUser,
    Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR)),
]


@router.post("/manual-reparse", response_model=ManualReparseResponse)
async def manual_reparse(
    user: OperatorUser,
    file: Annotated[UploadFile, File(description="待重新解析的 .xls 或 .xlsx 文件")],
    source_attachment_id: Annotated[int | None, Form()] = None,
) -> ManualReparseResponse:
    settings = get_settings()
    content = await file.read(settings.email.max_attachment_bytes + 1)
    try:
        result = ManualReparseService(
            settings,
            get_database_manager().session_factory,
        ).process(
            filename=file.filename or "manual-upload.xlsx",
            content=content,
            username=user.username,
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
