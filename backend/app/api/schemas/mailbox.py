"""多邮箱配置、运行状态和邮箱级授权 API 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator

from app.db.models import UserRole


class MailboxAccountCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=993, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=320)
    auth_mode: Literal["password", "oauth2"] = "password"
    credential: SecretStr | None = None
    use_ssl: bool = True
    start_tls: bool = False
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    folder: str = Field(default="INBOX", min_length=1, max_length=255)
    lookback_days: int = Field(default=7, ge=1, le=365)
    max_messages_per_run: int = Field(default=200, ge=1, le=5000)
    max_attachment_bytes: int = Field(default=50 * 1024 * 1024, ge=1024)
    retry_attempts: int = Field(default=3, ge=1, le=10)
    retry_base_delay_seconds: float = Field(default=1.0, ge=0, le=60)
    uid_reservation_stale_seconds: int = Field(default=1800, ge=60, le=86400)
    is_default: bool = False
    is_enabled: bool = True

    @model_validator(mode="after")
    def validate_transport(self) -> MailboxAccountCreate:
        if self.use_ssl and self.start_tls:
            raise ValueError("SSL/TLS 与 STARTTLS 不能同时启用")
        return self


class MailboxAccountUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, min_length=1, max_length=320)
    auth_mode: Literal["password", "oauth2"] | None = None
    credential: SecretStr | None = None
    clear_credential: bool = False
    use_ssl: bool | None = None
    start_tls: bool | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    folder: str | None = Field(default=None, min_length=1, max_length=255)
    lookback_days: int | None = Field(default=None, ge=1, le=365)
    max_messages_per_run: int | None = Field(default=None, ge=1, le=5000)
    max_attachment_bytes: int | None = Field(default=None, ge=1024)
    retry_attempts: int | None = Field(default=None, ge=1, le=10)
    retry_base_delay_seconds: float | None = Field(default=None, ge=0, le=60)
    uid_reservation_stale_seconds: int | None = Field(default=None, ge=60, le=86400)
    is_default: bool | None = None
    is_enabled: bool | None = None

    @model_validator(mode="after")
    def validate_credential_action(self) -> MailboxAccountUpdate:
        if self.clear_credential and "credential" in self.model_fields_set:
            raise ValueError("清空凭据和更新凭据不能同时执行")
        return self


class MailboxPermissions(BaseModel):
    can_read_metadata: bool = False
    can_read_content: bool = False
    can_operate: bool = False
    can_manage_credentials: bool = False


class MailboxAccountItem(BaseModel):
    id: int
    display_name: str
    provider_type: str
    host: str
    port: int
    username: str
    auth_mode: Literal["password", "oauth2"]
    use_ssl: bool
    start_tls: bool
    timeout_seconds: int
    folder: str
    lookback_days: int
    max_messages_per_run: int
    max_attachment_bytes: int
    is_default: bool
    is_enabled: bool
    credential_configured: bool
    configuration_source: str
    last_connection_status: str | None
    last_connection_at: datetime | None
    last_connection_error: str | None
    last_sync_status: str | None
    last_sync_at: datetime | None
    permissions: MailboxPermissions


class MailboxSecurityStatus(BaseModel):
    credential_key_configured: bool
    audit_key_configured: bool
    ready_for_credentials: bool


class TenantMemberItem(BaseModel):
    user_id: int
    username: str
    role: UserRole
    is_active: bool


class MailboxGrantUpdate(BaseModel):
    can_read_metadata: bool = True
    can_read_content: bool = False
    can_operate: bool = False
    can_manage_credentials: bool = False
    is_active: bool = True

    @model_validator(mode="after")
    def validate_permission_dependency(self) -> MailboxGrantUpdate:
        advanced = (
            self.can_read_content or self.can_operate or self.can_manage_credentials
        )
        if advanced and not self.can_read_metadata:
            raise ValueError("正文、操作或凭据权限必须同时包含邮箱元数据查看权限")
        return self


class MailboxGrantItem(MailboxGrantUpdate):
    user_id: int
    username: str
    role: UserRole
