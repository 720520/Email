"""邮件和附件审计模型。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import AttachmentStatus, EmailStatus
from app.db.models.mixins import TimestampMixin
from app.db.types import UTCDateTime

if TYPE_CHECKING:
    from app.db.models.exception_record import ExceptionRecord
    from app.db.models.fund_nav import FundNav
    from app.db.models.job_run import JobRun


class EmailRecord(TimestampMixin, Base):
    __tablename__ = "email_record"
    __table_args__ = (
        UniqueConstraint(
            "mailbox_key",
            "uid_validity",
            "message_uid",
            name="uq_email_record_mailbox_uidvalidity_uid",
        ),
        Index("ix_email_record_receive_time", "receive_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_run_id: Mapped[int | None] = mapped_column(ForeignKey("job_run.id", ondelete="SET NULL"))
    mailbox: Mapped[str] = mapped_column(String(255), nullable=False)
    mailbox_key: Mapped[str] = mapped_column(String(64), nullable=False)
    uid_validity: Mapped[str] = mapped_column(String(64), nullable=False, default="0")
    message_uid: Mapped[str] = mapped_column(String(64), nullable=False)
    message_id: Mapped[str | None] = mapped_column(String(500), index=True)
    subject: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    sender: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    receive_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    attachment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[EmailStatus] = mapped_column(
        Enum(
            EmailStatus,
            name="email_status",
            native_enum=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        default=EmailStatus.DISCOVERED,
        nullable=False,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    eml_path: Mapped[str | None] = mapped_column(String(1000))

    job_run: Mapped[JobRun | None] = relationship(back_populates="emails")
    attachments: Mapped[list[AttachmentRecord]] = relationship(
        back_populates="email",
        cascade="save-update, merge",
    )
    exceptions: Mapped[list[ExceptionRecord]] = relationship(back_populates="email")


class AttachmentRecord(TimestampMixin, Base):
    __tablename__ = "attachment_record"
    __table_args__ = (
        UniqueConstraint("email_id", "stored_path", name="uq_attachment_record_email_path"),
        Index("ix_attachment_record_sha256", "sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email_id: Mapped[int] = mapped_column(
        ForeignKey("email_record.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(64))
    parse_status: Mapped[AttachmentStatus] = mapped_column(
        Enum(
            AttachmentStatus,
            name="attachment_status",
            native_enum=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        default=AttachmentStatus.PENDING,
        nullable=False,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    email: Mapped[EmailRecord] = relationship(back_populates="attachments")
    nav_records: Mapped[list[FundNav]] = relationship(back_populates="attachment")
    exceptions: Mapped[list[ExceptionRecord]] = relationship(back_populates="attachment")
