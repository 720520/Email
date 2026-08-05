"""不可更新、不可删除且带 HMAC 哈希链的审计服务。"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.context import current_request_id
from app.db.models import AuditEvent

_REDACTED_KEYS = ("password", "credential", "token", "secret", "authorization", "cookie")


class AuditEventImmutableError(RuntimeError):
    pass


@event.listens_for(AuditEvent, "before_update")
@event.listens_for(AuditEvent, "before_delete")
def _reject_audit_mutation(*args) -> None:
    del args
    raise AuditEventImmutableError("审计事件为追加式记录，禁止更新或删除")


class AuditService:
    def __init__(self, signing_key: bytes) -> None:
        if len(signing_key) < 32:
            raise ValueError("审计签名密钥至少需要 32 字节")
        self.signing_key = signing_key

    def append(
        self,
        session: Session,
        *,
        tenant_id: int,
        actor_user_id: int | None,
        actor_username: str,
        action: str,
        resource_type: str,
        outcome: str,
        mailbox_account_id: int | None = None,
        resource_id: str | int | None = None,
        detail: dict[str, Any] | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditEvent:
        previous_hash = session.scalar(
            select(AuditEvent.event_hash)
            .where(AuditEvent.tenant_id == tenant_id)
            .order_by(AuditEvent.id.desc())
            .limit(1)
            .execution_options(skip_tenant_scope=True)
        ) or ("0" * 64)
        create_time = datetime.now(UTC)
        safe_detail = _sanitize(detail)
        actor_username = actor_username[:100] or "system"
        action = action[:100]
        resource_type = resource_type[:100]
        resource_id = None if resource_id is None else str(resource_id)[:100]
        outcome = outcome[:32]
        request_id = (request_id or current_request_id())[:128]
        ip_address = None if ip_address is None else ip_address[:64]
        user_agent = None if user_agent is None else user_agent[:500]
        canonical = _canonical_event(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_username=actor_username,
            mailbox_account_id=mailbox_account_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            create_time=create_time,
            detail=safe_detail,
            previous_hash=previous_hash,
        )
        event_hash = hmac.new(self.signing_key, canonical, hashlib.sha256).hexdigest()
        audit = AuditEvent(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_username=actor_username,
            mailbox_account_id=mailbox_account_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            detail=safe_detail,
            previous_hash=previous_hash,
            event_hash=event_hash,
            create_time=create_time,
        )
        session.add(audit)
        session.flush()
        return audit

    def append_independent(
        self,
        session_factory: sessionmaker[Session],
        **kwargs: Any,
    ) -> AuditEvent:
        with session_factory() as session, session.begin():
            session.info["skip_tenant_scope"] = True
            return self.append(session, **kwargs)

    def verify_tenant_chain(self, session: Session, *, tenant_id: int) -> tuple[bool, int | None]:
        """校验指定租户的审计哈希链，返回是否完整及首个异常事件 ID。"""

        previous_hash = "0" * 64
        events = session.scalars(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == tenant_id)
            .order_by(AuditEvent.id)
            .execution_options(skip_tenant_scope=True)
        )
        for item in events:
            if item.previous_hash != previous_hash:
                return False, item.id
            canonical = _canonical_event(
                tenant_id=item.tenant_id,
                actor_user_id=item.actor_user_id,
                actor_username=item.actor_username,
                mailbox_account_id=item.mailbox_account_id,
                action=item.action,
                resource_type=item.resource_type,
                resource_id=item.resource_id,
                outcome=item.outcome,
                request_id=item.request_id,
                ip_address=item.ip_address,
                user_agent=item.user_agent,
                create_time=item.create_time,
                detail=item.detail,
                previous_hash=item.previous_hash,
            )
            expected = hmac.new(self.signing_key, canonical, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, item.event_hash):
                return False, item.id
            previous_hash = item.event_hash
        return True, None


def _canonical_event(**fields: Any) -> bytes:
    payload = dict(fields)
    payload["create_time"] = fields["create_time"].isoformat()
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sanitize(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).casefold()
            result[str(key)] = (
                "[REDACTED]"
                if any(marker in normalized for marker in _REDACTED_KEYS)
                else _sanitize(item)
            )
        return result
    if isinstance(value, (list, tuple, set)):
        return [_sanitize(item) for item in value]
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return str(value)
