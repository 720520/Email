"""公共 API 依赖导出。"""

from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import InvalidSessionTokenError, SessionClaims, SessionTokenService
from app.db.models import (
    AppUser,
    MailboxUserGrant,
    Tenant,
    TenantMembership,
    UserRole,
)
from app.db.session import configure_tenant_scope, get_database_manager, get_db_session

DatabaseSession = Annotated[Session, Depends(get_db_session)]


@dataclass(frozen=True, slots=True)
class TenantContext:
    user: AppUser
    tenant_id: int
    tenant_code: str
    tenant_name: str
    role: UserRole
    mailbox_ids: tuple[int, ...]
    content_mailbox_ids: tuple[int, ...]
    operable_mailbox_ids: tuple[int, ...]
    manageable_mailbox_ids: tuple[int, ...]

    def can_read_content(self, mailbox_id: int) -> bool:
        return mailbox_id in self.content_mailbox_ids

    def can_operate(self, mailbox_id: int) -> bool:
        return mailbox_id in self.operable_mailbox_ids


def get_session_token_service() -> SessionTokenService:
    settings = get_settings()
    return SessionTokenService(
        settings.security.secret_key.get_secret_value(),
        ttl_minutes=settings.security.session_ttl_minutes,
    )


def get_session_claims(request: Request) -> SessionClaims:
    settings = get_settings()
    token = request.cookies.get(settings.security.session_cookie_name)
    if not token:
        raise AppError("AUTH_REQUIRED", "请先登录", status_code=401)
    try:
        return get_session_token_service().verify(token)
    except InvalidSessionTokenError as exc:
        raise AppError("SESSION_INVALID", "登录状态已失效，请重新登录", status_code=401) from exc


SessionClaimsDependency = Annotated[SessionClaims, Depends(get_session_claims)]


def get_current_user(
    request: Request,
    session: DatabaseSession,
    claims: SessionClaimsDependency,
) -> AppUser:
    del request
    user = session.get(AppUser, claims.user_id)
    if (
        user is None
        or not user.is_active
        or user.username != claims.username
        or user.token_version != claims.token_version
    ):
        raise AppError("SESSION_INVALID", "登录状态已失效，请重新登录", status_code=401)
    return user


CurrentUser = Annotated[AppUser, Depends(get_current_user)]


def get_tenant_context(
    session: DatabaseSession,
    user: CurrentUser,
    claims: SessionClaimsDependency,
) -> TenantContext:
    membership = session.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == claims.tenant_id,
            TenantMembership.user_id == user.id,
            TenantMembership.is_active.is_(True),
        ).execution_options(skip_tenant_scope=True)
    )
    tenant = session.get(Tenant, claims.tenant_id)
    if membership is None or tenant is None or not tenant.is_active:
        raise AppError("TENANT_ACCESS_REVOKED", "当前业务账套授权已失效", status_code=401)
    grants = list(
        session.scalars(
            select(MailboxUserGrant).where(
                MailboxUserGrant.tenant_id == claims.tenant_id,
                MailboxUserGrant.user_id == user.id,
                MailboxUserGrant.is_active.is_(True),
            ).execution_options(skip_tenant_scope=True)
        )
    )
    return TenantContext(
        user=user,
        tenant_id=claims.tenant_id,
        tenant_code=tenant.code,
        tenant_name=tenant.name,
        role=membership.role,
        mailbox_ids=tuple(
            sorted(item.mailbox_account_id for item in grants if item.can_read_metadata)
        ),
        content_mailbox_ids=tuple(
            sorted(item.mailbox_account_id for item in grants if item.can_read_content)
        ),
        operable_mailbox_ids=tuple(
            sorted(item.mailbox_account_id for item in grants if item.can_operate)
        ),
        manageable_mailbox_ids=tuple(
            sorted(item.mailbox_account_id for item in grants if item.can_manage_credentials)
        ),
    )


TenantScope = Annotated[TenantContext, Depends(get_tenant_context)]


def get_tenant_db_session(scope: TenantScope) -> Generator[Session, None, None]:
    session = get_database_manager().session_factory()
    configure_tenant_scope(
        session,
        tenant_id=scope.tenant_id,
        mailbox_ids=scope.mailbox_ids,
    )
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


TenantDatabaseSession = Annotated[Session, Depends(get_tenant_db_session)]


def require_roles(*roles: UserRole) -> Callable[..., TenantContext]:
    def dependency(scope: TenantScope) -> TenantContext:
        if scope.role not in roles:
            raise AppError("FORBIDDEN", "当前账号没有执行此操作的权限", status_code=403)
        return scope

    return dependency
