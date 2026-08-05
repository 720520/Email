"""认证接口模型。"""

from pydantic import BaseModel, Field

from app.db.models import UserRole


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)
    tenant_id: int | None = Field(default=None, ge=1)


class TenantOption(BaseModel):
    id: int
    code: str
    name: str
    role: UserRole
    is_current: bool = False


class UserResponse(BaseModel):
    id: int
    username: str
    role: UserRole
    tenant_id: int
    tenant_code: str
    tenant_name: str
    is_platform_admin: bool


class LoginResponse(BaseModel):
    requires_tenant_selection: bool = False
    tenants: list[TenantOption] = Field(default_factory=list)
    user: UserResponse | None = None
    expires_at: str | None = None


class TenantSwitchRequest(BaseModel):
    tenant_id: int = Field(ge=1)
