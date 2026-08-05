"""租户管理、成员关系和平台权限 API 模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, SecretStr, field_validator

from app.db.models import UserRole


class TenantCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=255)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().casefold()


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None


class TenantSummary(BaseModel):
    id: int
    code: str
    name: str
    is_active: bool
    current_user_role: UserRole | None
    is_current: bool
    can_manage: bool
    member_count: int
    mailbox_count: int
    create_time: datetime


class TenantMemberCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: SecretStr | None = Field(default=None, min_length=10, max_length=256)
    role: UserRole = UserRole.VIEWER


class TenantMemberUpdate(BaseModel):
    role: UserRole
    is_active: bool = True


class TenantMemberItem(BaseModel):
    membership_id: int
    user_id: int
    username: str
    role: UserRole
    is_active: bool
    user_is_active: bool
    is_platform_admin: bool
    create_time: datetime
