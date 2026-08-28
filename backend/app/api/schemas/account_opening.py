"""阶段 3 机构模板与开户台账 API 模型。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

InstitutionType = Literal[
    "broker",
    "futures_company",
    "custodian_bank",
    "commercial_bank",
    "fund_service_provider",
    "other",
]
TemplateScope = Literal["regulatory", "institution"]
SourceScope = Literal["organization", "product", "account_application"]
ApplicationStatus = Literal[
    "draft",
    "preparing",
    "pending_seal",
    "submitted",
    "supplement_required",
    "approved",
    "opened",
    "rejected",
    "closed",
]


class InstitutionCreate(BaseModel):
    institution_type: InstitutionType
    full_name: str = Field(min_length=1, max_length=300)
    short_name: str | None = Field(default=None, max_length=100)
    license_code: str | None = Field(default=None, max_length=100)
    contact_information: dict[str, str] = Field(default_factory=dict)

    @field_validator("full_name")
    @classmethod
    def clean_full_name(cls, value: str) -> str:
        return value.strip()


class InstitutionUpdate(BaseModel):
    institution_type: InstitutionType | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=300)
    short_name: str | None = Field(default=None, max_length=100)
    license_code: str | None = Field(default=None, max_length=100)
    contact_information: dict[str, str] | None = None
    is_active: bool | None = None


class InstitutionItem(BaseModel):
    id: int
    entity_id: int
    institution_type: str
    full_name: str
    short_name: str | None
    license_code: str | None
    contact_information: dict[str, str]
    is_active: bool
    create_time: datetime
    update_time: datetime


class RequirementTemplateItemCreate(BaseModel):
    requirement_code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,99}$")
    name: str = Field(min_length=1, max_length=200)
    source_scope: SourceScope
    required: bool = True
    condition: dict = Field(default_factory=dict)
    seal_requirement: str | None = Field(default=None, max_length=200)
    original_required: bool = False
    sort_order: int = Field(default=0, ge=0, le=100_000)


class RequirementTemplateCreate(BaseModel):
    template_scope: TemplateScope
    institution_id: int | None = None
    account_type: str = Field(min_length=1, max_length=64)
    fund_type: str = Field(default="all", min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    version: int = Field(default=1, ge=1)
    effective_from: date
    effective_to: date | None = None
    items: list[RequirementTemplateItemCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scope_and_dates(self) -> RequirementTemplateCreate:
        if self.template_scope == "institution" and self.institution_id is None:
            raise ValueError("机构模板必须选择机构")
        if self.template_scope == "regulatory" and self.institution_id is not None:
            raise ValueError("监管基础模板不能绑定单一机构")
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("模板失效日期不能早于生效日期")
        codes = [item.requirement_code for item in self.items]
        if len(codes) != len(set(codes)):
            raise ValueError("模板材料编码不能重复")
        return self


class RequirementTemplateStateUpdate(BaseModel):
    is_active: bool
    effective_to: date | None = None


class RequirementTemplateItemOut(RequirementTemplateItemCreate):
    id: int


class RequirementTemplateOut(BaseModel):
    id: int
    template_scope: str
    institution_id: int | None
    institution_name: str | None
    account_type: str
    fund_type: str
    name: str
    version: int
    effective_from: date
    effective_to: date | None
    is_active: bool
    items: list[RequirementTemplateItemOut]
    create_time: datetime
    update_time: datetime


class AccountApplicationCreate(BaseModel):
    product_id: int
    institution_id: int
    account_type: str = Field(min_length=1, max_length=64)
    settlement_mode: str = Field(min_length=1, max_length=64)
    fund_type: str = Field(default="all", min_length=1, max_length=64)
    application_date: date
    owner_user_id: int | None = None


class AccountApplicationUpdate(BaseModel):
    settlement_mode: str | None = Field(default=None, min_length=1, max_length=64)
    application_date: date | None = None
    owner_user_id: int | None = None
    status: Literal["draft", "preparing", "pending_seal"] | None = None


class RequirementDocumentAttach(BaseModel):
    document_id: int


class ApplicationSupplementCreate(BaseModel):
    requirement_id: int
    document_id: int
    comment: str | None = Field(default=None, max_length=1000)


class ApplicationReview(BaseModel):
    action: Literal["request_supplement", "approve", "reject", "open", "close"]
    requirement_ids: list[int] = Field(default_factory=list)
    comment: str | None = Field(default=None, max_length=1000)


class ApplicationRequirementOut(BaseModel):
    id: int
    requirement_code: str
    name: str
    source_scope: str
    required: bool
    condition: dict
    seal_requirement: str | None
    original_required: bool
    status: str
    document_id: int | None
    document_name: str | None
    document_version: int | None
    document_hash: str | None
    review_comment: str | None
    sort_order: int


class ApplicationSupplementOut(BaseModel):
    id: int
    requirement_id: int
    document_id: int
    document_name: str
    document_version: int
    document_hash: str
    comment: str | None
    submitted_by_user_id: int
    create_time: datetime


class ApplicationEventOut(BaseModel):
    id: int
    event_type: str
    from_status: str | None
    to_status: str | None
    comment: str | None
    actor_user_id: int
    detail: dict
    create_time: datetime


class AccountApplicationSummary(BaseModel):
    id: int
    product_id: int
    product_name: str
    product_code: str
    institution_id: int
    institution_name: str
    institution_type: str
    account_type: str
    settlement_mode: str
    fund_type: str
    status: str
    application_date: date
    completed_date: date | None
    closed_date: date | None
    owner_user_id: int
    reviewer_user_id: int | None
    submitted_at: datetime | None
    requirement_count: int
    completed_requirement_count: int
    create_time: datetime
    update_time: datetime


class AccountApplicationDetail(AccountApplicationSummary):
    requirements: list[ApplicationRequirementOut]
    supplements: list[ApplicationSupplementOut]
    events: list[ApplicationEventOut]
