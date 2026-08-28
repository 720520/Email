"""阶段 3：开户机构、材料模板、申请清单与补件轨迹。"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import CreatedAtMixin, TenantOwnedMixin, TimestampMixin
from app.db.types import UTCDateTime


class CounterpartyInstitution(TenantOwnedMixin, TimestampMixin, Base):
    __tablename__ = "counterparty_institution"
    __table_args__ = (
        UniqueConstraint("entity_id", name="uq_counterparty_institution_entity_id"),
        UniqueConstraint("tenant_id", "full_name", name="uq_counterparty_institution_full_name"),
        Index("ix_counterparty_institution_type_active", "institution_type", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entity.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    institution_type: Mapped[str] = mapped_column(String(32), nullable=False)
    full_name: Mapped[str] = mapped_column(String(300), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(100))
    license_code: Mapped[str | None] = mapped_column(String(100))
    contact_information: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class RequirementTemplate(TenantOwnedMixin, TimestampMixin, Base):
    __tablename__ = "requirement_template"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "institution_id",
            "account_type",
            "fund_type",
            "name",
            "version",
            name="uq_requirement_template_version",
        ),
        Index(
            "ix_requirement_template_match",
            "tenant_id",
            "institution_id",
            "account_type",
            "fund_type",
            "is_active",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    institution_id: Mapped[int | None] = mapped_column(
        ForeignKey("counterparty_institution.id", ondelete="RESTRICT"), index=True
    )
    template_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    account_type: Mapped[str] = mapped_column(String(64), nullable=False)
    fund_type: Mapped[str] = mapped_column(String(64), nullable=False, default="all")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class RequirementTemplateItem(TenantOwnedMixin, TimestampMixin, Base):
    __tablename__ = "requirement_template_item"
    __table_args__ = (
        UniqueConstraint(
            "template_id", "requirement_code", name="uq_requirement_template_item_code"
        ),
        Index("ix_requirement_template_item_order", "template_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("requirement_template.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requirement_code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    condition_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    seal_requirement: Mapped[str | None] = mapped_column(String(200))
    original_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AccountApplication(TenantOwnedMixin, TimestampMixin, Base):
    __tablename__ = "account_application"
    __table_args__ = (
        Index("ix_account_application_status", "tenant_id", "status", "application_date"),
        Index("ix_account_application_product", "product_id", "institution_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("fund_product.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    institution_id: Mapped[int] = mapped_column(
        ForeignKey("counterparty_institution.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    account_type: Mapped[str] = mapped_column(String(64), nullable=False)
    settlement_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    fund_type: Mapped[str] = mapped_column(String(64), nullable=False, default="all")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    application_date: Mapped[date] = mapped_column(Date, nullable=False)
    completed_date: Mapped[date | None] = mapped_column(Date)
    closed_date: Mapped[date | None] = mapped_column(Date)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reviewer_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class ApplicationRequirement(TenantOwnedMixin, TimestampMixin, Base):
    __tablename__ = "application_requirement"
    __table_args__ = (
        UniqueConstraint(
            "application_id", "requirement_code", name="uq_application_requirement_code"
        ),
        Index("ix_application_requirement_order", "application_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("account_application.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("requirement_template.id", ondelete="SET NULL"), index=True
    )
    requirement_code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    condition_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    seal_requirement: Mapped[str | None] = mapped_column(String(200))
    original_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="missing")
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_document.id", ondelete="RESTRICT"), index=True
    )
    review_comment: Mapped[str | None] = mapped_column(String(1000))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ApplicationSupplement(TenantOwnedMixin, CreatedAtMixin, Base):
    __tablename__ = "application_supplement"
    __table_args__ = (
        Index("ix_application_supplement_application", "application_id", "create_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("account_application.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("application_requirement.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("source_document.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    comment: Mapped[str | None] = mapped_column(String(1000))
    submitted_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False, index=True
    )


class ApplicationEvent(TenantOwnedMixin, CreatedAtMixin, Base):
    __tablename__ = "application_event"
    __table_args__ = (Index("ix_application_event_application", "application_id", "create_time"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("account_application.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str | None] = mapped_column(String(32))
    comment: Mapped[str | None] = mapped_column(String(1000))
    actor_user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    detail_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
