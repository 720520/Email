from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.base import Base
from app.db.models import (
    AppUser,
    AttachmentRecord,
    FundNav,
    JobRun,
    JobStatus,
    MailboxAccount,
    Tenant,
    UserRole,
)
from app.db.session import DatabaseManager
from app.services.manual_reparse_service import ManualReparseService


def _workbook_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "基金净值"
    sheet.append(["产品代码", "产品名称", "估值基准日", "单位净值", "累计净值", "资产净值"])
    sheet.append(["JYUPLOAD01", "吉余人工上传一号", date(2026, 7, 29), 1.1234, 1.2345, 5000000])
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


def test_manual_upload_is_archived_parsed_and_audited(tmp_path: Path) -> None:
    database = DatabaseManager(f"sqlite:///{(tmp_path / 'manual.db').as_posix()}")
    Base.metadata.create_all(database.engine)
    settings = Settings(
        app={"environment": "test"},
        database={"url": f"sqlite:///{(tmp_path / 'manual.db').as_posix()}"},
        storage={"data_directory": str(tmp_path / "data")},
    )
    with database.session_factory() as session, session.begin():
        session.info["skip_tenant_scope"] = True
        session.add(Tenant(id=1, code="tenant-1", name="Tenant 1"))
        session.add(
            MailboxAccount(
                id=1,
                tenant_id=1,
                display_name="Mailbox 1",
                host="imap.example.com",
                username="ops@example.com",
                is_default=True,
            )
        )
        session.add(
            AppUser(
                id=1,
                username="operator",
                password_hash="test-only",
                role=UserRole.OPERATOR,
                is_active=True,
            )
        )
    database.session_factory.configure(info={"tenant_id": 1, "mailbox_ids": (1,)})

    result = ManualReparseService(
        settings,
        database.session_factory,
        tenant_id=1,
        mailbox_account_id=1,
        actor_user_id=1,
        actor_username="operator",
    ).process(
        filename="人工修正净值.xlsx",
        content=_workbook_bytes(),
        username="operator",
    )

    with database.session_factory() as session:
        nav = session.scalar(select(FundNav))
        attachment = session.get(AttachmentRecord, result.attachment_id)
        job = session.scalar(select(JobRun))
        nav_count = session.scalar(select(func.count()).select_from(FundNav))
    assert result.inserted_count == 1
    assert nav_count == 1
    assert nav.product_code == "JYUPLOAD01"
    assert attachment.original_name == "人工修正净值.xlsx"
    assert (settings.data_directory / attachment.stored_path).is_file()
    assert job.status == JobStatus.SUCCESS
    database.dispose()
