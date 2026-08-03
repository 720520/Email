"""每日净值和异常导出的只读查询仓储。"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AttachmentRecord, EmailRecord, ExceptionRecord, FundNav


class ExportRepository:
    @staticmethod
    def list_nav_by_date(session: Session, report_date: date) -> list[FundNav]:
        statement = (
            select(FundNav)
            .where(FundNav.nav_date == report_date)
            .order_by(FundNav.product_code, FundNav.product_name, FundNav.id)
        )
        return list(session.scalars(statement))

    @staticmethod
    def list_exceptions_by_created_range(
        session: Session,
        *,
        start_time: datetime,
        end_time: datetime,
    ) -> list[tuple[ExceptionRecord, str | None, str | None]]:
        statement = (
            select(
                ExceptionRecord,
                AttachmentRecord.original_name,
                EmailRecord.subject,
            )
            .outerjoin(
                AttachmentRecord,
                ExceptionRecord.attachment_id == AttachmentRecord.id,
            )
            .outerjoin(EmailRecord, ExceptionRecord.email_id == EmailRecord.id)
            .where(
                ExceptionRecord.create_time >= start_time,
                ExceptionRecord.create_time < end_time,
            )
            .order_by(
                ExceptionRecord.severity,
                ExceptionRecord.create_time,
                ExceptionRecord.id,
            )
        )
        return [
            (row[0], row[1], row[2])
            for row in session.execute(statement).all()
        ]
