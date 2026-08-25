from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db.base import Base
from app.db.models import (
    AttachmentRecord,
    AttachmentStatus,
    EmailRecord,
    EmailStatus,
    ExceptionRecord,
    FundNav,
    FundProduct,
    MailboxAccount,
    Tenant,
)
from app.db.session import DatabaseManager
from app.email.models import (
    ArchivedAttachment,
    ArchivedEmail,
    MailboxMessage,
    ParsedEmail,
)
from app.parsers.models import (
    IssueCode,
    IssueSeverity,
    ParsedNavRow,
    ParseIssue,
    StandardNavRecord,
    WorkbookParseResult,
    WorkbookType,
)
from app.services.attachment_processing_service import AttachmentProcessingService
from app.services.persistence_service import (
    MailArchivePersistenceService,
    NavPersistenceService,
)


@pytest.fixture
def database(tmp_path: Path):
    manager = DatabaseManager(f"sqlite:///{(tmp_path / 'persistence.db').as_posix()}")
    Base.metadata.create_all(manager.engine)
    with manager.session_factory() as session, session.begin():
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
    manager.session_factory.configure(info={"tenant_id": 1, "mailbox_ids": (1,)})
    yield manager
    manager.dispose()


def _create_attachment(
    database: DatabaseManager,
    *,
    stored_path: str,
    sha256: str = "a" * 64,
) -> int:
    with database.session_factory() as session, session.begin():
        email = EmailRecord(
            tenant_id=1,
            mailbox_account_id=1,
            mailbox="imap.example.com/INBOX",
            mailbox_key="mailbox-key",
            uid_validity="100",
            message_uid=stored_path,
            subject="基金净值",
            sender="custodian@example.com",
            receive_time=datetime(2026, 7, 24, 10, tzinfo=UTC),
            attachment_count=1,
            status=EmailStatus.ARCHIVED,
        )
        session.add(email)
        session.flush()
        attachment = AttachmentRecord(
            tenant_id=1,
            mailbox_account_id=1,
            email_id=email.id,
            original_name=Path(stored_path).name,
            stored_path=stored_path,
            sha256=sha256,
            file_type="xlsx",
            parse_status=AttachmentStatus.ARCHIVED,
        )
        session.add(attachment)
        session.flush()
        return attachment.id


def _nav_record(
    *,
    source_file: str,
    product_code: str = "sawk26",
    unit_nav: str = "1.23456789",
    nav_date: date = date(2026, 7, 24),
) -> StandardNavRecord:
    return StandardNavRecord(
        product_name="吉余宸锋金炜幸福一号私募证券投资基金",
        product_code=product_code,
        nav_date=nav_date,
        unit_nav=Decimal(unit_nav),
        total_nav=Decimal("1.34567891"),
        asset_value=Decimal("123456789.1234"),
        source_file=source_file,
        source_sheet="基金净值",
        source_row=5,
        source_type=WorkbookType.FUND_NAV_SUMMARY,
        create_time=datetime(2026, 7, 24, 10, tzinfo=UTC),
    )


def _parse_result(path: Path, *records: StandardNavRecord) -> WorkbookParseResult:
    return WorkbookParseResult(
        source_path=path,
        rows=[ParsedNavRow(record=record) for record in records],
    )


