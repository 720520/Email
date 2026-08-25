"""附件解析队列与人工复核暂存模型。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import MailboxOwnedMixin, TimestampMixin
from app.db.types import UTCDateTime, utc_now


class AttachmentParseTask(MailboxOwnedMixin, TimestampMixin, Base):
    """持久化附件解析任务；邮件同步只入队，不在 IMAP 会话中解析。"""

    __tablename__ = "attachment_parse_task"
    __table_args__ = (
        UniqueConstraint("attachment_id", name="uq_attachment_parse_task_attachment"),
        Index("ix_attachment_parse_task_queue", "status", "next_attempt_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attachment_id: Mapped[int] = mapped_column(
        ForeignKey("attachment_record.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_job_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_run.id", ondelete="SET NULL"), index=True
    )
    parse_job_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_run.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(32), default="scheduled", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    queued_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    locked_by: Mapped[str | None] = mapped_column(String(255))
    parser_version: Mapped[str | None] = mapped_column(String(64))
    inserted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exception_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)


class ParseSession(MailboxOwnedMixin, TimestampMixin, Base):
    """人工上传的解析会话；确认前不写入正式净值表。"""

    __tablename__ = "parse_session"
    __table_args__ = (
        UniqueConstraint("attachment_id", name="uq_parse_session_attachment"),
        Index("ix_parse_session_status_update_time", "status", "update_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attachment_id: Mapped[int] = mapped_column(
        ForeignKey("attachment_record.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_attachment_id: Mapped[int | None] = mapped_column(
        ForeignKey("attachment_record.id", ondelete="SET NULL"), index=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    confirmed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    file_issues: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    invalid_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ignored_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    error_message: Mapped[str | None] = mapped_column(Text)


class ParseResultRow(MailboxOwnedMixin, TimestampMixin, Base):
    """解析后的可编辑行；original_data 永久保存机器初始识别值。"""

    __tablename__ = "parse_result_row"
    __table_args__ = (
        UniqueConstraint(
            "parse_session_id", "source_sheet", "source_row", name="uq_parse_result_row_source"
        ),
        Index("ix_parse_result_row_session_status", "parse_session_id", "status", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parse_session_id: Mapped[int] = mapped_column(
        ForeignKey("parse_session.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="valid", nullable=False, index=True)
    source_sheet: Mapped[str] = mapped_column(String(255), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str | None] = mapped_column(String(255))
    product_code: Mapped[str | None] = mapped_column(String(64))
    master_product_code: Mapped[str | None] = mapped_column(String(64))
    asset_code: Mapped[str | None] = mapped_column(String(64))
    registration_code: Mapped[str | None] = mapped_column(String(64))
    share_class: Mapped[str | None] = mapped_column(String(32))
    nav_date: Mapped[date | None] = mapped_column(Date)
    unit_nav: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    total_nav: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    asset_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    asset_share: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    paid_in_capital: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    holding_shares: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    reference_market_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    total_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    total_assets_nav_ratio: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    investor_name: Mapped[str | None] = mapped_column(String(255))
    investor_account: Mapped[str | None] = mapped_column(String(128))
    parent_unit_nav: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    parent_total_nav: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    parent_asset_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    parent_product_code: Mapped[str | None] = mapped_column(String(64))
    parent_product_name: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    parent_paid_in_capital: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    investment_manager_info: Mapped[str | None] = mapped_column(Text)
    investment_strategy_info: Mapped[str | None] = mapped_column(Text)
    issues: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    original_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    validation_message: Mapped[str | None] = mapped_column(Text)
    conflict_action: Mapped[str] = mapped_column(String(32), default="unresolved", nullable=False)
    existing_nav_id: Mapped[int | None] = mapped_column(
        ForeignKey("fund_nav.id", ondelete="SET NULL"), index=True
    )
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    edit_reason: Mapped[str | None] = mapped_column(String(500))
    edited_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    committed_nav_id: Mapped[int | None] = mapped_column(
        ForeignKey("fund_nav.id", ondelete="SET NULL"), index=True
    )


class FundNavRevision(MailboxOwnedMixin, TimestampMixin, Base):
    """正式净值人工更正快照，保留修改前后完整字段。"""

    __tablename__ = "fund_nav_revision"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fund_nav_id: Mapped[int] = mapped_column(
        ForeignKey("fund_nav.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    parse_session_id: Mapped[int] = mapped_column(
        ForeignKey("parse_session.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    parse_result_row_id: Mapped[int] = mapped_column(
        ForeignKey("parse_result_row.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    original_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    corrected_data: Mapped[dict] = mapped_column(JSON, nullable=False)
