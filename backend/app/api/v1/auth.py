"""后台登录、租户选择、安全切换、退出和当前用户接口。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    DatabaseSession,
    TenantScope,
    get_session_token_service,
)
from app.api.schemas.auth import (
    LoginRequest,
    LoginResponse,
    TenantOption,
    TenantSwitchRequest,
    UserResponse,
)
from app.core.config import get_settings
from app.core.credential_security import audit_signing_key
from app.core.errors import AppError
from app.core.security import SessionTokenService
from app.db.models import AppUser, Tenant, TenantMembership
from app.db.session import get_database_manager
from app.services.audit_service import AuditService
from app.services.auth_service import AuthenticationError, AuthService
from app.services.foundation_service import DEFAULT_TENANT_CODE

router = APIRouter()
TokenService = Annotated[SessionTokenService, Depends(get_session_token_service)]


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: DatabaseSession,
    token_service: TokenService,
) -> LoginResponse:
    try:
        user = AuthService().authenticate(
            session,
            username=payload.username,
            password=payload.password,
        )
    except (AuthenticationError, ValueError) as exc:
        _audit_auth(username=payload.username, outcome="failure", request=request)
        raise AppError("LOGIN_FAILED", "用户名或密码错误", status_code=401) from exc

    available = _available_tenants(session, user_id=user.id)
    if not available:
        _audit_auth(username=user.username, outcome="denied", request=request)
        raise AppError("TENANT_UNAVAILABLE", "账号没有可用的业务账套", status_code=403)

    selected = _select_membership(available, payload.tenant_id)
    if payload.tenant_id is not None and selected is None:
        _audit_auth(
            username=user.username,
            outcome="denied",
            request=request,
            tenant_id=available[0][1].id,
            user_id=user.id,
            detail={"requested_tenant_id": payload.tenant_id},
        )
        raise AppError("TENANT_ACCESS_DENIED", "无权进入指定业务账套", status_code=403)

    if selected is None and len(available) > 1:
        _clear_session_cookie(response)
        _audit_auth(
            username=user.username,
            outcome="selection_required",
            request=request,
            tenant_id=available[0][1].id,
            user_id=user.id,
            action="auth.tenant.select",
            detail={"available_tenant_count": len(available)},
        )
        return LoginResponse(
            requires_tenant_selection=True,
            tenants=[_tenant_option(membership, tenant) for membership, tenant in available],
        )

    membership, tenant = selected or available[0]
    now = datetime.now(UTC)
    user.last_login_at = now
    session.commit()
    _set_session_cookie(
        response,
        token_service.create(
            user_id=user.id,
            username=user.username,
            token_version=user.token_version,
            tenant_id=tenant.id,
            now=now,
        ),
    )
    _audit_auth(
        username=user.username,
        outcome="success",
        request=request,
        tenant_id=tenant.id,
        user_id=user.id,
    )
    return _login_response(user, membership, tenant, token_service, now)


@router.get("/tenants", response_model=list[TenantOption])
def available_tenants(
    session: DatabaseSession,
    scope: TenantScope,
) -> list[TenantOption]:
    return [
        _tenant_option(membership, tenant, current_id=scope.tenant_id)
        for membership, tenant in _available_tenants(session, user_id=scope.user.id)
    ]


@router.post("/switch-tenant", response_model=LoginResponse)
def switch_tenant(
    payload: TenantSwitchRequest,
    request: Request,
    response: Response,
    session: DatabaseSession,
    scope: TenantScope,
    token_service: TokenService,
) -> LoginResponse:
    available = _available_tenants(session, user_id=scope.user.id)
    selected = _select_membership(available, payload.tenant_id)
    if selected is None:
        _audit_auth(
            username=scope.user.username,
            outcome="denied",
            request=request,
            tenant_id=scope.tenant_id,
            user_id=scope.user.id,
            action="auth.tenant.switch",
            detail={"target_tenant_id": payload.tenant_id},
        )
        raise AppError("TENANT_ACCESS_DENIED", "无权切换到指定业务账套", status_code=403)

    membership, tenant = selected
    now = datetime.now(UTC)
    _set_session_cookie(
        response,
        token_service.create(
            user_id=scope.user.id,
            username=scope.user.username,
            token_version=scope.user.token_version,
            tenant_id=tenant.id,
            now=now,
        ),
    )
    detail = {"from_tenant_id": scope.tenant_id, "to_tenant_id": tenant.id}
    _audit_auth(
        username=scope.user.username,
        outcome="success",
        request=request,
        tenant_id=scope.tenant_id,
        user_id=scope.user.id,
        action="auth.tenant.switch_out",
        detail=detail,
    )
    if tenant.id != scope.tenant_id:
        _audit_auth(
            username=scope.user.username,
            outcome="success",
            request=request,
            tenant_id=tenant.id,
            user_id=scope.user.id,
            action="auth.tenant.switch_in",
            detail=detail,
        )
    return _login_response(scope.user, membership, tenant, token_service, now)


@router.post("/logout", status_code=204)
def logout(response: Response, request: Request, scope: TenantScope) -> None:
    _clear_session_cookie(response)
    _audit_auth(
        username=scope.user.username,
        outcome="success",
        request=request,
        tenant_id=scope.tenant_id,
        user_id=scope.user.id,
        action="auth.logout",
    )


@router.get("/me", response_model=UserResponse)
def current_user(scope: TenantScope) -> UserResponse:
    return UserResponse(
        id=scope.user.id,
        username=scope.user.username,
        role=scope.role,
        tenant_id=scope.tenant_id,
        tenant_code=scope.tenant_code,
        tenant_name=scope.tenant_name,
        is_platform_admin=scope.user.is_platform_admin,
    )


def _available_tenants(
    session: Session,
    *,
    user_id: int,
) -> list[tuple[TenantMembership, Tenant]]:
    statement = (
        select(TenantMembership, Tenant)
        .join(Tenant, TenantMembership.tenant_id == Tenant.id)
        .where(
            TenantMembership.user_id == user_id,
            TenantMembership.is_active.is_(True),
            Tenant.is_active.is_(True),
        )
        .order_by(Tenant.name, Tenant.id)
        .execution_options(skip_tenant_scope=True)
    )
    return list(session.execute(statement))


def _select_membership(
    available: list[tuple[TenantMembership, Tenant]],
    tenant_id: int | None,
) -> tuple[TenantMembership, Tenant] | None:
    if tenant_id is None:
        return available[0] if len(available) == 1 else None
    return next((item for item in available if item[1].id == tenant_id), None)


def _tenant_option(
    membership: TenantMembership,
    tenant: Tenant,
    *,
    current_id: int | None = None,
) -> TenantOption:
    return TenantOption(
        id=tenant.id,
        code=tenant.code,
        name=tenant.name,
        role=membership.role,
        is_current=tenant.id == current_id,
    )


def _login_response(
    user: AppUser,
    membership: TenantMembership,
    tenant: Tenant,
    token_service: SessionTokenService,
    now: datetime,
) -> LoginResponse:
    return LoginResponse(
        user=UserResponse(
            id=user.id,
            username=user.username,
            role=membership.role,
            tenant_id=tenant.id,
            tenant_code=tenant.code,
            tenant_name=tenant.name,
            is_platform_admin=user.is_platform_admin,
        ),
        expires_at=(now + token_service.ttl).isoformat(),
    )


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.security.session_cookie_name,
        value=token,
        max_age=settings.security.session_ttl_minutes * 60,
        httponly=True,
        secure=settings.security.secure_cookie,
        samesite="strict",
        path=settings.app.api_prefix,
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.security.session_cookie_name,
        path=settings.app.api_prefix,
        secure=settings.security.secure_cookie,
        httponly=True,
        samesite="strict",
    )


def _audit_auth(
    *,
    username: str,
    outcome: str,
    request: Request,
    tenant_id: int | None = None,
    user_id: int | None = None,
    action: str = "auth.login",
    detail: dict[str, Any] | None = None,
) -> None:
    settings = get_settings()
    manager = get_database_manager()
    if tenant_id is None:
        with manager.session_factory() as session:
            tenant_id = session.scalar(
                select(Tenant.id).where(Tenant.code == DEFAULT_TENANT_CODE)
            )
    if tenant_id is None:
        return
    AuditService(audit_signing_key(settings.security)).append_independent(
        manager.session_factory,
        tenant_id=tenant_id,
        actor_user_id=user_id,
        actor_username=username.strip().casefold()[:100] or "unknown",
        action=action,
        resource_type="session",
        outcome=outcome,
        detail=detail,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
