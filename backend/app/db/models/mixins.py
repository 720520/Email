"""模型公共字段。"""

from datetime import datetime

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.types import UTCDateTime, utc_now


class CreatedAtMixin:
    create_time: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        nullable=False,
    )


class TimestampMixin(CreatedAtMixin):
    update_time: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class TenantOwnedMixin:
    """需要由服务端租户上下文强制隔离的业务模型。"""

    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )


class MailboxOwnedMixin(TenantOwnedMixin):
    """除租户外，还必须受邮箱授权范围限制的业务模型。"""

    mailbox_account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("mailbox_account.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
