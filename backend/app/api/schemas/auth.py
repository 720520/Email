"""认证接口模型。"""

from pydantic import BaseModel, Field

from app.db.models import UserRole


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class UserResponse(BaseModel):
    id: int
    username: str
    role: UserRole


class LoginResponse(BaseModel):
    user: UserResponse
    expires_at: str