def test_duplicate_nav_keeps_first_history_and_creates_exception(
    database: DatabaseManager,
    tmp_path: Path,
) -> None:
    first_attachment_id = _create_attachment(database, stored_path="first.xlsx")
    second_attachment_id = _create_attachment(database, stored_path="second.xlsx")
    service = NavPersistenceService()

    with database.session_factory() as session, session.begin():
        first = service.persist(
            session,
            attachment_id=first_attachment_id,
            result=_parse_result(
                tmp_path / "first.xlsx",
                replace(
                    _nav_record(source_file="first.xlsx"),
                    investment_manager_info="首次附件经理信息",
                ),
            ),
        )
    with database.session_factory() as session, session.begin():
        duplicate = service.persist(
            session,
            attachment_id=second_attachment_id,
            result=_parse_result(
                tmp_path / "second.xlsx",
                replace(
                    _nav_record(
                        source_file="second.xlsx",
                        product_code="SAWK26",
                        unit_nav="9.9",
                    ),
                    investment_manager_info="重复附件不应覆盖",
                ),
            ),
        )

    with database.session_factory() as session:
        nav_records = list(session.scalars(select(FundNav)))
        duplicate_issue = session.scalar(
            select(ExceptionRecord).where(ExceptionRecord.exception_type == "duplicate_nav")
        )
        first_attachment = session.get(AttachmentRecord, first_attachment_id)
        second_attachment = session.get(AttachmentRecord, second_attachment_id)
        product = session.scalar(select(FundProduct))

    assert first.inserted_count == 1
    assert duplicate.duplicate_count == 1
    assert len(nav_records) == 1
    assert nav_records[0].product_code == "SAWK26"
    assert nav_records[0].unit_nav == Decimal("1.23456789")
    assert nav_records[0].source_file == "first.xlsx"
    assert duplicate_issue is not None
    assert duplicate_issue.raw_data["existing_nav_id"] == nav_records[0].id
    assert first_attachment.parse_status == AttachmentStatus.SUCCESS
    assert second_attachment.parse_status == AttachmentStatus.DUPLICATE
    assert product.source_investment_manager_info == "首次附件经理信息"


def test_different_nav_dates_are_kept_as_history(
    database: DatabaseManager,
    tmp_path: Path,
) -> None:
    attachment_id = _create_attachment(database, stored_path="history.xlsx")
    service = NavPersistenceService()
    records = (
        _nav_record(source_file="history.xlsx", nav_date=date(2026, 7, 23)),
        _nav_record(source_file="history.xlsx", nav_date=date(2026, 7, 24)),
    )

    with database.session_factory() as session, session.begin():
        result = service.persist(
            session,
            attachment_id=attachment_id,
            result=_parse_result(tmp_path / "history.xlsx", *records),
        )

    with database.session_factory() as session:
        count = session.scalar(select(func.count()).select_from(FundNav))
    assert result.inserted_count == 2
    assert count == 2


def test_partial_success_keeps_actionable_error_summary(
    database: DatabaseManager,
    tmp_path: Path,
) -> None:
    attachment_id = _create_attachment(database, stored_path="partial.xlsx")
    service = NavPersistenceService()
    valid = _nav_record(source_file="partial.xlsx")
    invalid = replace(
        _nav_record(source_file="partial.xlsx", nav_date=date(2026, 7, 25)),
        product_code=None,
    )

    with database.session_factory() as session, session.begin():
        result = service.persist(
            session,
            attachment_id=attachment_id,
            result=_parse_result(tmp_path / "partial.xlsx", valid, invalid),
        )

    with database.session_factory() as session:
        attachment = session.get(AttachmentRecord, attachment_id)
    assert result.status == AttachmentStatus.PARTIAL_SUCCESS
    assert result.inserted_count == 1
    assert result.exception_count == 1
    assert attachment.error_message == "部分解析成功：新增 1 条，错误 1 条，其中重复 0 条"


