"""追加式、可校验的合规审计事件。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import CreatedAtMixin, TenantOwnedMixin


class AuditEvent(TenantOwnedMixin, CreatedAtMixin, Base):
    __tablename__ = "audit_event"
    __table_args__ = (
        Index("ix_audit_event_tenant_time", "tenant_id", "create_time"),
        Index("ix_audit_event_resource", "resource_type", "resource_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    actor_username: Mapped[str] = mapped_column(String(100), nullable=False, default="system")
    mailbox_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("mailbox_account.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(100))
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
