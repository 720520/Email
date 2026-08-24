"""动态报表字段 API 数据模型。"""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

FieldDataType = Literal[
    "string",
    "number",
    "percentage",
    "date",
    "boolean",
    "rich_text",
    "image",
    "list",
    "table",
    "chart",
    "json",
]
FieldValueKind = Literal["scalar", "image", "list", "table", "chart", "json"]


class ReportFieldDefinitionCreate(BaseModel):
    field_key: str = Field(
        min_length=3, max_length=128, pattern=r"^custom\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$"
    )
    label: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    data_type: FieldDataType = "string"
    value_kind: FieldValueKind = "scalar"
    format_config: dict[str, Any] = Field(default_factory=dict)
    default_value: str | None = Field(default=None, max_length=20_000)
    is_required: bool = False
    is_sensitive: bool = False

    @field_validator("label", "description", "default_value")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class ReportFieldDefinitionUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    data_type: FieldDataType | None = None
    value_kind: FieldValueKind | None = None
    format_config: dict[str, Any] | None = None
    default_value: str | None = Field(default=None, max_length=20_000)
    is_required: bool | None = None
    is_sensitive: bool | None = None


class ReportFieldDefinitionItem(BaseModel):
    id: int | None
    field_key: str
    label: str
    description: str | None
    data_type: str
    value_kind: str
    source_type: str
    format_config: dict[str, Any]
    default_value: str | None
    is_required: bool
    is_sensitive: bool
    is_active: bool
    is_system: bool
    version: int
    create_time: datetime | None = None
    update_time: datetime | None = None


class ReportFieldResolveRequest(BaseModel):
    field_keys: list[str] = Field(min_length=1, max_length=200)
    product_id: int | None = None
    report_date: date | None = None


class ResolvedReportField(BaseModel):
    field_key: str
    value: Any = None
    data_type: str
    source_type: str | None = None
    source_reference: str | None = None
    used_default: bool = False


class ReportFieldResolveResponse(BaseModel):
    fields: dict[str, ResolvedReportField]


class ReportFieldValueUpdate(BaseModel):
    value: Any = None
    effective_date: date | None = None
    source_reference: str | None = Field(default=None, max_length=1000)


class ReportFieldValueItem(BaseModel):
    field_key: str
    label: str
    data_type: str
    value: Any = None
    effective_date: date | None = None
    source_type: str | None = None
    source_reference: str | None = None
    version: int = 0
