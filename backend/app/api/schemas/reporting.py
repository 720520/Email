"""报表中心 API 数据模型。"""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ReportTemplateItem(BaseModel):
    key: str
    id: int | None = None
    name: str
    description: str | None = None
    kind: Literal["builtin", "uploaded"]
    original_name: str | None = None
    is_active: bool = True
    create_time: datetime | None = None
    version_id: int | None = None
    version: int | None = None
    status: Literal["builtin", "draft", "validating", "published", "archived"] = "published"
    required_fields: list[str] = Field(default_factory=list)
    required_components: list[str] = Field(default_factory=list)
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)


class ReportProductField(BaseModel):
    key: str
    label: str
    group: str
    value: str | None = None
    source_type: str | None = None
    source_reference: str | None = None
    is_manual: bool
    editable: bool


class ReportProductFieldsResponse(BaseModel):
    product_id: int
    product_code: str
    product_name: str
    fields: list[ReportProductField]


class ReportFieldUpdate(BaseModel):
    value: str | None = Field(default=None, max_length=20_000)
    reason: str = Field(min_length=2, max_length=500)
    restore_source: bool = False

    @model_validator(mode="after")
    def validate_value(self) -> "ReportFieldUpdate":
        if not self.restore_source and "value" not in self.model_fields_set:
            raise ValueError("人工修改必须提交字段值")
        return self


class ContractUploadResponse(BaseModel):
    document_id: int
    original_name: str
    extracted_fields: dict[str, str]
    extracted_count: int


class ReportDefinitionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    fund_product_id: int
    template_key: str = Field(default="builtin:weekly", max_length=64)
    report_type: Literal["weekly", "custom"] = "weekly"
    sections: list[str] = Field(default_factory=list, max_length=20)
    settings: dict[str, Any] = Field(default_factory=dict)


class ReportDefinitionItem(ReportDefinitionCreate):
    id: int
    create_time: datetime
    update_time: datetime


class ReportGenerateRequest(BaseModel):
    definition_id: int | None = None
    fund_product_id: int | None = None
    template_key: str | None = Field(default=None, max_length=64)
    report_date: date | None = None
    sections: list[str] | None = Field(default=None, max_length=20)
    settings: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source(self) -> "ReportGenerateRequest":
        if self.definition_id is None and self.fund_product_id is None:
            raise ValueError("请选择已保存报表或基金产品")
        return self


class ReportPreviewRequest(BaseModel):
    fund_product_id: int
    report_date: date | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class ReportPreviewResponse(BaseModel):
    product_id: int
    product_code: str
    product_name: str
    report_date: date
    fields: dict[str, Any]
    field_provenance: list[ReportProductField]
    performance: dict[str, str | None]
    nav_series: list[dict[str, str | None]]


class ReportRunItem(BaseModel):
    id: int
    definition_id: int | None
    fund_product_id: int
    product_name: str
    template_key: str
    report_date: date
    status: str
    output_filename: str | None
    current_version_id: int | None = None
    current_version: int | None = None
    template_version_id: int | None = None
    error_stage: str | None = None
    error_code: str | None = None
    error_message: str | None
    create_time: datetime


class ReportGenerateResponse(BaseModel):
    run: ReportRunItem
    download_url: str | None


class ReportFileVersionItem(BaseModel):
    id: int
    report_run_id: int
    version: int
    source: str
    filename: str
    content_hash: str
    file_size: int
    create_time: datetime


class ReportBatchCreate(BaseModel):
    product_ids: list[int] = Field(default_factory=list, max_length=1000)
    product_code_contains: str | None = Field(default=None, max_length=100)
    product_name_contains: str | None = Field(default=None, max_length=200)
    template_key: str = Field(max_length=64)
    report_date: date
    sections: list[str] = Field(default_factory=list, max_length=20)
    settings: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def require_selection(self) -> "ReportBatchCreate":
        if not self.product_ids and not (self.product_code_contains or self.product_name_contains):
            raise ValueError("必须选择基金或提供产品筛选条件")
        return self


class ReportBatchItemView(BaseModel):
    id: int
    fund_product_id: int
    product_name: str
    status: str
    report_run_id: int | None
    attempt_count: int
    error_code: str | None
    error_message: str | None


class ReportBatchView(BaseModel):
    id: int
    template_key: str
    template_version_id: int | None
    report_date: date
    status: str
    total_count: int
    success_count: int
    failed_count: int
    cancelled_count: int
    create_time: datetime


class OnlyOfficeSessionResponse(BaseModel):
    api_url: str
    config: dict[str, Any]
