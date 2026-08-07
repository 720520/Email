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
    error_message: str | None
    create_time: datetime


class ReportGenerateResponse(BaseModel):
    run: ReportRunItem
    download_url: str | None