def test_product_elements_create_master_and_daily_snapshot(
    database: DatabaseManager,
    tmp_path: Path,
) -> None:
    attachment_id = _create_attachment(database, stored_path="elements.xlsx")
    record = replace(
        _nav_record(source_file="elements.xlsx", product_code="T08604(B级)"),
        asset_code="T08604(B级)",
        registration_code="SAVH33",
        share_class="B类",
        paid_in_capital=Decimal("9000000.12"),
        total_assets=Decimal("10010000.34"),
        total_assets_nav_ratio=Decimal("1.001"),
        parent_product_code="SAVH33",
        parent_product_name="吉余牡丹私募证券投资基金",
        investment_manager_info="附件经理信息",
        investment_strategy_info="附件策略信息",
    )

    with database.session_factory() as session, session.begin():
        result = NavPersistenceService().persist(
            session,
            attachment_id=attachment_id,
            result=_parse_result(tmp_path / "elements.xlsx", record),
        )

    with database.session_factory() as session:
        nav = session.scalar(select(FundNav))
        product = session.scalar(select(FundProduct))

    assert result.inserted_count == 1
    assert nav is not None
    assert nav.product_code == "T08604(B级)"
    assert nav.master_product_code == "SAVH33"
    assert nav.registration_code == "SAVH33"
    assert nav.paid_in_capital == Decimal("9000000.1200")
    assert nav.total_assets_nav_ratio == Decimal("1.00100000")
    assert product is not None
    assert product.product_code == "SAVH33"
    assert product.product_name == "吉余牡丹私募证券投资基金"
    assert product.investment_manager_info == "附件经理信息"


def test_parser_issue_is_persisted_with_source_location(
    database: DatabaseManager,
    tmp_path: Path,
) -> None:
    attachment_id = _create_attachment(database, stored_path="invalid.xlsx")
    issue = ParseIssue(
        code=IssueCode.INVALID_NUMBER,
        severity=IssueSeverity.ERROR,
        message="数值格式无效",
        source_file="invalid.xlsx",
        sheet_name="Sheet2",
        row_number=17,
        field_name="unit_nav",
        raw_value="--",
        raw_data={"单位净值": Decimal("0")},
    )
    parse_result = WorkbookParseResult(
        source_path=tmp_path / "invalid.xlsx",
        issues=[issue],
    )

    with database.session_factory() as session, session.begin():
        persisted = NavPersistenceService().persist(
            session,
            attachment_id=attachment_id,
            result=parse_result,
        )

    with database.session_factory() as session:
        saved = session.scalar(select(ExceptionRecord))
    assert persisted.status == AttachmentStatus.FAILED
    assert saved.sheet_name == "Sheet2"
    assert saved.row_number == 17
    assert saved.field_name == "unit_nav"
    assert saved.raw_data == {"单位净值": "0"}


def test_attachment_transaction_rolls_back_all_changes(
    database: DatabaseManager,
    tmp_path: Path,
) -> None:
    attachment_id = _create_attachment(database, stored_path="rollback.xlsx")

    with pytest.raises(RuntimeError, match="simulate failure"):
        with database.session_factory() as session, session.begin():
            NavPersistenceService().persist(
                session,
                attachment_id=attachment_id,
                result=_parse_result(
                    tmp_path / "rollback.xlsx",
                    _nav_record(source_file="rollback.xlsx"),
                ),
            )
            raise RuntimeError("simulate failure")

    with database.session_factory() as session:
        nav_count = session.scalar(select(func.count()).select_from(FundNav))
        exception_count = session.scalar(select(func.count()).select_from(ExceptionRecord))
        attachment = session.get(AttachmentRecord, attachment_id)
    assert nav_count == 0
    assert exception_count == 0
    assert attachment.parse_status == AttachmentStatus.ARCHIVED


def test_attachment_processor_verifies_hash_then_persists(
    database: DatabaseManager,
    tmp_path: Path,
) -> None:
    data_directory = tmp_path / "data"
    data_directory.mkdir()
    attachment_path = data_directory / "archived.xlsx"
    content = b"immutable archived workbook"
    attachment_path.write_bytes(content)
    attachment_id = _create_attachment(
        database,
        stored_path="archived.xlsx",
        sha256=hashlib.sha256(content).hexdigest(),
    )
    parse_result = _parse_result(
        attachment_path,
        _nav_record(source_file="archived.xlsx"),
    )

    class FakeParser:
        def parse_file(self, source_path):
            assert Path(source_path) == attachment_path.resolve()
            return parse_result

    processor = AttachmentProcessingService(
        database.session_factory,
        data_directory=data_directory,
        parser=FakeParser(),
        tenant_id=1,
        mailbox_account_id=1,
    )
    result = processor.process(attachment_id)

    with database.session_factory() as session:
        nav_count = session.scalar(select(func.count()).select_from(FundNav))
    assert result is not None
    assert result.status == AttachmentStatus.SUCCESS
    assert nav_count == 1


