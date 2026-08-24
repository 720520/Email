"""可维护的报表字段定义与产品字段值。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import CreatedAtMixin, TenantOwnedMixin, TimestampMixin


class ReportFieldDefinition(TenantOwnedMixin, TimestampMixin, Base):
    """租户自定义报表字段；系统字段由 Provider 目录提供。"""

    __tablename__ = "report_field_definition"
    __table_args__ = (
        UniqueConstraint("tenant_id", "field_key", name="uq_report_field_tenant_key"),
        Index("ix_report_field_tenant_active", "tenant_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_key: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    data_type: Mapped[str] = mapped_column(String(32), nullable=False, default="string")
    value_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="scalar")
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="custom")
    source_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    format_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    default_value: Mapped[str | None] = mapped_column(Text)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )


class ReportFieldValue(TenantOwnedMixin, TimestampMixin, Base):
    """按业务实体和生效日保存自定义字段值。"""

    __tablename__ = "report_field_value"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "field_definition_id",
            "entity_type",
            "entity_id",
            "effective_date",
            name="uq_report_field_value_scope",
        ),
        Index("ix_report_field_value_entity", "tenant_id", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_definition_id: Mapped[int] = mapped_column(
        ForeignKey("report_field_definition.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, default="fund_product")
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text)
    value_json: Mapped[object | None] = mapped_column(JSON)
    effective_date: Mapped[date | None] = mapped_column(Date)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    source_reference: Mapped[str | None] = mapped_column(String(1000))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )


class ReportFieldDefinitionVersion(TenantOwnedMixin, CreatedAtMixin, Base):
    """字段定义的不可变快照，用于历史报表复现和审计。"""

    __tablename__ = "report_field_definition_version"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "field_definition_id",
            "version",
            name="uq_report_field_definition_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_definition_id: Mapped[int] = mapped_column(
        ForeignKey("report_field_definition.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
