"""调度和人工任务运行记录。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import JobStatus, JobType, TriggerType
from app.db.models.mixins import CreatedAtMixin
from app.db.types import UTCDateTime, utc_now

if TYPE_CHECKING:
    from app.db.models.email_record import EmailRecord


class JobRun(CreatedAtMixin, Base):
    __tablename__ = "job_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[JobType] = mapped_column(
        Enum(
            JobType,
            name="job_type",
            native_enum=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        index=True,
    )
    trigger_type: Mapped[TriggerType] = mapped_column(
        Enum(
            TriggerType,
            name="trigger_type",
            native_enum=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[JobStatus] = mapped_column(
        Enum(
            JobStatus,
            name="job_status",
            native_enum=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        default=JobStatus.RUNNING,
        nullable=False,
        index=True,
    )
    emails_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    emails: Mapped[list[EmailRecord]] = relationship(back_populates="job_run")
