"""报表模板、合同来源、可复用定义和生成记录。"""

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


class ProductDocument(TenantOwnedMixin, CreatedAtMixin, Base):
    """产品合同等原始文件；只追加归档，提取结果保留来源文件引用。"""

    __tablename__ = "product_document"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "fund_product_id", "content_hash",
            name="uq_product_document_tenant_product_hash",
        ),
        Index("ix_product_document_product_time", "fund_product_id", "create_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fund_product_id: Mapped[int] = mapped_column(
        ForeignKey("fund_product.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    document_type: Mapped[str] = mapped_column(String(32), nullable=False, default="contract")
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_fields: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )


class ReportTemplate(TenantOwnedMixin, TimestampMixin, Base):
    """租户自有 PPTX 模板；内置模板由服务层以虚拟记录提供。"""

    __tablename__ = "report_template"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_report_template_tenant_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )


class ReportDefinition(TenantOwnedMixin, TimestampMixin, Base):
    """用户保存的自定义报表配置，可反复选择不同报告日期生成。"""

    __tablename__ = "report_definition"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_report_definition_tenant_name"),
        Index("ix_report_definition_product", "fund_product_id", "update_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    fund_product_id: Mapped[int] = mapped_column(
        ForeignKey("fund_product.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    template_key: Mapped[str] = mapped_column(String(64), nullable=False)
    report_type: Mapped[str] = mapped_column(String(32), nullable=False, default="weekly")
    sections: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )


class ReportRun(TenantOwnedMixin, CreatedAtMixin, Base):
    """每次生成均保存输入快照和输出文件引用，保证可追溯、可复核。"""

    __tablename__ = "report_run"
    __table_args__ = (
        Index("ix_report_run_tenant_time", "tenant_id", "create_time"),
        Index("ix_report_run_product_date", "fund_product_id", "report_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    definition_id: Mapped[int | None] = mapped_column(
        ForeignKey("report_definition.id", ondelete="SET NULL"), index=True
    )
    fund_product_id: Mapped[int] = mapped_column(
        ForeignKey("fund_product.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    template_key: Mapped[str] = mapped_column(String(64), nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    output_filename: Mapped[str | None] = mapped_column(String(500))
    output_path: Mapped[str | None] = mapped_column(String(1000))
    input_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
