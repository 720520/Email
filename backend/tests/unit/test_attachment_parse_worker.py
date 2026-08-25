from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from app.core.config import Settings
from app.db.base import Base
from app.db.models import (
    AttachmentParseTask,
    AttachmentRecord,
    AttachmentStatus,
    EmailRecord,
    EmailStatus,
    JobRun,
    JobStatus,
    JobType,
    MailboxAccount,
    Tenant,
    TriggerType,
)
from app.db.session import DatabaseManager
from app.db.types import utc_now
from app.services.attachment_parse_worker import AttachmentParseWorker


@pytest.fixture
def worker_context(tmp_path: Path):
    manager = DatabaseManager(f"sqlite:///{(tmp_path / 'worker.db').as_posix()}")
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
    settings = Settings(
        app={"environment": "test"},
        database={"url": f"sqlite:///{(tmp_path / 'worker.db').as_posix()}"},
        logging={"directory": str(tmp_path / "logs")},
        storage={"data_directory": str(tmp_path / "data")},
        excel={"worker_stale_minutes": 15, "worker_max_attempts": 2},
    )
    yield manager, settings
    manager.dispose()


def _create_task(
    manager: DatabaseManager,
    *,
    status: str = "queued",
    max_attempts: int = 2,
) -> tuple[int, int]:
    with manager.session_factory() as session, session.begin():
        email = EmailRecord(
            tenant_id=1,
            mailbox_account_id=1,
            mailbox="INBOX",
            mailbox_key="mailbox-key",
            uid_validity="1",
            message_uid=f"uid-{utc_now().timestamp()}",
            subject="基金净值",
            sender="custodian@example.com",
            receive_time=utc_now(),
            attachment_count=1,
            status=EmailStatus.PROCESSING,
        )
        session.add(email)
        session.flush()
        attachment = AttachmentRecord(
            tenant_id=1,
            mailbox_account_id=1,
            email_id=email.id,
            original_name="missing.xlsx",
            stored_path="missing.xlsx",
            sha256="a" * 64,
            file_type="xlsx",
            parse_status=(
                AttachmentStatus.PARSING if status == "running" else AttachmentStatus.PENDING
            ),
        )
        session.add(attachment)
        session.flush()
        task = AttachmentParseTask(
            tenant_id=1,
            mailbox_account_id=1,
            attachment_id=attachment.id,
            status=status,
            trigger_type="mail_sync",
            max_attempts=max_attempts,
        )
        session.add(task)
        session.flush()
        return task.id, attachment.id


def test_worker_records_deterministic_attachment_failure(worker_context) -> None:
    manager, settings = worker_context
    task_id, attachment_id = _create_task(manager)

    assert AttachmentParseWorker(settings, manager.session_factory, worker_id="worker-a").run_once()

    with manager.session_factory() as session:
        task = session.get(AttachmentParseTask, task_id)
        attachment = session.get(AttachmentRecord, attachment_id)
        job = session.get(JobRun, task.parse_job_run_id)
        assert task.status == "failed"
        assert task.attempt_count == 1
        assert task.locked_by is None
        assert "归档附件不存在" in task.error_message
        assert attachment.parse_status == AttachmentStatus.FAILED
        assert job.status == JobStatus.FAILED
        assert job.failure_count == 1


def test_worker_runtime_failure_retries_then_stops(worker_context, monkeypatch) -> None:
    manager, settings = worker_context
    task_id, _ = _create_task(manager, max_attempts=2)

    def fail_process(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("temporary parser failure")

    monkeypatch.setattr(
        "app.services.attachment_parse_worker.AttachmentProcessingService.process",
        fail_process,
    )
    worker = AttachmentParseWorker(settings, manager.session_factory, worker_id="worker-a")

    assert worker.run_once()
    with manager.session_factory() as session, session.begin():
        task = session.get(AttachmentParseTask, task_id)
        assert task.status == "queued"
        assert task.attempt_count == 1
        assert task.next_attempt_at is not None
        task.next_attempt_at = None

    assert worker.run_once()
    with manager.session_factory() as session:
        task = session.get(AttachmentParseTask, task_id)
        assert task.status == "failed"
        assert task.attempt_count == 2
        assert task.finished_at is not None
        assert task.error_message == "temporary parser failure"


def test_recover_stale_task_closes_orphan_job(worker_context) -> None:
    manager, settings = worker_context
    task_id, attachment_id = _create_task(manager, status="running")
    with manager.session_factory() as session, session.begin():
        task = session.get(AttachmentParseTask, task_id)
        job = JobRun(
            tenant_id=1,
            mailbox_account_id=1,
            job_type=JobType.ATTACHMENT_REPARSE,
            trigger_type=TriggerType.SCHEDULED,
            status=JobStatus.RUNNING,
            started_at=utc_now() - timedelta(minutes=60),
        )
        session.add(job)
        session.flush()
        task.parse_job_run_id = job.id
        task.locked_by = "dead-worker"
        task.started_at = utc_now() - timedelta(minutes=60)
        orphan_job_id = job.id

    worker = AttachmentParseWorker(settings, manager.session_factory, worker_id="worker-b")
    assert worker.recover_stale() == 1

    with manager.session_factory() as session:
        task = session.get(AttachmentParseTask, task_id)
        attachment = session.get(AttachmentRecord, attachment_id)
        job = session.get(JobRun, orphan_job_id)
        assert task.status == "queued"
        assert task.locked_by is None
        assert task.parse_job_run_id is None
        assert task.next_attempt_at is not None
        assert attachment.parse_status == AttachmentStatus.PENDING
        assert job.status == JobStatus.FAILED
        assert job.finished_at is not None
        assert "超时" in job.error_message
