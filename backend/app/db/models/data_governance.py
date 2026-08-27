"""阶段 1：统一主体、字段事实、来源文件与显式授权。"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import CreatedAtMixin, TenantOwnedMixin, TimestampMixin
from app.db.types import UTCDateTime


class Entity(TenantOwnedMixin, TimestampMixin, Base):
    __tablename__ = "entity"
    __table_args__ = (
        UniqueConstraint("tenant_id", "entity_type", "external_code", name="uq_entity_code"),
        Index("ix_entity_tenant_type_status", "tenant_id", "entity_type", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    external_code: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )


class FieldDefinition(TenantOwnedMixin, TimestampMixin, Base):
    __tablename__ = "field_definition"
    __table_args__ = (
        UniqueConstraint("tenant_id", "entity_type", "field_code", name="uq_field_definition_code"),
        Index("ix_field_definition_type_order", "tenant_id", "entity_type", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    field_code: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    sensitivity: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    is_multivalue: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    display_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class FieldValue(TenantOwnedMixin, CreatedAtMixin, Base):
    __tablename__ = "field_value"
    __table_args__ = (
        Index("ix_field_value_entity_field_time", "entity_id", "field_definition_id", "valid_from"),
        Index("ix_field_value_source_document", "source_document_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entity.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    field_definition_id: Mapped[int] = mapped_column(
        ForeignKey("field_definition.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    value_json: Mapped[object] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    valid_from: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(UTCDateTime())
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_document.id", ondelete="RESTRICT"), index=True
    )
    source_locator_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    extraction_run_id: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[int | None] = mapped_column(Integer)
    entered_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )


class SourceDocument(TenantOwnedMixin, CreatedAtMixin, Base):
    __tablename__ = "source_document"
    __table_args__ = (
        UniqueConstraint("tenant_id", "document_key", "version", name="uq_source_document_version"),
        Index("ix_source_document_entity_time", "entity_id", "create_time"),
        Index("ix_source_document_hash", "tenant_id", "content_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_key: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(
        ForeignKey("entity.id", ondelete="RESTRICT"), index=True
    )
    document_type: Mapped[str] = mapped_column(String(100), nullable=False)
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(200), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_date: Mapped[date | None]
    expiry_date: Mapped[date | None]
    source_channel: Mapped[str] = mapped_column(String(32), nullable=False)
    sensitivity: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )


class DocumentRelation(TenantOwnedMixin, CreatedAtMixin, Base):
    __tablename__ = "document_relation"
    __table_args__ = (
        UniqueConstraint("document_id", "entity_id", "relation_type", name="uq_document_relation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("source_document.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entity.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)


class ResourceGrant(TenantOwnedMixin, TimestampMixin, Base):
    """对默认角色策略的显式补充授权；用于敏感资料和后续产品级授权。"""

    __tablename__ = "resource_grant"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "entity_id", name="uq_resource_grant_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_id: Mapped[int | None] = mapped_column(
        ForeignKey("entity.id", ondelete="CASCADE"), index=True
    )
    permissions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    sensitivity_ceiling: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    granted_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )


class SourceDocumentImmutableError(RuntimeError):
    pass


@event.listens_for(SourceDocument, "before_update")
@event.listens_for(SourceDocument, "before_delete")
def _reject_source_document_mutation(*args) -> None:
    del args
    raise SourceDocumentImmutableError("来源文件版本为不可变记录，禁止更新或删除")
