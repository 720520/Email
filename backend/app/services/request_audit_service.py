"""把请求、租户和用户上下文统一接入追加式审计链。"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.api.deps import TenantContext
from app.core.config import get_settings
from app.core.credential_security import audit_signing_key
from app.db.models import AuditEvent
from app.services.audit_service import AuditService


class RequestAuditService:
    def append(
        self,
        session: Session,
        request: Request,
        scope: TenantContext,
        *,
        action: str,
        resource_type: str,
        resource_id: str | int | None,
        detail: dict[str, Any] | None = None,
        outcome: str = "success",
    ) -> AuditEvent:
        return AuditService(audit_signing_key(get_settings().security)).append(
            session,
            tenant_id=scope.tenant_id,
            actor_user_id=scope.user.id,
            actor_username=scope.user.username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            detail=detail,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
