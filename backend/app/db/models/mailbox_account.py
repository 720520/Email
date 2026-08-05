"""可独立连接和调度的邮箱账户。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TenantOwnedMixin, TimestampMixin
from app.db.types import UTCDateTime

if TYPE_CHECKING:
    from app.db.models.tenant import MailboxUserGrant, Tenant


class MailboxAccount(TenantOwnedMixin, TimestampMixin, Base):
    """非敏感连接信息和加密凭据密文；任何接口都不得返回密文。"""

    __tablename__ = "mailbox_account"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "host",
            "username",
            "folder",
            name="uq_mailbox_account_tenant_identity",
        ),
        Index(
            "uq_mailbox_account_one_default_per_tenant",
            "tenant_id",
            unique=True,
            sqlite_where=text("is_default = 1"),
            postgresql_where=text("is_default = true"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(64), nullable=False, default="generic_imap")
    host: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=993)
    username: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    auth_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="password")
    configuration_source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="database"
    )
    credential_ciphertext: Mapped[str | None] = mapped_column(Text)
    credential_key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    credential_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    use_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    start_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    folder: Mapped[str] = mapped_column(String(255), nullable=False, default="INBOX")
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    max_messages_per_run: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    max_attachment_bytes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=50 * 1024 * 1024
    )
    retry_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retry_base_delay_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=1)
    uid_reservation_stale_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1800
    )
    parsing_options: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    last_connection_status: Mapped[str | None] = mapped_column(String(32))
    last_connection_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_connection_error: Mapped[str | None] = mapped_column(String(1000))
    last_sync_status: Mapped[str | None] = mapped_column(String(32))
    last_sync_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    tenant: Mapped[Tenant] = relationship(back_populates="mailboxes")
    user_grants: Mapped[list[MailboxUserGrant]] = relationship(back_populates="mailbox")
