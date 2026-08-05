"""合规审计查询响应。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditEventListItem(BaseModel):
    id: int
    actor_username: str
    mailbox_account_id: int | None
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    request_id: str
    ip_address: str | None
    detail: dict[str, Any] | None
    previous_hash: str
    event_hash: str
    create_time: datetime
