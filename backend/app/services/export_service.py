"""每日基金净值 Excel 导出服务。"""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.credential_security import audit_signing_key
from app.db.models import (
    ExceptionRecord,
    ExceptionSeverity,
    ExceptionStatus,
    JobRun,
    JobStatus,
    JobType,
    TriggerType,
)
from app.db.session import configure_tenant_scope
from app.domain.exception_categories import exception_category
from app.exports import DailyNavExportRow, DailyNavWorkbookBuilder, ExceptionExportRow
from app.repositories import ExportRepository
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

@dataclass(frozen=True, slots=True)
class DailyExportResult:
    report_date: date
    output_path: Path
    nav_count: int
    exception_count: int
    job_run_id: int


class DailyExcelExportService:
    """查询业务数据，构建双工作表，并以原子方式发布到日期目录。"""

    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        *,
        tenant_id: int,
        mailbox_ids: tuple[int, ...],
        actor_user_id: int | None = None,
        actor_username: str = "system",
        repository: ExportRepository | None = None,
        workbook_builder: DailyNavWorkbookBuilder | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.tenant_id = tenant_id
        self.mailbox_ids = mailbox_ids
        self.actor_user_id = actor_user_id
        self.actor_username = actor_username
        self.audit = AuditService(audit_signing_key(settings.security))
        self.repository = repository or ExportRepository()
        self.workbook_builder = workbook_builder or DailyNavWorkbookBuilder()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.timezone = ZoneInfo(settings.storage.archive_timezone)

    def export(
        self,
        report_date: date | None = None,
        *,
        trigger_type: TriggerType = TriggerType.MANUAL,
    ) -> DailyExportResult:
        now = self._now()
        local_now = now.astimezone(self.timezone)
        target_date = report_date or local_now.date()
        job_run_id = self._start_job(trigger_type, started_at=now)

        try:
            nav_rows, exception_rows = self._load_rows(target_date)
            workbook = self.workbook_builder.build(
                report_date=target_date,
                generated_at=local_now,
                nav_rows=nav_rows,
                exception_rows=exception_rows,
            )
            output_path = self._output_path(target_date)
            self._save_atomic(workbook, output_path)
            self._finish_job(job_run_id, success=True)
        except Exception as exc:
            try:
                self._finish_job(job_run_id, success=False, error_message=str(exc))
            except Exception:
                logger.critical(
                    "导出失败且任务状态回写失败",
                    extra={"job_run_id": job_run_id},
                    exc_info=True,
                )
            logger.exception("每日基金净值汇总导出失败", extra={"job_run_id": job_run_id})
            raise

        logger.info(
            "每日基金净值汇总导出成功",
            extra={
                "job_run_id": job_run_id,
                "report_date": target_date.isoformat(),
                "nav_count": len(nav_rows),
                "exception_count": len(exception_rows),
                "output_path": str(output_path),
            },
        )
        return DailyExportResult(
            report_date=target_date,
            output_path=output_path,
            nav_count=len(nav_rows),
            exception_count=len(exception_rows),
            job_run_id=job_run_id,
        )

    def _load_rows(
        self,
        report_date: date,
    ) -> tuple[list[DailyNavExportRow], list[ExceptionExportRow]]:
        start_local = datetime.combine(report_date, time.min, tzinfo=self.timezone)
        end_local = start_local + timedelta(days=1)
        with self.session_factory() as session:
            self._scope(session)
            nav_records = self.repository.list_nav_by_date(
                session,
                report_date,
                tenant_id=self.tenant_id,
                mailbox_ids=self.mailbox_ids,
            )
            exception_records = self.repository.list_exceptions_by_created_range(
                session,
                tenant_id=self.tenant_id,
                mailbox_ids=self.mailbox_ids,
                start_time=start_local.astimezone(UTC),
                end_time=end_local.astimezone(UTC),
            )

            nav_rows = [
                DailyNavExportRow(
                    nav_date=item.nav_date,
                    product_code=item.product_code,
                    product_name=item.product_name,
                    unit_nav=item.unit_nav,
                    total_nav=item.total_nav,
                    asset_value=item.asset_value,
                    source_file=item.source_file,
                )
                for item in nav_records
            ]
            exception_rows = [
                self._exception_row(exception, attachment_name, subject)
                for exception, attachment_name, subject in exception_records
            ]
        return nav_rows, exception_rows

    def _exception_row(
        self,
        exception: ExceptionRecord,
        attachment_name: str | None,
        subject: str | None,
    ) -> ExceptionExportRow:
        raw_data = exception.raw_data if isinstance(exception.raw_data, dict) else {}
        return ExceptionExportRow(
            occurred_date=exception.create_time.astimezone(self.timezone).date(),
            category=exception_category(exception.exception_type),
            severity=(
                "错误" if exception.severity == ExceptionSeverity.ERROR else "警告"
            ),
            product_code=_raw_text(raw_data, "product_code"),
            product_name=_raw_text(raw_data, "product_name"),
            source=attachment_name or subject or "系统",
            sheet_name=exception.sheet_name,
            row_number=exception.row_number,
            field_name=exception.field_name,
            raw_value=exception.raw_value,
            message=exception.message,
            status=_exception_status_label(exception.status),
        )

    def _output_path(self, report_date: date) -> Path:
        scope_directory = self.settings.data_directory / "tenants" / str(self.tenant_id)
        if len(self.mailbox_ids) == 1:
            scope_directory = scope_directory / "mailboxes" / str(self.mailbox_ids[0])
        else:
            scope_directory = scope_directory / "combined"
        return (
            scope_directory
            / f"{report_date.year:04d}"
            / f"{report_date.month:02d}"
            / f"{report_date.day:02d}"
            / "exports"
            / self.settings.storage.daily_export_filename
        )

    @staticmethod
    def _save_atomic(workbook, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output_path.stem}.",
            suffix=".tmp.xlsx",
            dir=output_path.parent,
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        try:
            workbook.save(temporary_path)
            with temporary_path.open("rb+") as handle:
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, output_path)
        finally:
            workbook.close()
            temporary_path.unlink(missing_ok=True)

    def _start_job(self, trigger_type: TriggerType, *, started_at: datetime) -> int:
        with self.session_factory() as session, session.begin():
            self._scope(session)
            job = JobRun(
                tenant_id=self.tenant_id,
                mailbox_account_id=(self.mailbox_ids[0] if len(self.mailbox_ids) == 1 else None),
                triggered_by_user_id=self.actor_user_id,
                job_type=JobType.EXPORT,
                trigger_type=trigger_type,
                status=JobStatus.RUNNING,
                started_at=started_at,
            )
            session.add(job)
            session.flush()
            self.audit.append(
                session,
                tenant_id=self.tenant_id,
                actor_user_id=self.actor_user_id,
                actor_username=self.actor_username,
                mailbox_account_id=job.mailbox_account_id,
                action="nav.export.start",
                resource_type="job_run",
                resource_id=job.id,
                outcome="started",
            )
            return job.id

    def _finish_job(
        self,
        job_run_id: int,
        *,
        success: bool,
        error_message: str | None = None,
    ) -> None:
        with self.session_factory() as session, session.begin():
            self._scope(session)
            job = session.get(JobRun, job_run_id)
            if job is None:
                raise RuntimeError(f"导出任务记录不存在: {job_run_id}")
            job.finished_at = self._now()
            job.status = JobStatus.SUCCESS if success else JobStatus.FAILED
            job.success_count = 1 if success else 0
            job.failure_count = 0 if success else 1
            job.error_message = None if success else (error_message or "未知导出错误")[:4000]
            self.audit.append(
                session,
                tenant_id=self.tenant_id,
                actor_user_id=self.actor_user_id,
                actor_username=self.actor_username,
                mailbox_account_id=job.mailbox_account_id,
                action="nav.export.finish",
                resource_type="job_run",
                resource_id=job.id,
                outcome=job.status.value,
                detail={"error": job.error_message},
            )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("导出服务时钟必须返回带时区的时间")
        return value.astimezone(UTC)

    def _scope(self, session: Session) -> None:
        configure_tenant_scope(
            session,
            tenant_id=self.tenant_id,
            mailbox_ids=self.mailbox_ids,
        )


def _raw_text(raw_data: dict[str, Any], key: str) -> str | None:
    value = raw_data.get(key)
    return None if value is None else str(value)


def _exception_status_label(status: ExceptionStatus) -> str:
    labels = {
        ExceptionStatus.OPEN: "待处理",
        ExceptionStatus.RESOLVED: "已解决",
        ExceptionStatus.IGNORED: "已忽略",
    }
    return labels[status]
