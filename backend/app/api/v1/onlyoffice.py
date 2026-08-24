"""Document Server 文件读取及编辑结果保存回调。"""

import hashlib
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import APIRouter
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.api.deps import DatabaseSession
from app.core.config import get_settings
from app.core.credential_security import audit_signing_key
from app.core.errors import AppError
from app.core.files import atomic_write_bytes
from app.db.models import ReportFileVersion, ReportRun
from app.services.audit_service import AuditService
from app.services.onlyoffice_service import OnlyOfficeService, OnlyOfficeTokenError

router = APIRouter()


@router.get("/files/{token}")
def get_onlyoffice_file(token: str, session: DatabaseSession) -> FileResponse:
    settings = get_settings()
    service = OnlyOfficeService(settings.onlyoffice)
    try:
        claims = service.verify_file_token(token)
        tenant_id = int(claims["tenant_id"])
        run_id = int(claims["run_id"])
        version_id = int(claims["version_id"])
    except (OnlyOfficeTokenError, KeyError, TypeError, ValueError) as exc:
        raise AppError(
            "ONLYOFFICE_FILE_TOKEN_INVALID",
            "OnlyOffice 文件链接无效或已过期",
            status_code=401,
        ) from exc

    session.info["skip_tenant_scope"] = True
    run = session.get(ReportRun, run_id)
    version = session.get(ReportFileVersion, version_id)
    if (
        run is None
        or version is None
        or run.tenant_id != tenant_id
        or version.tenant_id != tenant_id
        or version.report_run_id != run.id
        or run.current_version_id != version.id
        or run.status != "success"
    ):
        raise AppError("ONLYOFFICE_FILE_NOT_FOUND", "OnlyOffice 报表文件不存在", status_code=404)
    path = settings.data_directory / version.stored_path
    root = settings.data_directory.resolve()
    path = path.resolve()
    if root not in path.parents or not path.is_file():
        raise AppError("ONLYOFFICE_FILE_NOT_FOUND", "OnlyOffice 报表文件已丢失", status_code=404)
    if path.stat().st_size > settings.onlyoffice.max_download_bytes:
        raise AppError(
            "ONLYOFFICE_FILE_TOO_LARGE", "OnlyOffice 报表文件超过大小限制", status_code=413
        )
    return FileResponse(
        path,
        filename=version.filename,
        media_type=("application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        content_disposition_type="inline",
    )


@router.post("/callbacks/{token}")
async def save_onlyoffice_callback(
    token: str,
    payload: dict[str, Any],
    session: DatabaseSession,
) -> dict[str, int]:
    """接收 Document Server 保存通知，并追加一个不可变 PPTX 文件版本。"""

    settings = get_settings()
    service = OnlyOfficeService(settings.onlyoffice)
    try:
        claims = service.verify_callback_token(token)
        tenant_id = int(claims["tenant_id"])
        run_id = int(claims["run_id"])
        user_id = int(claims["user_id"])
        username = str(claims["username"])
    except (OnlyOfficeTokenError, KeyError, TypeError, ValueError) as exc:
        raise AppError(
            "ONLYOFFICE_CALLBACK_TOKEN_INVALID",
            "OnlyOffice 保存回调无效或已过期",
            status_code=401,
        ) from exc

    status = int(payload.get("status", 0))
    if status not in (2, 6):
        return {"error": 0}
    download_url = payload.get("url")
    if not isinstance(download_url, str) or not download_url:
        return {"error": 1}

    session.info["skip_tenant_scope"] = True
    run = session.get(ReportRun, run_id)
    if run is None or run.tenant_id != tenant_id or run.status != "success":
        return {"error": 1}
    try:
        content = _download_edited_pptx(download_url)
    except (ValueError, HTTPError, URLError, TimeoutError, OSError):
        return {"error": 1}

    digest = hashlib.sha256(content).hexdigest()
    current = session.get(ReportFileVersion, run.current_version_id) if run.current_version_id else None
    if current is not None and current.content_hash == digest:
        return {"error": 0}

    next_version = (
        session.scalar(
            select(func.max(ReportFileVersion.version)).where(
                ReportFileVersion.report_run_id == run.id
            )
        )
        or 0
    ) + 1
    filename = run.output_filename or (current.filename if current else f"report-{run.id}.pptx")
    relative_path = (
        Path("tenants")
        / str(tenant_id)
        / "reporting"
        / "exports"
        / f"{run.report_date.year:04d}"
        / f"{run.report_date.month:02d}"
        / str(run.id)
        / f"v{next_version}_{uuid.uuid4().hex[:8]}_{filename}"
    )
    atomic_write_bytes(settings.data_directory / relative_path, content)
    version = ReportFileVersion(
        tenant_id=tenant_id,
        report_run_id=run.id,
        version=next_version,
        source="onlyoffice",
        filename=filename,
        stored_path=relative_path.as_posix(),
        content_hash=digest,
        file_size=len(content),
        created_by_user_id=user_id,
    )
    session.add(version)
    session.flush()
    run.current_version_id = version.id
    run.output_path = version.stored_path
    AuditService(audit_signing_key(settings.security)).append(
        session,
        tenant_id=tenant_id,
        actor_user_id=user_id,
        actor_username=username,
        action="report.onlyoffice.save",
        resource_type="report_file_version",
        resource_id=version.id,
        outcome="success",
        detail={
            "run_id": run.id,
            "version": version.version,
            "sha256": digest,
            "callback_status": status,
        },
        user_agent="ONLYOFFICE Document Server",
    )
    session.commit()
    return {"error": 0}


def _download_edited_pptx(url: str) -> bytes:
    settings = get_settings()
    parsed = urlparse(url)
    allowed_origins = {
        (item.scheme, item.hostname, item.port)
        for item in (
            urlparse(settings.onlyoffice.public_url),
            urlparse(settings.onlyoffice.internal_url),
        )
    }
    if parsed.scheme not in ("http", "https") or (
        parsed.scheme,
        parsed.hostname,
        parsed.port,
    ) not in allowed_origins:
        raise ValueError("OnlyOffice 回调下载地址不受信任")
    request = Request(url, headers={"User-Agent": "fund-nav-onlyoffice-save/1.0"})
    limit = settings.onlyoffice.max_download_bytes
    with urlopen(request, timeout=settings.onlyoffice.request_timeout) as response:
        content = response.read(limit + 1)
    if len(content) > limit:
        raise ValueError("OnlyOffice 编辑文件超过大小限制")
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            if "ppt/presentation.xml" not in archive.namelist():
                raise ValueError("OnlyOffice 保存结果不是 PPTX")
    except zipfile.BadZipFile as exc:
        raise ValueError("OnlyOffice 保存结果不是 PPTX") from exc
    return content
