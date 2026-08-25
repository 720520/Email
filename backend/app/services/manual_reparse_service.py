"""人工上传 Excel 并重新解析。"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.credential_security import audit_signing_key
from app.core.files import atomic_write_bytes
from app.db.models import (
    AttachmentRecord,
    AttachmentStatus,
    EmailRecord,
    EmailStatus,
    JobRun,
    JobStatus,
    JobType,
    TriggerType,
)
from app.db.session import configure_tenant_scope
from app.parsers.service import ExcelParserService
from app.services.archive_service import sanitize_filename
from app.services.audit_service import AuditService
from app.services.parse_review_service import ParseReviewService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ManualReparseResult:
    email_id: int
    attachment_id: int
    parse_session_id: int
    inserted_count: int
    duplicate_count: int
    exception_count: int
    valid_count: int
    invalid_count: int
    status: str
    source_file: str
    message: str
    records: tuple[object, ...]
    issues: tuple[dict, ...]


class ManualReparseService:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        *,
        tenant_id: int,
        mailbox_account_id: int,
        actor_user_id: int,
        actor_username: str,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.tenant_id = tenant_id
        self.mailbox_account_id = mailbox_account_id
        self.actor_user_id = actor_user_id
        self.actor_username = actor_username
        self.audit = AuditService(audit_signing_key(settings.security))
        self.timezone = ZoneInfo(settings.storage.archive_timezone)
        self.parser = ExcelParserService(settings)

    def process(
        self,
        *,
        filename: str,
        content: bytes,
        username: str,
        source_attachment_id: int | None = None,
    ) -> ManualReparseResult:
        if len(filename) > 500:
            raise ValueError("文件名过长，请缩短至 500 个字符以内")
        suffix = Path(filename).suffix.casefold()
        if suffix not in {".xls", ".xlsx"}:
            raise ValueError("只支持 .xls 或 .xlsx 文件")
        if not content:
            raise ValueError("上传文件为空")
        if len(content) > self.settings.email.max_attachment_bytes:
            raise ValueError("上传文件超过配置的附件大小限制")
        if source_attachment_id is not None:
            with self.session_factory() as session:
                self._scope(session)
                if session.get(AttachmentRecord, source_attachment_id) is None:
                    raise ValueError("原附件记录不存在")

        now = datetime.now(UTC)
        local_date = now.astimezone(self.timezone).date()
        operation_id = uuid4().hex
        safe_name = sanitize_filename(filename)
        stored_path = (
            self.settings.data_directory
            / "tenants"
            / str(self.tenant_id)
            / "mailboxes"
            / str(self.mailbox_account_id)
            / f"{local_date.year:04d}"
            / f"{local_date.month:02d}"
            / f"{local_date.day:02d}"
            / "attachments"
            / f"manual_{operation_id}_{safe_name}"
        )
        job_run_id = self._start_job(now)
        file_created = False
        try:
            atomic_write_bytes(stored_path, content)
            file_created = True
            email_id, attachment_id = self._create_records(
                job_run_id=job_run_id,
                operation_id=operation_id,
                filename=filename,
                stored_path=stored_path,
                content=content,
                username=username,
                now=now,
                source_attachment_id=source_attachment_id,
            )
            parse_result = self.parser.parse_file(stored_path)
            review_service = ParseReviewService(
                self.settings,
                self.session_factory,
                tenant_id=self.tenant_id,
                mailbox_account_id=self.mailbox_account_id,
                actor_user_id=self.actor_user_id,
                actor_username=self.actor_username,
            )
            parse_session_id = review_service.create_session(
                attachment_id=attachment_id,
                source_attachment_id=source_attachment_id,
                result=parse_result,
            )
            review, records = review_service.get_session(parse_session_id)
            issues = tuple(review.file_issues) + tuple(
                issue
                for row in records
                for issue in row.issues
            )
            self._finish_review_job(job_run_id, review.status, review.row_count)
            return ManualReparseResult(
                email_id=email_id,
                attachment_id=attachment_id,
                parse_session_id=parse_session_id,
                inserted_count=0,
                duplicate_count=review.duplicate_count,
                exception_count=len(issues),
                valid_count=review.valid_count,
                invalid_count=review.invalid_count,
                status=review.status,
                source_file=filename,
                message=self._result_message(review.status),
                records=records,
                issues=issues,
            )
        except Exception as exc:
            self._mark_job_failed(job_run_id, str(exc))
            if file_created and not self._has_attachment_record(stored_path):
                stored_path.unlink(missing_ok=True)
            logger.exception("人工重新解析失败", extra={"job_run_id": job_run_id})
            raise

    def _start_job(self, now: datetime) -> int:
        with self.session_factory() as session, session.begin():
            self._scope(session)
            job = JobRun(
                tenant_id=self.tenant_id,
                mailbox_account_id=self.mailbox_account_id,
                triggered_by_user_id=self.actor_user_id,
                job_type=JobType.MANUAL_UPLOAD,
                trigger_type=TriggerType.MANUAL,
                status=JobStatus.RUNNING,
                started_at=now,
            )
            session.add(job)
            session.flush()
            self.audit.append(
                session,
                tenant_id=self.tenant_id,
                actor_user_id=self.actor_user_id,
                actor_username=self.actor_username,
                mailbox_account_id=self.mailbox_account_id,
                action="attachment.reparse.start",
                resource_type="job_run",
                resource_id=job.id,
                outcome="started",
            )
            return job.id

    def _create_records(
        self,
        *,
        job_run_id: int,
        operation_id: str,
        filename: str,
        stored_path: Path,
        content: bytes,
        username: str,
        now: datetime,
        source_attachment_id: int | None,
    ) -> tuple[int, int]:
        subject = f"人工重新解析：{filename}"
        if source_attachment_id is not None:
            subject = f"{subject}（替代附件 #{source_attachment_id}）"
        with self.session_factory() as session, session.begin():
            self._scope(session)
            email = EmailRecord(
                tenant_id=self.tenant_id,
                mailbox_account_id=self.mailbox_account_id,
                job_run_id=job_run_id,
                mailbox="manual-upload",
                mailbox_key="manual-upload",
                uid_validity="1",
                message_uid=operation_id,
                subject=subject,
                sender=username,
                receive_time=now,
                attachment_count=1,
                status=EmailStatus.ARCHIVED,
            )
            session.add(email)
            session.flush()
            attachment = AttachmentRecord(
                tenant_id=self.tenant_id,
                mailbox_account_id=self.mailbox_account_id,
                email_id=email.id,
                original_name=filename,
                stored_path=stored_path.relative_to(self.settings.data_directory).as_posix(),
                sha256=hashlib.sha256(content).hexdigest(),
                file_type=stored_path.suffix.casefold().removeprefix("."),
                parse_status=AttachmentStatus.ARCHIVED,
            )
            session.add(attachment)
            session.flush()
            return email.id, attachment.id

    def _finish_review_job(self, job_run_id: int, status: str, row_count: int) -> None:
        successful = status in {"ready", "review_required"}
        with self.session_factory() as session, session.begin():
            self._scope(session)
            job = session.get(JobRun, job_run_id)
            if job is None:
                raise RuntimeError("人工解析任务记录不存在")
            job.finished_at = datetime.now(UTC)
            job.status = JobStatus.SUCCESS if successful else JobStatus.PARTIAL_SUCCESS
            job.success_count = row_count
            job.failure_count = 0 if successful else 1
            self.audit.append(
                session,
                tenant_id=self.tenant_id,
                actor_user_id=self.actor_user_id,
                actor_username=self.actor_username,
                mailbox_account_id=self.mailbox_account_id,
                action="attachment.reparse.finish",
                resource_type="job_run",
                resource_id=job.id,
                outcome=status,
                detail={"staged_row_count": row_count, "awaiting_confirmation": True},
            )

    def _mark_job_failed(self, job_run_id: int, message: str) -> None:
        try:
            with self.session_factory() as session, session.begin():
                self._scope(session)
                job = session.get(JobRun, job_run_id)
                if job is not None:
                    job.finished_at = datetime.now(UTC)
                    job.status = JobStatus.FAILED
                    job.failure_count = 1
                    job.error_message = message[:4000]
                    self.audit.append(
                        session,
                        tenant_id=self.tenant_id,
                        actor_user_id=self.actor_user_id,
                        actor_username=self.actor_username,
                        mailbox_account_id=self.mailbox_account_id,
                        action="attachment.reparse.finish",
                        resource_type="job_run",
                        resource_id=job.id,
                        outcome="failed",
                        detail={"error": message[:1000]},
                    )
        except Exception:
            logger.critical("人工解析任务失败状态回写失败", exc_info=True)

    def _has_attachment_record(self, stored_path: Path) -> bool:
        relative_path = stored_path.relative_to(self.settings.data_directory).as_posix()
        with self.session_factory() as session:
            self._scope(session)
            return (
                session.scalar(
                    select(AttachmentRecord.id).where(
                        AttachmentRecord.stored_path == relative_path
                    )
                )
                is not None
            )

    def _scope(self, session: Session) -> None:
        configure_tenant_scope(
            session,
            tenant_id=self.tenant_id,
            mailbox_ids=(self.mailbox_account_id,),
        )

    @staticmethod
    def _result_message(status: str) -> str:
        return {
            "ready": "解析完成，请核对后确认入库",
            "review_required": "解析完成，存在重复数据，请选择处理方式",
            "invalid": "解析完成，但存在需要人工修正的数据",
        }.get(status, "解析完成，等待人工复核")
