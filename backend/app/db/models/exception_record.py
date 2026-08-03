"""解析、重复和人工处理异常模型。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import ExceptionSeverity, ExceptionStatus
from app.db.models.mixins import CreatedAtMixin
from app.db.types import UTCDateTime

if TYPE_CHECKING:
    from app.db.models.email_record import AttachmentRecord, EmailRecord


class ExceptionRecord(CreatedAtMixin, Base):
    __tablename__ = "exception_record"
    __table_args__ = (
        Index("ix_exception_record_status_create_time", "status", "create_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email_id: Mapped[int | None] = mapped_column(
        ForeignKey("email_record.id", ondelete="RESTRICT"), index=True
    )
    attachment_id: Mapped[int | None] = mapped_column(
        ForeignKey("attachment_record.id", ondelete="RESTRICT"), index=True
    )
    exception_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    severity: Mapped[ExceptionSeverity] = mapped_column(
        Enum(
            ExceptionSeverity,
            name="exception_severity",
            native_enum=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    sheet_name: Mapped[str | None] = mapped_column(String(255))
    row_number: Mapped[int | None] = mapped_column(Integer)
    field_name: Mapped[str | None] = mapped_column(String(100))
    raw_value: Mapped[str | None] = mapped_column(Text)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ExceptionStatus] = mapped_column(
        Enum(
            ExceptionStatus,
            name="exception_status",
            native_enum=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        default=ExceptionStatus.OPEN,
        nullable=False,
    )
    resolved_time: Mapped[datetime | None] = mapped_column(UTCDateTime())

    email: Mapped[EmailRecord | None] = relationship(back_populates="exceptions")
    attachment: Mapped[AttachmentRecord | None] = relationship(back_populates="exceptions")
