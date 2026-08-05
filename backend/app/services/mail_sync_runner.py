"""统一编排网页、命令行和后续定时任务的邮箱同步。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import EmailSettings, Settings
from app.core.credential_security import audit_signing_key
from app.db.models import JobRun, JobStatus, JobType, MailboxAccount, TriggerType
from app.db.session import configure_tenant_scope
from app.email.models import EmailSyncResult
from app.email.uid_registry import FileUidRegistry
from app.parsers.service import ExcelParserService
from app.services.archive_service import EmailArchiveService
from app.services.attachment_processing_service import AttachmentProcessingService
from app.services.audit_service import AuditService
from app.services.email_service import EmailSyncService
from app.services.persistence_service import DatabaseArchiveRecorder

logger = logging.getLogger(__name__)
_MAIL_SYNC_LOCKS_GUARD = Lock()
_MAIL_SYNC_LOCKS: dict[int, Lock] = {}


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
        *,
        tenant_id: int,
        mailbox_account_id: int,
        email_settings: EmailSettings,
        actor_user_id: int | None = None,
        actor_username: str = "system",
    ) -> None:
        self.settings = settings
        self.runtime_settings = settings.model_copy(update={"email": email_settings})
        self.session_factory = session_factory
        self.tenant_id = tenant_id
        self.mailbox_account_id = mailbox_account_id
        self.actor_user_id = actor_user_id
        self.actor_username = actor_username
        self.audit = AuditService(audit_signing_key(settings.security))

    def run(self, *, trigger_type: TriggerType) -> MailSyncExecution:
        lock = _mailbox_lock(self.mailbox_account_id)
        if not lock.acquire(blocking=False):
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
            lock.release()

    def _build_service(self, job_run_id: int) -> EmailSyncService:
        attachment_processor = AttachmentProcessingService(
            self.session_factory,
            data_directory=self.settings.data_directory,
            parser=ExcelParserService(self.runtime_settings),
            tenant_id=self.tenant_id,
            mailbox_account_id=self.mailbox_account_id,
        )
        recorder = DatabaseArchiveRecorder(
            self.session_factory,
            data_directory=self.settings.data_directory,
            mailbox=f"{self.runtime_settings.email.host}/{self.runtime_settings.email.folder}",
            tenant_id=self.tenant_id,
            mailbox_account_id=self.mailbox_account_id,
            job_run_id=job_run_id,
            attachment_processor=attachment_processor,
        )
        scoped_root = (
            self.settings.data_directory
            / "tenants"
            / str(self.tenant_id)
            / "mailboxes"
            / str(self.mailbox_account_id)
        )
        return EmailSyncService(
            self.runtime_settings,
            archive_recorder=recorder,
            archive_service=EmailArchiveService(
                self.settings.data_directory,
                archive_timezone=self.settings.storage.archive_timezone,
                max_attachment_bytes=self.runtime_settings.email.max_attachment_bytes,
                tenant_id=self.tenant_id,
                mailbox_account_id=self.mailbox_account_id,
            ),
            uid_registry=FileUidRegistry(
                scoped_root / ".email_uid_state",
                stale_seconds=self.runtime_settings.email.uid_reservation_stale_seconds,
            ),
        )

    def _start_job(self, trigger_type: TriggerType) -> int:
        with self.session_factory() as session, session.begin():
            configure_tenant_scope(
                session,
                tenant_id=self.tenant_id,
                mailbox_ids=(self.mailbox_account_id,),
            )
            job = JobRun(
                tenant_id=self.tenant_id,
                mailbox_account_id=self.mailbox_account_id,
                triggered_by_user_id=self.actor_user_id,
                job_type=JobType.MAIL_SYNC,
                trigger_type=trigger_type,
                status=JobStatus.RUNNING,
                started_at=datetime.now(UTC),
            )
            session.add(job)
            session.flush()
            self.audit.append(
                session,
                tenant_id=self.tenant_id,
                actor_user_id=self.actor_user_id,
                actor_username=self.actor_username,
                mailbox_account_id=self.mailbox_account_id,
                action="mail.sync.start",
                resource_type="job_run",
                resource_id=job.id,
                outcome="started",
                detail={"trigger_type": trigger_type.value},
            )
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
            configure_tenant_scope(
                session,
                tenant_id=self.tenant_id,
                mailbox_ids=(self.mailbox_account_id,),
            )
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
            mailbox = self._mailbox_account(session)
            mailbox.last_sync_status = status.value
            mailbox.last_sync_at = job.finished_at
            self.audit.append(
                session,
                tenant_id=self.tenant_id,
                actor_user_id=self.actor_user_id,
                actor_username=self.actor_username,
                mailbox_account_id=self.mailbox_account_id,
                action="mail.sync.finish",
                resource_type="job_run",
                resource_id=job.id,
                outcome=status.value,
                detail={
                    "emails_found": job.emails_found,
                    "success_count": job.success_count,
                    "failure_count": job.failure_count,
                },
            )

    def _fail_job(self, job_run_id: int, message: str) -> None:
        try:
            with self.session_factory() as session, session.begin():
                configure_tenant_scope(
                    session,
                    tenant_id=self.tenant_id,
                    mailbox_ids=(self.mailbox_account_id,),
                )
                job = session.get(JobRun, job_run_id)
                if job is not None:
                    job.finished_at = datetime.now(UTC)
                    job.status = JobStatus.FAILED
                    job.failure_count = 1
                    job.error_message = message[:4000]
                    mailbox = self._mailbox_account(session)
                    mailbox.last_sync_status = JobStatus.FAILED.value
                    mailbox.last_sync_at = job.finished_at
                    self.audit.append(
                        session,
                        tenant_id=self.tenant_id,
                        actor_user_id=self.actor_user_id,
                        actor_username=self.actor_username,
                        mailbox_account_id=self.mailbox_account_id,
                        action="mail.sync.finish",
                        resource_type="job_run",
                        resource_id=job.id,
                        outcome="failed",
                        detail={"error": message[:1000]},
                    )
        except Exception:
            logger.critical("邮箱同步任务失败状态回写失败", exc_info=True)

    def _mailbox_account(self, session: Session) -> MailboxAccount:
        """显式校验租户，防止任务状态被回写到其他租户的同名资源。"""

        mailbox = session.scalar(
            select(MailboxAccount).where(
                MailboxAccount.id == self.mailbox_account_id,
                MailboxAccount.tenant_id == self.tenant_id,
            )
        )
        if mailbox is None:
            raise RuntimeError("邮箱账户不存在或租户不匹配")
        return mailbox


def _mailbox_lock(mailbox_account_id: int) -> Lock:
    with _MAIL_SYNC_LOCKS_GUARD:
        return _MAIL_SYNC_LOCKS.setdefault(mailbox_account_id, Lock())
