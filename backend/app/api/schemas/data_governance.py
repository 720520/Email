"""阶段 1 数据治理 API 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

EntityType = Literal[
    "organization", "product", "investor", "fund_manager", "institution", "financial_account"
]
Sensitivity = Literal["normal", "sensitive", "highly_sensitive"]


class EntityCreate(BaseModel):
    entity_type: EntityType
    display_name: str = Field(min_length=1, max_length=300)
    external_code: str | None = Field(default=None, max_length=100)

    @field_validator("display_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return value.strip()


class EntityItem(BaseModel):
    id: int
    entity_type: str
    display_name: str
    external_code: str | None
    status: str
    create_time: datetime
    update_time: datetime


class FieldDefinitionCreate(BaseModel):
    entity_type: EntityType
    field_code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,99}$")
    label: str = Field(min_length=1, max_length=200)
    data_type: Literal["string", "number", "date", "datetime", "boolean", "json"]
    category: str = Field(min_length=1, max_length=100)
    sensitivity: Sensitivity = "normal"
    is_multivalue: bool = False
    validation_schema: dict[str, Any] = Field(default_factory=dict)
    display_schema: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = Field(default=0, ge=0, le=100_000)


class FieldDefinitionItem(FieldDefinitionCreate):
    id: int
    is_system: bool
    is_active: bool


class FieldValueCreate(BaseModel):
    field_definition_id: int
    value: Any
    status: Literal["draft", "extracted", "confirmed", "rejected"] = "draft"
    valid_from: datetime
    valid_to: datetime | None = None
    source_type: Literal["manual", "document", "email", "batch_import", "system"]
    source_document_id: int | None = None
    source_locator: dict[str, Any] = Field(default_factory=dict)
    confidence: int | None = Field(default=None, ge=0, le=100)


class FieldValueItem(BaseModel):
    id: int
    entity_id: int
    field_definition_id: int
    value: Any
    status: str
    valid_from: datetime
    valid_to: datetime | None
    source_type: str
    source_document_id: int | None
    source_locator: dict[str, Any]
    confidence: int | None
    entered_by_user_id: int | None
    reviewed_by_user_id: int | None
    create_time: datetime


class SourceDocumentItem(BaseModel):
    id: int
    document_key: str
    entity_id: int | None
    document_type: str
    original_name: str
    mime_type: str
    content_hash: str
    file_size: int
    version: int
    source_channel: str
    sensitivity: str
    create_time: datetime
    download_url: str


class ResourceGrantUpsert(BaseModel):
    user_id: int
    entity_id: int | None = None
    permissions: list[
        Literal["read", "create", "update", "approve", "download", "export", "sensitive_read"]
    ] = Field(min_length=1)
    sensitivity_ceiling: Sensitivity = "normal"


class ResourceGrantItem(ResourceGrantUpsert):
    id: int
    is_active: bool