def test_mail_archive_persistence_is_idempotent_and_stores_utc(
    database: DatabaseManager,
    tmp_path: Path,
) -> None:
    data_directory = tmp_path / "data"
    archive = ArchivedEmail(
        uid=7,
        eml_path=data_directory / "2026/07/24/emails/mail_7.eml",
        manifest_path=data_directory / "2026/07/24/emails/mail_7.json",
        attachments=(
            ArchivedAttachment(
                original_name="净值.xlsx",
                stored_path=data_directory / "2026/07/24/attachments/mail_7_净值.xlsx",
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                size=128,
                sha256="b" * 64,
            ),
        ),
    )
    source = MailboxMessage(
        uid=7,
        internal_date=datetime(2026, 7, 24, 10, tzinfo=UTC),
        raw_message=b"raw",
    )
    parsed = ParsedEmail(
        subject="基金净值",
        sender="custodian@example.com",
        receive_time=datetime(2026, 7, 24, 10, tzinfo=UTC),
        message_id="<7@example.com>",
        attachments=(),
    )
    service = MailArchivePersistenceService(
        data_directory,
        tenant_id=1,
        mailbox_account_id=1,
    )

    with database.session_factory() as session, session.begin():
        first = service.persist(
            session,
            mailbox="imap.example.com/INBOX",
            mailbox_key="mailbox-key",
            uid_validity="999",
            source=source,
            parsed=parsed,
            archive=archive,
        )
    with database.session_factory() as session, session.begin():
        second = service.persist(
            session,
            mailbox="imap.example.com/INBOX",
            mailbox_key="mailbox-key",
            uid_validity="999",
            source=source,
            parsed=parsed,
            archive=archive,
        )

    with database.session_factory() as session:
        email_count = session.scalar(select(func.count()).select_from(EmailRecord))
        attachment_count = session.scalar(select(func.count()).select_from(AttachmentRecord))
        saved_email = session.get(EmailRecord, first.email_id)
    assert first.created is True
    assert second.created is False
    assert first.email_id == second.email_id
    assert email_count == 1
    assert attachment_count == 1
    assert saved_email.eml_path == "2026/07/24/emails/mail_7.eml"
    assert saved_email.receive_time.tzinfo is UTC


def test_mail_without_excel_is_failed_and_audited(
    database: DatabaseManager,
    tmp_path: Path,
) -> None:
    data_directory = tmp_path / "data"
    archive = ArchivedEmail(
        uid=8,
        eml_path=data_directory / "mail_8.eml",
        manifest_path=data_directory / "mail_8.json",
        attachments=(),
    )
    source = MailboxMessage(
        uid=8,
        internal_date=datetime(2026, 7, 24, 10, tzinfo=UTC),
        raw_message=b"raw",
    )
    parsed = ParsedEmail(
        subject="基金净值",
        sender="custodian@example.com",
        receive_time=datetime(2026, 7, 24, 10, tzinfo=UTC),
        message_id="<8@example.com>",
        attachments=(),
    )

    with database.session_factory() as session, session.begin():
        saved = MailArchivePersistenceService(
            data_directory,
            tenant_id=1,
            mailbox_account_id=1,
        ).persist(
            session,
            mailbox="imap.example.com/INBOX",
            mailbox_key="mailbox-key",
            uid_validity="999",
            source=source,
            parsed=parsed,
            archive=archive,
        )

    with database.session_factory() as session:
        email = session.get(EmailRecord, saved.email_id)
        issue = session.scalar(select(ExceptionRecord))
    assert email.status == EmailStatus.FAILED
    assert issue.exception_type == "no_supported_excel_attachment"
