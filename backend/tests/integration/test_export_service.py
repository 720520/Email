from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app.core.config import Settings
from app.db.base import Base
from app.db.models import (
    AttachmentRecord,
    AttachmentStatus,
    EmailRecord,
    EmailStatus,
    ExceptionRecord,
    ExceptionSeverity,
    FundNav,
    JobRun,
    JobStatus,
)
from app.db.session import DatabaseManager
from app.services.export_service import DailyExcelExportService
from app.services.foundation_service import FoundationService


@pytest.fixture
def export_database(tmp_path: Path):
    manager = DatabaseManager(f"sqlite:///{(tmp_path / 'export.db').as_posix()}")
    Base.metadata.create_all(manager.engine)
    with manager.session_factory() as session, session.begin():
        FoundationService(_settings(tmp_path)).ensure(session)
    manager.session_factory.configure(info={"tenant_id": 1, "mailbox_ids": (1,)})
    yield manager
    manager.dispose()


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app={"environment": "test"},
        database={"url": f"sqlite:///{(tmp_path / 'export.db').as_posix()}"},
        logging={"directory": str(tmp_path / "logs")},
        storage={
            "data_directory": str(tmp_path / "data"),
            "archive_timezone": "Asia/Shanghai",
        },
    )


def _seed_export_data(database: DatabaseManager) -> None:
    with database.session_factory() as session, session.begin():
        email = EmailRecord(
            tenant_id=1,
            mailbox_account_id=1,
            mailbox="imap.example.com/INBOX",
            mailbox_key="mailbox-key",
            uid_validity="100",
            message_uid="7",
            subject="基金净值",
            sender="custodian@example.com",
            receive_time=datetime(2026, 7, 24, 9, tzinfo=UTC),
            attachment_count=1,
            status=EmailStatus.PARTIAL_SUCCESS,
        )
        session.add(email)
        session.flush()
        attachment = AttachmentRecord(
            tenant_id=1,
            mailbox_account_id=1,
            email_id=email.id,
            original_name="托管净值.xlsx",
            stored_path="2026/07/24/attachments/托管净值.xlsx",
            sha256="a" * 64,
            file_type="xlsx",
            parse_status=AttachmentStatus.PARTIAL_SUCCESS,
        )
        session.add(attachment)
        session.flush()
        session.add(
            FundNav(
                tenant_id=1,
                mailbox_account_id=1,
                product_name="吉余宸锋金炜幸福一号私募证券投资基金",
                product_code="SAWK26",
                nav_date=date(2026, 7, 24),
                unit_nav=Decimal("1.23456789"),
                total_nav=Decimal("1.34567891"),
                asset_value=Decimal("123456789.1234"),
                source_file="托管净值.xlsx",
                source_sheet="基金净值",
                source_row=6,
                source_type="fund_nav_summary",
                attachment_id=attachment.id,
                create_time=datetime(2026, 7, 24, 9, tzinfo=UTC),
            )
        )
        session.add_all(
            [
                ExceptionRecord(
                    tenant_id=1,
                    mailbox_account_id=1,
                    email_id=email.id,
                    attachment_id=attachment.id,
                    exception_type="duplicate_nav",
                    severity=ExceptionSeverity.ERROR,
                    sheet_name="基金净值",
                    row_number=7,
                    field_name="product_code+nav_date",
                    raw_data={
                        "product_code": "SAWK26",
                        "product_name": "吉余宸锋金炜幸福一号私募证券投资基金",
                    },
                    message="重复净值",
                    create_time=datetime(2026, 7, 24, 10, tzinfo=UTC),
                ),
                ExceptionRecord(
                    tenant_id=1,
                    mailbox_account_id=1,
                    email_id=email.id,
                    attachment_id=attachment.id,
                    exception_type="empty_nav",
                    severity=ExceptionSeverity.ERROR,
                    message="净值为空",
                    create_time=datetime(2026, 7, 23, 10, tzinfo=UTC),
                ),
            ]
        )


def test_export_service_writes_dated_report_and_success_job(
    export_database: DatabaseManager,
    tmp_path: Path,
) -> None:
    _seed_export_data(export_database)
    service = DailyExcelExportService(
        _settings(tmp_path),
        export_database.session_factory,
        tenant_id=1,
        mailbox_ids=(1,),
        clock=lambda: datetime(2026, 7, 24, 12, tzinfo=UTC),
    )

    result = service.export(date(2026, 7, 24))

    assert result.output_path == (
        tmp_path
        / "data/tenants/1/mailboxes/1/2026/07/24/exports/每日基金净值汇总.xlsx"
    )
    assert result.output_path.is_file()
    assert result.nav_count == 1
    assert result.exception_count == 1

    workbook = load_workbook(result.output_path, data_only=False)
    assert workbook["基金净值"]["B6"].value == "SAWK26"
    assert workbook["异常记录"]["B6"].value == "产品重复"
    assert workbook["异常记录"]["F6"].value == "托管净值.xlsx"
    workbook.close()

    with export_database.session_factory() as session:
        job = session.get(JobRun, result.job_run_id)
    assert job.status == JobStatus.SUCCESS
    assert job.finished_at is not None
    assert job.success_count == 1


def test_export_failure_preserves_previous_file_and_marks_job_failed(
    export_database: DatabaseManager,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    output_path = (
        tmp_path
        / "data/tenants/1/mailboxes/1/2026/07/24/exports/每日基金净值汇总.xlsx"
    )
    output_path.parent.mkdir(parents=True)
    output_path.write_bytes(b"previous valid report")

    class FailingBuilder:
        def build(self, **kwargs):
            del kwargs
            raise RuntimeError("simulated workbook failure")

    service = DailyExcelExportService(
        settings,
        export_database.session_factory,
        tenant_id=1,
        mailbox_ids=(1,),
        workbook_builder=FailingBuilder(),
        clock=lambda: datetime(2026, 7, 24, 12, tzinfo=UTC),
    )

    with pytest.raises(RuntimeError, match="simulated workbook failure"):
        service.export(date(2026, 7, 24))

    assert output_path.read_bytes() == b"previous valid report"
    with export_database.session_factory() as session:
        job = session.scalar(select(JobRun))
    assert job.status == JobStatus.FAILED
    assert job.failure_count == 1
    assert "simulated workbook failure" in job.error_message
