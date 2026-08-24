"""租户级备案复用字段与不可变文件版本。"""

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import CreatedAtMixin, TenantOwnedMixin, TimestampMixin


class FilingProfile(TenantOwnedMixin, TimestampMixin, Base):
    """每个私募牌照一份可复用的公司、人员和材料资料。"""

    __tablename__ = "filing_profile"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_filing_profile_tenant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_values: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    document_notes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class FilingField(TenantOwnedMixin, TimestampMixin, Base):
    """管理员自定义的文本或文件字段；删除采用停用以保留历史。"""

    __tablename__ = "filing_field"
    __table_args__ = (
        UniqueConstraint("tenant_id", "field_key", name="uq_filing_field_tenant_key"),
        Index("ix_filing_field_tenant_order", "tenant_id", "sort_order", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    field_type: Mapped[str] = mapped_column(String(16), nullable=False, default="text")
    sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    multiline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_forms: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )


class FilingFileVersion(TenantOwnedMixin, CreatedAtMixin, Base):
    """备案文件只追加版本，不覆盖旧文件。"""

    __tablename__ = "filing_file_version"
    __table_args__ = (
        UniqueConstraint("tenant_id", "field_id", "version", name="uq_filing_file_version"),
        Index("ix_filing_file_version_field_time", "field_id", "create_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(
        ForeignKey("filing_field.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(200))
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
