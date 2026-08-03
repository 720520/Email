"""邮件归档与基金净值的事务化持久化服务。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AttachmentRecord,
    AttachmentStatus,
    EmailRecord,
    EmailStatus,
    ExceptionRecord,
    ExceptionSeverity,
    FundNav,
)
from app.email.models import ArchivedEmail, MailboxMessage, ParsedEmail
from app.parsers.models import IssueSeverity, ParseIssue, StandardNavRecord, WorkbookParseResult
from app.repositories import EmailRepository, ExceptionRepository, FundNavRepository

logger = logging.getLogger(__name__)


class AttachmentProcessor(Protocol):
    def process(self, attachment_id: int) -> object: ...


@dataclass(frozen=True, slots=True)
class ArchivePersistenceResult:
    email_id: int
    attachment_ids: tuple[int, ...]
    created: bool


@dataclass(frozen=True, slots=True)
class NavPersistenceResult:
    attachment_id: int
    inserted_count: int
    duplicate_count: int
    exception_count: int
    status: AttachmentStatus


class MailArchivePersistenceService:
    """将一封已归档邮件及其全部附件作为一个事务写入数据库。"""

    def __init__(
        self,
        data_directory: Path,
        *,
        repository: EmailRepository | None = None,
    ) -> None:
        self.data_directory = data_directory.resolve()
        self.repository = repository or EmailRepository()
        self.exception_repository = ExceptionRepository()

    def persist(
        self,
        session: Session,
        *,
        mailbox: str,
        mailbox_key: str,
        uid_validity: str,
        source: MailboxMessage,
        parsed: ParsedEmail,
        archive: ArchivedEmail,
        job_run_id: int | None = None,
    ) -> ArchivePersistenceResult:
        existing = self.repository.find_by_uid(
            session,
            mailbox_key=mailbox_key,
            uid_validity=uid_validity,
            message_uid=str(source.uid),
        )
        if existing is not None:
            attachment_ids = tuple(
                session.scalars(
                    select(AttachmentRecord.id).where(AttachmentRecord.email_id == existing.id)
                )
            )
            return ArchivePersistenceResult(existing.id, attachment_ids, False)

        has_supported_attachment = any(
            item.stored_path.suffix.casefold() in {".xls", ".xlsx"}
            for item in archive.attachments
        )
        email = EmailRecord(
            job_run_id=job_run_id,
            mailbox=mailbox,
            mailbox_key=mailbox_key,
            uid_validity=uid_validity,
            message_uid=str(source.uid),
            message_id=parsed.message_id or None,
            subject=parsed.subject,
            sender=parsed.sender,
            receive_time=parsed.receive_time,
            attachment_count=len(archive.attachments),
            status=(EmailStatus.ARCHIVED if has_supported_attachment else EmailStatus.FAILED),
            error_message=(
                None if has_supported_attachment else "邮件中没有可解析的 Excel 附件"
            ),
            eml_path=self._stored_path(archive.eml_path),
        )
        session.add(email)
        session.flush()

        attachments: list[AttachmentRecord] = []
        for archived_attachment in archive.attachments:
            suffix = archived_attachment.stored_path.suffix.casefold()
            supported = suffix in {".xls", ".xlsx"}
            attachment = AttachmentRecord(
                email_id=email.id,
                original_name=archived_attachment.original_name,
                stored_path=self._stored_path(archived_attachment.stored_path),
                sha256=archived_attachment.sha256,
                file_type=suffix.removeprefix(".") or archived_attachment.content_type,
                parse_status=(
                    AttachmentStatus.ARCHIVED if supported else AttachmentStatus.UNSUPPORTED
                ),
            )
            session.add(attachment)
            attachments.append(attachment)
        if not has_supported_attachment:
            self.exception_repository.add(
                session,
                ExceptionRecord(
                    email_id=email.id,
                    exception_type="no_supported_excel_attachment",
                    severity=ExceptionSeverity.ERROR,
                    raw_data={
                        "attachment_names": [item.original_name for item in archive.attachments]
                    },
                    message="候选净值邮件中没有 .xls 或 .xlsx 附件",
                ),
            )
        session.flush()
        logger.info(
            "邮件归档记录写入数据库",
            extra={"email_id": email.id, "attachment_count": len(attachments)},
        )
        return ArchivePersistenceResult(email.id, tuple(item.id for item in attachments), True)

    def _stored_path(self, path: Path) -> str:
        resolved = path.resolve()
        try:
            return resolved.relative_to(self.data_directory).as_posix()
        except ValueError:
            # 人工上传的临时文件可能位于数据目录外，保留绝对路径供审计。
            return resolved.as_posix()


class NavPersistenceService:
    """保存解析结果；重复净值只登记异常，绝不覆盖历史记录。"""

    def __init__(
        self,
        *,
        nav_repository: FundNavRepository | None = None,
        exception_repository: ExceptionRepository | None = None,
    ) -> None:
        self.nav_repository = nav_repository or FundNavRepository()
        self.exception_repository = exception_repository or ExceptionRepository()

    def persist(
        self,
        session: Session,
        *,
        attachment_id: int,
        result: WorkbookParseResult,
    ) -> NavPersistenceResult:
        """调用方应放在 ``with session.begin()`` 中，保证附件级原子性。"""

        attachment = session.get(AttachmentRecord, attachment_id)
        if attachment is None:
            raise ValueError(f"附件记录不存在: {attachment_id}")
        attachment.parse_status = AttachmentStatus.PARSING
        attachment.error_message = None

        exception_count = 0
        error_count = 0
        for issue in result.issues:
            self._add_parse_issue(session, attachment, issue)
            exception_count += 1
            if issue.severity == IssueSeverity.ERROR:
                error_count += 1

        inserted_count = 0
        duplicate_count = 0
        for record in result.records:
            if (
                record.product_code is None
                or record.product_name is None
                or record.nav_date is None
            ):
                self._add_invalid_standard_record(session, attachment, record)
                exception_count += 1
                error_count += 1
                continue

            # 基金代码统一去空格并转大写，防止大小写差异绕过业务唯一键。
            product_code = record.product_code.strip().upper()
            candidate = FundNav(
                product_name=record.product_name.strip(),
                product_code=product_code,
                nav_date=record.nav_date,
                unit_nav=record.unit_nav,
                total_nav=record.total_nav,
                asset_value=record.asset_value,
                source_file=record.source_file,
                source_sheet=record.source_sheet,
                source_row=record.source_row,
                source_type=record.source_type.value,
                attachment_id=attachment.id,
                create_time=record.create_time,
            )
            insertion = self.nav_repository.insert_if_absent(session, candidate)
            if insertion.inserted:
                inserted_count += 1
                continue

            duplicate_count += 1
            exception_count += 1
            error_count += 1
            self._add_duplicate_issue(session, attachment, record, insertion.record)

        status = self._status(
            inserted_count=inserted_count,
            duplicate_count=duplicate_count,
            error_count=error_count,
        )
        attachment.parse_status = status
        if status in {AttachmentStatus.FAILED, AttachmentStatus.DUPLICATE}:
            attachment.error_message = self._error_summary(
                error_count=error_count,
                duplicate_count=duplicate_count,
            )
        self._refresh_email_status(session, attachment.email_id)
        logger.info(
            "解析结果写入数据库",
            extra={
                "attachment_id": attachment.id,
                "inserted_count": inserted_count,
                "duplicate_count": duplicate_count,
                "exception_count": exception_count,
                "status": status.value,
            },
        )
        return NavPersistenceResult(
            attachment_id=attachment.id,
            inserted_count=inserted_count,
            duplicate_count=duplicate_count,
            exception_count=exception_count,
            status=status,
        )

    def persist_processing_failure(
        self,
        session: Session,
        *,
        attachment_id: int,
        exception_type: str,
        message: str,
        raw_data: dict[str, Any] | None = None,
    ) -> NavPersistenceResult:
        """记录文件缺失、哈希不一致等解析器外部故障。"""

        attachment = session.get(AttachmentRecord, attachment_id)
        if attachment is None:
            raise ValueError(f"附件记录不存在: {attachment_id}")
        self.exception_repository.add(
            session,
            ExceptionRecord(
                email_id=attachment.email_id,
                attachment_id=attachment.id,
                exception_type=exception_type,
                severity=ExceptionSeverity.ERROR,
                raw_data=_json_safe(raw_data),
                message=message,
            ),
        )
        attachment.parse_status = AttachmentStatus.FAILED
        attachment.error_message = message
        self._refresh_email_status(session, attachment.email_id)
        return NavPersistenceResult(
            attachment_id=attachment.id,
            inserted_count=0,
            duplicate_count=0,
            exception_count=1,
            status=AttachmentStatus.FAILED,
        )

    def _add_parse_issue(
        self,
        session: Session,
        attachment: AttachmentRecord,
        issue: ParseIssue,
    ) -> None:
        self.exception_repository.add(
            session,
            ExceptionRecord(
                email_id=attachment.email_id,
                attachment_id=attachment.id,
                exception_type=issue.code.value,
                severity=self._severity(issue.severity),
                sheet_name=issue.sheet_name,
                row_number=issue.row_number,
                field_name=issue.field_name,
                raw_value=None if issue.raw_value is None else str(issue.raw_value),
                raw_data=_json_safe(issue.raw_data),
                message=issue.message,
            ),
        )

    def _add_duplicate_issue(
        self,
        session: Session,
        attachment: AttachmentRecord,
        incoming: StandardNavRecord,
        existing: FundNav,
    ) -> None:
        self.exception_repository.add(
            session,
            ExceptionRecord(
                email_id=attachment.email_id,
                attachment_id=attachment.id,
                exception_type="duplicate_nav",
                severity=ExceptionSeverity.ERROR,
                sheet_name=incoming.source_sheet,
                row_number=incoming.source_row,
                field_name="product_code+nav_date",
                raw_data={
                    "product_code": incoming.product_code,
                    "nav_date": incoming.nav_date.isoformat() if incoming.nav_date else None,
                    "incoming_source_file": incoming.source_file,
                    "existing_nav_id": existing.id,
                    "existing_source_file": existing.source_file,
                },
                message="产品代码和日期已存在，已保留历史记录并拒绝覆盖",
            ),
        )

    def _add_invalid_standard_record(
        self,
        session: Session,
        attachment: AttachmentRecord,
        record: StandardNavRecord,
    ) -> None:
        self.exception_repository.add(
            session,
            ExceptionRecord(
                email_id=attachment.email_id,
                attachment_id=attachment.id,
                exception_type="invalid_standard_record",
                severity=ExceptionSeverity.ERROR,
                sheet_name=record.source_sheet,
                row_number=record.source_row,
                raw_data={
                    "product_code": record.product_code,
                    "product_name": record.product_name,
                    "nav_date": record.nav_date.isoformat() if record.nav_date else None,
                },
                message="标准化记录缺少产品代码、产品名称或净值日期，拒绝入库",
            ),
        )

    @staticmethod
    def _severity(severity: IssueSeverity) -> ExceptionSeverity:
        return (
            ExceptionSeverity.ERROR
            if severity == IssueSeverity.ERROR
            else ExceptionSeverity.WARNING
        )

    @staticmethod
    def _status(
        *,
        inserted_count: int,
        duplicate_count: int,
        error_count: int,
    ) -> AttachmentStatus:
        if inserted_count > 0 and error_count > 0:
            return AttachmentStatus.PARTIAL_SUCCESS
        if inserted_count > 0:
            return AttachmentStatus.SUCCESS
        if duplicate_count > 0 and error_count == duplicate_count:
            return AttachmentStatus.DUPLICATE
        return AttachmentStatus.FAILED

    @staticmethod
    def _error_summary(*, error_count: int, duplicate_count: int) -> str:
        return f"解析未产生新净值：错误 {error_count} 条，其中重复 {duplicate_count} 条"

    @staticmethod
    def _refresh_email_status(session: Session, email_id: int) -> None:
        email = session.get(EmailRecord, email_id)
        if email is None:
            return
        session.flush()
        statuses = set(
            session.scalars(
                select(AttachmentRecord.parse_status).where(
                    AttachmentRecord.email_id == email_id
                )
            )
        )
        if statuses and statuses <= {AttachmentStatus.SUCCESS, AttachmentStatus.UNSUPPORTED}:
            email.status = EmailStatus.SUCCESS
            email.error_message = None
        elif AttachmentStatus.SUCCESS in statuses or AttachmentStatus.PARTIAL_SUCCESS in statuses:
            email.status = EmailStatus.PARTIAL_SUCCESS
        elif statuses and not statuses.intersection(
            {AttachmentStatus.ARCHIVED, AttachmentStatus.PENDING, AttachmentStatus.PARSING}
        ):
            email.status = EmailStatus.FAILED
        else:
            email.status = EmailStatus.PROCESSING


class DatabaseArchiveRecorder:
    """供邮箱同步服务调用的数据库适配器；每封邮件独立提交或回滚。"""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        data_directory: Path,
        mailbox: str,
        job_run_id: int | None = None,
        attachment_processor: AttachmentProcessor | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.mailbox = mailbox
        self.job_run_id = job_run_id
        self.persistence = MailArchivePersistenceService(data_directory)
        self.attachment_processor = attachment_processor

    def record(
        self,
        *,
        mailbox_key: str,
        uid_validity: str,
        source: MailboxMessage,
        parsed: ParsedEmail,
        archive: ArchivedEmail,
    ) -> ArchivePersistenceResult:
        with self.session_factory() as session, session.begin():
            persisted = self.persistence.persist(
                session,
                mailbox=self.mailbox,
                mailbox_key=mailbox_key,
                uid_validity=uid_validity,
                source=source,
                parsed=parsed,
                archive=archive,
                job_run_id=self.job_run_id,
            )
        if self.attachment_processor is not None and persisted.attachment_ids:
            with self.session_factory() as session:
                processable_ids = tuple(
                    session.scalars(
                        select(AttachmentRecord.id).where(
                            AttachmentRecord.id.in_(persisted.attachment_ids),
                            AttachmentRecord.parse_status.in_(
                                {
                                    AttachmentStatus.ARCHIVED,
                                    AttachmentStatus.PENDING,
                                    AttachmentStatus.PARSING,
                                }
                            ),
                        )
                    )
                )
            for attachment_id in processable_ids:
                self.attachment_processor.process(attachment_id)
        return persisted


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (Decimal, Path)):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)
