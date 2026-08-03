"""邮箱配置与连接检测响应模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class EmailConnectionInfoResponse(BaseModel):
    host: str
    port: int
    username: str
    auth_mode: Literal["password", "oauth2"]
    folder: str
    transport: str
    timeout_seconds: int
    credential_configured: bool
    configured: bool


class EmailConnectionTestResponse(BaseModel):
    success: bool
    message: str
    checked_at: datetime
    latency_ms: int
    uid_validity: str | None
    message_count: int | None


class EmailSyncResponse(BaseModel):
    success: bool
    message: str
    job_run_id: int
    attempts: int
    discovered_count: int
    archived_count: int
    ignored_count: int
    duplicate_count: int
    failed_count: int
