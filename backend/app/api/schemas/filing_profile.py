"""动态备案资料库 API 模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class FilingFileVersionItem(BaseModel):
    id: int
    version: int
    original_name: str
    file_size: int
    content_type: str | None
    content_hash: str
    created_by: str
    create_time: datetime
    download_url: str


class FilingFieldDefinition(BaseModel):
    id: int
    key: str
    label: str
    category: str
    field_type: Literal["text", "file"]
    sensitive: bool = False
    multiline: bool = False
    source_forms: list[str] = Field(default_factory=list)
    sort_order: int = 0
    file_versions: list[FilingFileVersionItem] = Field(default_factory=list)


class FilingProfileResponse(BaseModel):
    tenant_name: str
    can_edit: bool
    fields: list[FilingFieldDefinition]
    field_values: dict[str, str]
    update_time: datetime | None = None


class FilingProfileUpdate(BaseModel):
    field_values: dict[str, str] = Field(default_factory=dict)


class FilingFieldCreate(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    field_type: Literal["text", "file"] = "text"
    sensitive: bool = False
    multiline: bool = False
    source_forms: list[str] = Field(default_factory=list, max_length=20)
    sort_order: int = Field(default=0, ge=0, le=100_000)

    @field_validator("label", "category")
    @classmethod
    def clean_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("字段名称和分类不能为空")
        return value.strip()


class FilingFieldUpdate(FilingFieldCreate):
    pass
