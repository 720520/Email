"""统一编排网页、命令行和后续定时任务的邮箱同步。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.models import JobRun, JobStatus, JobType, TriggerType
from app.email.models import EmailSyncResult
from app.parsers.service import ExcelParserService
from app.services.attachment_processing_service import AttachmentProcessingService
from app.services.email_service import EmailSyncService
from app.services.persistence_service import DatabaseArchiveRecorder

logger = logging.getLogger(__name__)
_MAIL_SYNC_LOCK = Lock()


class MailSyncAlreadyRunningError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MailSyncExecution:
    job_run_id: int
    result: EmailSyncResult


class MailSyncRunner:
    """保证单进程内同步任务互斥，并写入 job_run 审计记录。"""

    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory

    def run(self, *, trigger_type: TriggerType) -> MailSyncExecution:
        if not _MAIL_SYNC_LOCK.acquire(blocking=False):
            raise MailSyncAlreadyRunningError("已有邮箱同步任务正在执行")
        job_run_id: int | None = None
        try:
            job_run_id = self._start_job(trigger_type)
            result = self._build_service(job_run_id).sync()
            self._finish_job(job_run_id, result)
            return MailSyncExecution(job_run_id=job_run_id, result=result)
        except Exception as exc:
            if job_run_id is not None:
                self._fail_job(job_run_id, str(exc))
            logger.exception("邮箱同步任务异常终止", extra={"job_run_id": job_run_id})
            raise
        finally:
            _MAIL_SYNC_LOCK.release()

    def _build_service(self, job_run_id: int) -> EmailSyncService:
        attachment_processor = AttachmentProcessingService(
            self.session_factory,
            data_directory=self.settings.data_directory,
            parser=ExcelParserService(self.settings),
        )
        recorder = DatabaseArchiveRecorder(
            self.session_factory,
            data_directory=self.settings.data_directory,
            mailbox=f"{self.settings.email.host}/{self.settings.email.folder}",
            job_run_id=job_run_id,
            attachment_processor=attachment_processor,
        )
        return EmailSyncService(self.settings, archive_recorder=recorder)

    def _start_job(self, trigger_type: TriggerType) -> int:
        with self.session_factory() as session, session.begin():
            job = JobRun(
                job_type=JobType.MAIL_SYNC,
                trigger_type=trigger_type,
                status=JobStatus.RUNNING,
                started_at=datetime.now(UTC),
            )
            session.add(job)
            session.flush()
            return job.id

    def _finish_job(self, job_run_id: int, result: EmailSyncResult) -> None:
        failure_count = len(result.failed_uids) + (1 if result.fatal_error else 0)
        if failure_count and result.archived_uids:
            status = JobStatus.PARTIAL_SUCCESS
        elif failure_count:
            status = JobStatus.FAILED
        else:
            status = JobStatus.SUCCESS
        with self.session_factory() as session, session.begin():
            job = session.get(JobRun, job_run_id)
            if job is None:
                raise RuntimeError("邮箱同步任务记录不存在")
            job.finished_at = datetime.now(UTC)
            job.status = status
            job.emails_found = len(result.discovered_uids)
            job.success_count = len(result.archived_uids)
            job.failure_count = failure_count
            messages = [item.message for item in result.errors]
            job.error_message = (result.fatal_error or "; ".join(messages) or None)
            if job.error_message:
                job.error_message = job.error_message[:4000]

    def _fail_job(self, job_run_id: int, message: str) -> None:
        try:
            with self.session_factory() as session, session.begin():
                job = session.get(JobRun, job_run_id)
                if job is not None:
                    job.finished_at = datetime.now(UTC)
                    job.status = JobStatus.FAILED
                    job.failure_count = 1
                    job.error_message = message[:4000]
        except Exception:
            logger.critical("邮箱同步任务失败状态回写失败", exc_info=True)
