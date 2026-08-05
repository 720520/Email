"""租户、成员关系与邮箱级授权。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import UserRole
from app.db.models.mixins import TenantOwnedMixin, TimestampMixin

if TYPE_CHECKING:
    from app.db.models.app_user import AppUser
    from app.db.models.mailbox_account import MailboxAccount


class Tenant(TimestampMixin, Base):
    """机构或独立业务账套，是系统最外层数据边界。"""

    __tablename__ = "tenant"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    memberships: Mapped[list[TenantMembership]] = relationship(back_populates="tenant")
    mailboxes: Mapped[list[MailboxAccount]] = relationship(back_populates="tenant")


class TenantMembership(TenantOwnedMixin, TimestampMixin, Base):
    """用户在指定租户内的角色；不再依赖全局角色决定业务权限。"""

    __tablename__ = "tenant_membership"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_membership_tenant_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="tenant_user_role",
            native_enum=False,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    tenant: Mapped[Tenant] = relationship(back_populates="memberships")
    user: Mapped[AppUser] = relationship(back_populates="tenant_memberships")


class MailboxUserGrant(TenantOwnedMixin, TimestampMixin, Base):
    """邮箱资源级授权，后续开放多邮箱时直接复用。"""

    __tablename__ = "mailbox_user_grant"
    __table_args__ = (
        UniqueConstraint(
            "mailbox_account_id",
            "user_id",
            name="uq_mailbox_user_grant_mailbox_user",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mailbox_account_id: Mapped[int] = mapped_column(
        ForeignKey("mailbox_account.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    can_read_metadata: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_read_content: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_operate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_manage_credentials: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    mailbox: Mapped[MailboxAccount] = relationship(back_populates="user_grants")
    user: Mapped[AppUser] = relationship(back_populates="mailbox_grants")
