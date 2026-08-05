"""租户内追加式审计日志查询。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import TenantContext, TenantDatabaseSession, require_roles
from app.api.schemas.audit import AuditEventListItem
from app.api.schemas.common import PageResponse
from app.db.models import AuditEvent, UserRole

router = APIRouter()
AdminScope = Annotated[TenantContext, Depends(require_roles(UserRole.ADMIN))]


@router.get("", response_model=PageResponse[AuditEventListItem])
def list_audit_events(
    session: TenantDatabaseSession,
    scope: AdminScope,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    action: str | None = Query(default=None, max_length=100),
    mailbox_account_id: int | None = Query(default=None, ge=1),
) -> PageResponse[AuditEventListItem]:
    conditions = [AuditEvent.tenant_id == scope.tenant_id]
    if action and action.strip():
        conditions.append(AuditEvent.action == action.strip())
    if mailbox_account_id is not None:
        if mailbox_account_id not in scope.mailbox_ids:
            return PageResponse(items=[], total=0, page=page, page_size=page_size)
        conditions.append(AuditEvent.mailbox_account_id == mailbox_account_id)
    total = session.scalar(select(func.count(AuditEvent.id)).where(*conditions)) or 0
    statement = (
        select(AuditEvent)
        .where(*conditions)
        .order_by(AuditEvent.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return PageResponse(
        items=[
            AuditEventListItem.model_validate(item, from_attributes=True)
            for item in session.scalars(statement)
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
