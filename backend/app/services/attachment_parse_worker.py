"""数据库驱动的独立 Excel 附件解析 Worker。"""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.credential_security import audit_signing_key
from app.db.models import (
    AttachmentParseTask,
    AttachmentRecord,
    AttachmentStatus,
    JobRun,
    JobStatus,
    JobType,
    TriggerType,
)
from app.db.session import configure_tenant_scope
from app.db.types import utc_now
from app.parsers.service import ExcelParserService
from app.services.attachment_processing_service import AttachmentProcessingService
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ParseTaskCounts:
    queued: int = 0
    running: int = 0
    success: int = 0
    partial_success: int = 0
    duplicate: int = 0
    failed: int = 0


class AttachmentParseWorker:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        *,
        worker_id: str | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.worker_id = worker_id or f"{socket.gethostname()}:{uuid4().hex}"
        self.audit = AuditService(audit_signing_key(settings.security))

    def run_once(self) -> bool:
        claimed = self._claim()
        if claimed is None:
            return False
        task_id, tenant_id, mailbox_id = claimed
        self._process(task_id, tenant_id, mailbox_id)
        return True

    def recover_stale(self) -> int:
        cutoff = utc_now() - timedelta(minutes=self.settings.excel.worker_stale_minutes)
        with self.session_factory() as session, session.begin():
            session.info["skip_tenant_scope"] = True
            stale = list(
                session.scalars(
                    select(AttachmentParseTask).where(
                        AttachmentParseTask.status == "running",
                        AttachmentParseTask.started_at < cutoff,
                    )
                )
            )
            for task in stale:
                stale_job_id = task.parse_job_run_id
                job = session.get(JobRun, stale_job_id) if stale_job_id is not None else None
                if job is not None and job.status == JobStatus.RUNNING:
                    job.status = JobStatus.FAILED
                    job.finished_at = utc_now()
                    job.failure_count = max(job.failure_count, 1)
                    job.error_message = "解析 Worker 超时，任务已回收并重新排队"
                task.status = "queued"
                task.locked_by = None
                task.started_at = None
                task.finished_at = None
                task.parse_job_run_id = None
                task.next_attempt_at = utc_now()
                task.error_message = "Worker 超时，任务已自动恢复"
                attachment = session.get(AttachmentRecord, task.attachment_id)
                if attachment is not None:
                    attachment.parse_status = AttachmentStatus.PENDING
                    attachment.error_message = task.error_message
                self.audit.append(
                    session,
                    tenant_id=task.tenant_id,
                    actor_user_id=None,
                    actor_username="parse-worker",
                    mailbox_account_id=task.mailbox_account_id,
                    action="attachment.parse.recover",
                    resource_type="attachment_parse_task",
                    resource_id=task.id,
                    outcome="queued",
                    detail={"stale_job_id": stale_job_id, "cutoff": cutoff.isoformat()},
                )
            return len(stale)

    def _claim(self) -> tuple[int, int, int] | None:
        now = utc_now()
        with self.session_factory() as session, session.begin():
            session.info["skip_tenant_scope"] = True
            candidate = session.execute(
                select(
                    AttachmentParseTask.id,
                    AttachmentParseTask.tenant_id,
                    AttachmentParseTask.mailbox_account_id,
                )
                .where(
                    AttachmentParseTask.status == "queued",
                    (AttachmentParseTask.next_attempt_at.is_(None))
                    | (AttachmentParseTask.next_attempt_at <= now),
                )
                .order_by(AttachmentParseTask.queued_at, AttachmentParseTask.id)
                .limit(1)
            ).first()
            if candidate is None:
                return None
            claimed = session.execute(
                update(AttachmentParseTask)
                .where(
                    AttachmentParseTask.id == candidate.id,
                    AttachmentParseTask.status == "queued",
                )
                .values(
                    status="running",
                    started_at=now,
                    finished_at=None,
                    locked_by=self.worker_id,
                    attempt_count=AttachmentParseTask.attempt_count + 1,
                    parser_version=self.settings.excel.parser_version,
                    error_message=None,
                )
            )
            if claimed.rowcount != 1:
                return None
            return candidate.id, candidate.tenant_id, candidate.mailbox_account_id

    def _process(self, task_id: int, tenant_id: int, mailbox_id: int) -> None:
        job_id: int | None = None
        try:
            job_id = self._start_job(task_id, tenant_id, mailbox_id)
            result = AttachmentProcessingService(
                self.session_factory,
                data_directory=self.settings.data_directory,
                parser=ExcelParserService(self.settings),
                tenant_id=tenant_id,
                mailbox_account_id=mailbox_id,
            ).process(self._attachment_id(task_id, tenant_id, mailbox_id))
            if result is None:
                raise RuntimeError("附件类型不支持解析")
            self._finish(task_id, job_id, tenant_id, mailbox_id, result)
        except Exception as exc:
            logger.exception("附件解析任务失败", extra={"parse_task_id": task_id})
            self._retry_or_fail(task_id, job_id, tenant_id, mailbox_id, str(exc))

    def _attachment_id(self, task_id: int, tenant_id: int, mailbox_id: int) -> int:
        with self.session_factory() as session:
            configure_tenant_scope(session, tenant_id=tenant_id, mailbox_ids=(mailbox_id,))
            task = session.get(AttachmentParseTask, task_id)
            if task is None:
                raise RuntimeError("解析任务不存在")
            return task.attachment_id

    def _start_job(self, task_id: int, tenant_id: int, mailbox_id: int) -> int:
        with self.session_factory() as session, session.begin():
            configure_tenant_scope(session, tenant_id=tenant_id, mailbox_ids=(mailbox_id,))
            task = session.get(AttachmentParseTask, task_id)
            if task is None:
                raise RuntimeError("解析任务不存在")
            if task.status != "running" or task.locked_by != self.worker_id:
                raise RuntimeError("解析任务锁已失效，停止本次处理")
            trigger = TriggerType.MANUAL if task.trigger_type == "manual" else TriggerType.SCHEDULED
            job = JobRun(
                tenant_id=tenant_id,
                mailbox_account_id=mailbox_id,
                job_type=JobType.ATTACHMENT_REPARSE,
                trigger_type=trigger,
                status=JobStatus.RUNNING,
                started_at=utc_now(),
            )
            session.add(job)
            session.flush()
            task.parse_job_run_id = job.id
            self.audit.append(
                session,
                tenant_id=tenant_id,
                actor_user_id=None,
                actor_username="parse-worker",
                mailbox_account_id=mailbox_id,
                action="attachment.parse.start",
                resource_type="attachment_parse_task",
                resource_id=task.id,
                outcome="started",
                detail={"attachment_id": task.attachment_id, "attempt": task.attempt_count},
            )
            return job.id

    def _finish(self, task_id, job_id, tenant_id, mailbox_id, result) -> None:
        status = result.status.value
        job_status = (
            JobStatus.SUCCESS
            if status == "success"
            else JobStatus.PARTIAL_SUCCESS
            if status in {"partial_success", "duplicate"}
            else JobStatus.FAILED
        )
        with self.session_factory() as session, session.begin():
            configure_tenant_scope(session, tenant_id=tenant_id, mailbox_ids=(mailbox_id,))
            task = session.get(AttachmentParseTask, task_id)
            job = session.get(JobRun, job_id)
            if task is None or job is None:
                raise RuntimeError("解析任务完成状态写入失败")
            if task.status != "running" or task.locked_by != self.worker_id:
                logger.warning(
                    "解析任务锁已被回收，忽略迟到的完成状态",
                    extra={"parse_task_id": task_id, "worker_id": self.worker_id},
                )
                return
            task.status = status
            task.finished_at = utc_now()
            task.locked_by = None
            task.inserted_count = result.inserted_count
            task.duplicate_count = result.duplicate_count
            task.exception_count = result.exception_count
            attachment = session.get(AttachmentRecord, task.attachment_id)
            task.error_message = attachment.error_message if attachment is not None else None
            job.finished_at = task.finished_at
            job.status = job_status
            job.success_count = result.inserted_count
            job.failure_count = (
                0 if job_status == JobStatus.SUCCESS else max(result.exception_count, 1)
            )
            self.audit.append(
                session,
                tenant_id=tenant_id,
                actor_user_id=None,
                actor_username="parse-worker",
                mailbox_account_id=mailbox_id,
                action="attachment.parse.finish",
                resource_type="attachment_parse_task",
                resource_id=task.id,
                outcome=status,
                detail={
                    "inserted_count": result.inserted_count,
                    "duplicate_count": result.duplicate_count,
                    "exception_count": result.exception_count,
                    "parser_version": task.parser_version,
                },
            )

    def _retry_or_fail(
        self,
        task_id: int,
        job_id: int | None,
        tenant_id: int,
        mailbox_id: int,
        message: str,
    ) -> None:
        with self.session_factory() as session, session.begin():
            configure_tenant_scope(session, tenant_id=tenant_id, mailbox_ids=(mailbox_id,))
            task = session.get(AttachmentParseTask, task_id)
            job = session.get(JobRun, job_id) if job_id is not None else None
            if task is None:
                return
            if task.status != "running" or task.locked_by != self.worker_id:
                logger.warning(
                    "解析任务锁已被回收，忽略迟到的失败状态",
                    extra={"parse_task_id": task_id, "worker_id": self.worker_id},
                )
                return
            retry = task.attempt_count < task.max_attempts
            task.status = "queued" if retry else "failed"
            task.next_attempt_at = (
                utc_now() + timedelta(seconds=2 ** max(task.attempt_count - 1, 0))
                if retry
                else None
            )
            task.finished_at = None if retry else utc_now()
            task.locked_by = None
            task.error_message = message[:4000]
            attachment = session.get(AttachmentRecord, task.attachment_id)
            if attachment is not None:
                attachment.parse_status = (
                    AttachmentStatus.PENDING if retry else AttachmentStatus.FAILED
                )
                attachment.error_message = message[:4000]
            if job is not None:
                job.finished_at = utc_now()
                job.status = JobStatus.FAILED
                job.failure_count = 1
                job.error_message = message[:4000]
            self.audit.append(
                session,
                tenant_id=tenant_id,
                actor_user_id=None,
                actor_username="parse-worker",
                mailbox_account_id=mailbox_id,
                action="attachment.parse.retry" if retry else "attachment.parse.finish",
                resource_type="attachment_parse_task",
                resource_id=task.id,
                outcome="queued" if retry else "failed",
                detail={"error": message[:1000], "attempt": task.attempt_count},
            )


def parse_task_counts(session: Session) -> ParseTaskCounts:
    counts = dict(
        session.execute(
            select(AttachmentParseTask.status, func.count(AttachmentParseTask.id)).group_by(
                AttachmentParseTask.status
            )
        ).all()
    )
    return ParseTaskCounts(
        **{field: counts.get(field, 0) for field in ParseTaskCounts.__dataclass_fields__}
    )
