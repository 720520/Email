"""数据库驱动的批量报表 Worker；Web 进程不执行批量渲染。"""

from __future__ import annotations

import socket
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.reports import (
    ReportGenerationStageError,
    _create_file_version,
    _stored_template_path,
)
from app.db.models import (
    FundProduct,
    ReportBatch,
    ReportBatchItem,
    ReportRun,
    ReportTemplateVersion,
)
from app.db.session import configure_tenant_scope
from app.db.types import utc_now
from app.services.archive_service import sanitize_filename


class ReportBatchWorker:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        worker_id: str | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.worker_id = worker_id or f"{socket.gethostname()}:{id(self)}"

    def recover_stale(self, stale_minutes: int = 15) -> int:
        cutoff = utc_now() - timedelta(minutes=stale_minutes)
        with self.session_factory() as session, session.begin():
            session.info["skip_tenant_scope"] = True
            result = session.execute(
                update(ReportBatchItem)
                .where(
                    ReportBatchItem.status == "processing",
                    ReportBatchItem.locked_at < cutoff,
                )
                .values(status="pending", locked_by=None, locked_at=None)
            )
            return result.rowcount

    def run_once(self) -> bool:
        claimed = self._claim()
        if claimed is None:
            return False
        item_id, tenant_id = claimed
        self._process(item_id, tenant_id)
        return True

    def _claim(self) -> tuple[int, int] | None:
        with self.session_factory() as session, session.begin():
            session.info["skip_tenant_scope"] = True
            candidate = session.execute(
                select(
                    ReportBatchItem.id,
                    ReportBatchItem.tenant_id,
                    ReportBatchItem.batch_id,
                )
                .join(ReportBatch, ReportBatch.id == ReportBatchItem.batch_id)
                .where(
                    ReportBatchItem.status == "pending",
                    ReportBatch.status.in_(("pending", "processing")),
                )
                .order_by(ReportBatchItem.id)
                .limit(1)
            ).first()
            if candidate is None:
                return None
            result = session.execute(
                update(ReportBatchItem)
                .where(
                    ReportBatchItem.id == candidate.id,
                    ReportBatchItem.status == "pending",
                )
                .values(
                    status="processing",
                    locked_by=self.worker_id,
                    locked_at=utc_now(),
                    attempt_count=ReportBatchItem.attempt_count + 1,
                )
            )
            if result.rowcount != 1:
                return None
            session.execute(
                update(ReportBatch)
                .where(ReportBatch.id == candidate.batch_id)
                .values(status="processing")
            )
            return candidate.id, candidate.tenant_id

    def _process(self, item_id: int, tenant_id: int) -> None:
        with self.session_factory() as session:
            configure_tenant_scope(session, tenant_id=tenant_id, mailbox_ids=())
            item = session.get(ReportBatchItem, item_id)
            if item is None or item.status != "processing":
                return
            batch = session.get(ReportBatch, item.batch_id)
            product = session.get(FundProduct, item.fund_product_id)
            if batch is None or product is None:
                item.status = "failed"
                item.error_code = "REPORT_BATCH_CONTEXT_MISSING"
                item.error_message = "批次或基金不存在"
                self._refresh_batch(session, batch)
                session.commit()
                return
            existing = (
                session.scalar(
                    select(ReportRun).where(
                        ReportRun.id == item.report_run_id,
                        ReportRun.status == "success",
                    )
                )
                if item.report_run_id
                else None
            )
            if existing is not None:
                item.status = "success"
                self._refresh_batch(session, batch)
                session.commit()
                return
            snapshot = dict(item.input_snapshot or {})
            run = session.get(ReportRun, item.report_run_id) if item.report_run_id else None
            if run is None:
                run = ReportRun(
                    tenant_id=tenant_id,
                    fund_product_id=product.id,
                    template_key=batch.template_key,
                    template_version_id=batch.template_version_id,
                    report_date=batch.report_date,
                    status="processing",
                    input_snapshot=snapshot,
                    field_definition_versions=dict(snapshot.get("field_definition_versions") or {}),
                    created_by_user_id=batch.created_by_user_id,
                )
                session.add(run)
                session.flush()
                item.report_run_id = run.id
            else:
                run.status = "processing"
                run.error_stage = run.error_code = run.error_message = None
            template = (
                session.get(ReportTemplateVersion, batch.template_version_id)
                if batch.template_version_id
                else None
            )
            template_path: Path | None = _stored_template_path(template) if template else None
            product_name = snapshot.get("product_name") or product.product_name
            filename = (
                f"{sanitize_filename(product_name, max_length=80)}_"
                f"{batch.report_date.isoformat()}_基金周报.pptx"
            )
            try:
                _create_file_version(
                    session,
                    run,
                    snapshot,
                    list(batch.sections or []),
                    template_path,
                    filename,
                    source="generated",
                    user_id=batch.created_by_user_id,
                )
                run.status = item.status = "success"
                item.error_code = item.error_message = None
            except ReportGenerationStageError as exc:
                run.status = item.status = "failed"
                run.error_stage = exc.stage
                run.error_code = exc.code
                run.error_message = str(exc)[:1000]
                item.error_code, item.error_message = exc.code, str(exc)[:1000]
            except Exception as exc:  # 单项异常不得中止整个 Worker
                run.status = item.status = "failed"
                run.error_stage = "worker"
                run.error_code = "REPORT_BATCH_ITEM_FAILED"
                run.error_message = str(exc)[:1000]
                item.error_code = run.error_code
                item.error_message = run.error_message
            item.locked_by = item.locked_at = None
            self._refresh_batch(session, batch)
            session.commit()

    @staticmethod
    def _refresh_batch(session: Session, batch: ReportBatch | None) -> None:
        if batch is None:
            return
        session.flush()
        counts = dict(
            session.execute(
                select(ReportBatchItem.status, func.count(ReportBatchItem.id))
                .where(ReportBatchItem.batch_id == batch.id)
                .group_by(ReportBatchItem.status)
            ).all()
        )
        batch.success_count = counts.get("success", 0)
        batch.failed_count = counts.get("failed", 0)
        batch.cancelled_count = counts.get("cancelled", 0)
        remaining = counts.get("pending", 0) + counts.get("processing", 0)
        if remaining:
            batch.status = "processing"
        elif batch.cancelled_count and not (batch.success_count or batch.failed_count):
            batch.status = "cancelled"
        elif batch.failed_count:
            batch.status = "partial_failed"
        else:
            batch.status = "success"
