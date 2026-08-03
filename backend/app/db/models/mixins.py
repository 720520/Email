"""模型公共字段。"""

from datetime import datetime

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

