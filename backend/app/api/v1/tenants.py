"""租户创建、停用和用户成员关系管理。"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import DatabaseSession, TenantContext, TenantScope
from app.api.schemas.tenant import (
    TenantCreate,
    TenantMemberCreate,
    TenantMemberItem,
    TenantMemberUpdate,
    TenantSummary,
    TenantUpdate,
)
from app.core.config import get_settings
from app.core.credential_security import audit_signing_key, dedicated_audit_key_configured
from app.core.errors import AppError
from app.db.models import (
    AppUser,
    MailboxAccount,
    Tenant,
    TenantMembership,
    UserRole,
)
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService, normalize_username
from app.services.profile_service import ProfileService

router = APIRouter()


@router.get("", response_model=list[TenantSummary])
def list_tenants(
    session: DatabaseSession,
    scope: TenantScope,
) -> list[TenantSummary]:
    _require_tenant_admin(scope)
    memberships = {
        membership.tenant_id: membership
        for membership in session.scalars(
            select(TenantMembership)
            .where(TenantMembership.user_id == scope.user.id)
            .execution_options(skip_tenant_scope=True)
        )
    }
    conditions = []
    if not scope.user.is_platform_admin:
        conditions.append(Tenant.id == scope.tenant_id)
    tenants = list(session.scalars(select(Tenant).where(*conditions).order_by(Tenant.name)))
    return [
        _tenant_summary(
            session,
            tenant,
            memberships.get(tenant.id),
            scope=scope,
        )
        for tenant in tenants
    ]


@router.post("", response_model=TenantSummary, status_code=201)
def create_tenant(
    payload: TenantCreate,
    request: Request,
    session: DatabaseSession,
    scope: TenantScope,
) -> TenantSummary:
    _require_platform_admin(scope)
    _require_audit_key()
    with _unscoped(session):
        exists = session.scalar(select(Tenant.id).where(Tenant.code == payload.code))
        if exists is not None:
            raise AppError("TENANT_CODE_EXISTS", "租户代码已存在", status_code=409)
        tenant = Tenant(code=payload.code, name=payload.name.strip(), is_active=True)
        session.add(tenant)
        session.flush()
        ProfileService.ensure_organization(
            session,
            tenant,
            created_by_user_id=scope.user.id,
        )
        membership = TenantMembership(
            tenant_id=tenant.id,
            user_id=scope.user.id,
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(membership)
        session.flush()
        _audit(
            session,
            scope,
            request,
            tenant_id=tenant.id,
            action="tenant.create",
            resource_type="tenant",
            resource_id=tenant.id,
            detail={"code": tenant.code, "name": tenant.name},
        )
        session.flush()
    session.commit()
    return _tenant_summary(session, tenant, membership, scope=scope)


@router.patch("/{tenant_id}", response_model=TenantSummary)
def update_tenant(
    tenant_id: int,
    payload: TenantUpdate,
    request: Request,
    session: DatabaseSession,
    scope: TenantScope,
) -> TenantSummary:
    _require_platform_admin(scope)
    _require_audit_key()
    if payload.is_active is False and tenant_id == scope.tenant_id:
        raise AppError(
            "TENANT_CURRENT_DEACTIVATE",
            "请先切换到其他租户，再停用当前租户",
            status_code=409,
        )
    with _unscoped(session):
        tenant = session.get(Tenant, tenant_id)
        if tenant is None:
            raise AppError("TENANT_NOT_FOUND", "租户不存在", status_code=404)
        changed: list[str] = []
        if payload.name is not None:
            tenant.name = payload.name.strip()
            changed.append("name")
        if payload.is_active is not None:
            tenant.is_active = payload.is_active
            changed.append("is_active")
        _audit(
            session,
            scope,
            request,
            tenant_id=tenant.id,
            action="tenant.update",
            resource_type="tenant",
            resource_id=tenant.id,
            detail={"changed_fields": changed},
        )
        session.flush()
    session.commit()
    membership = session.scalar(
        select(TenantMembership)
        .where(
            TenantMembership.tenant_id == tenant.id,
            TenantMembership.user_id == scope.user.id,
        )
        .execution_options(skip_tenant_scope=True)
    )
    return _tenant_summary(session, tenant, membership, scope=scope)


@router.get("/{tenant_id}/members", response_model=list[TenantMemberItem])
def list_tenant_members(
    tenant_id: int,
    session: DatabaseSession,
    scope: TenantScope,
) -> list[TenantMemberItem]:
    _assert_tenant_manager(session, scope, tenant_id)
    statement = (
        select(TenantMembership, AppUser)
        .join(AppUser, TenantMembership.user_id == AppUser.id)
        .where(TenantMembership.tenant_id == tenant_id)
        .order_by(AppUser.username)
        .execution_options(skip_tenant_scope=True)
    )
    return [_member_item(membership, user) for membership, user in session.execute(statement)]


@router.post("/{tenant_id}/members", response_model=TenantMemberItem, status_code=201)
def create_tenant_member(
    tenant_id: int,
    payload: TenantMemberCreate,
    request: Request,
    session: DatabaseSession,
    scope: TenantScope,
) -> TenantMemberItem:
    _assert_tenant_manager(session, scope, tenant_id)
    _require_audit_key()
    username = normalize_username(payload.username)
    with _unscoped(session):
        tenant = session.get(Tenant, tenant_id)
        if tenant is None or not tenant.is_active:
            raise AppError("TENANT_NOT_FOUND", "租户不存在或已停用", status_code=404)
        user = session.scalar(select(AppUser).where(AppUser.username == username))
        created_identity = user is None
        if user is None:
            if payload.password is None:
                raise AppError(
                    "MEMBER_PASSWORD_REQUIRED",
                    "新用户必须设置初始密码",
                    status_code=422,
                )
            user = AuthService().create_identity(
                session,
                username=username,
                password=payload.password.get_secret_value(),
                role=payload.role,
                is_platform_admin=False,
            )
        elif not scope.user.is_platform_admin:
            raise AppError(
                "MEMBER_IDENTITY_REQUIRES_PLATFORM",
                "该用户名已在系统注册，请由平台管理员建立跨租户成员关系",
                status_code=403,
            )
        elif not user.is_active:
            raise AppError("USER_DISABLED", "该登录用户已停用", status_code=409)
        existing = session.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == user.id,
            )
        )
        if existing is not None:
            raise AppError("MEMBERSHIP_EXISTS", "用户已属于该租户", status_code=409)
        membership = TenantMembership(
            tenant_id=tenant_id,
            user_id=user.id,
            role=payload.role,
            is_active=True,
        )
        session.add(membership)
        session.flush()
        _audit(
            session,
            scope,
            request,
            tenant_id=tenant_id,
            action="tenant.member.create",
            resource_type="tenant_membership",
            resource_id=membership.id,
            detail={
                "target_user_id": user.id,
                "role": payload.role.value,
                "created_identity": created_identity,
            },
        )
        session.flush()
    session.commit()
    return _member_item(membership, user)


@router.put("/{tenant_id}/members/{user_id}", response_model=TenantMemberItem)
def update_tenant_member(
    tenant_id: int,
    user_id: int,
    payload: TenantMemberUpdate,
    request: Request,
    session: DatabaseSession,
    scope: TenantScope,
) -> TenantMemberItem:
    _assert_tenant_manager(session, scope, tenant_id)
    _require_audit_key()
    with _unscoped(session):
        membership = session.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == user_id,
            )
        )
        user = session.get(AppUser, user_id)
        if membership is None or user is None:
            raise AppError("MEMBERSHIP_NOT_FOUND", "租户成员不存在", status_code=404)
        removes_admin = (
            membership.is_active
            and membership.role == UserRole.ADMIN
            and (not payload.is_active or payload.role != UserRole.ADMIN)
        )
        if removes_admin and _active_admin_count(session, tenant_id, exclude_user_id=user_id) == 0:
            raise AppError(
                "TENANT_LAST_ADMIN",
                "必须先设置另一名租户管理员",
                status_code=409,
            )
        membership.role = payload.role
        membership.is_active = payload.is_active
        user.token_version += 1
        _audit(
            session,
            scope,
            request,
            tenant_id=tenant_id,
            action="tenant.member.update",
            resource_type="tenant_membership",
            resource_id=membership.id,
            detail={
                "target_user_id": user.id,
                "role": payload.role.value,
                "is_active": payload.is_active,
            },
        )
        session.flush()
    session.commit()
    return _member_item(membership, user)


def _tenant_summary(
    session: Session,
    tenant: Tenant,
    membership: TenantMembership | None,
    *,
    scope: TenantContext,
) -> TenantSummary:
    member_count = (
        session.scalar(
            select(func.count(TenantMembership.id))
            .where(
                TenantMembership.tenant_id == tenant.id,
                TenantMembership.is_active.is_(True),
            )
            .execution_options(skip_tenant_scope=True)
        )
        or 0
    )
    mailbox_count = (
        session.scalar(
            select(func.count(MailboxAccount.id))
            .where(MailboxAccount.tenant_id == tenant.id)
            .execution_options(skip_tenant_scope=True)
        )
        or 0
    )
    can_manage = scope.user.is_platform_admin or bool(
        membership and membership.is_active and membership.role == UserRole.ADMIN
    )
    return TenantSummary(
        id=tenant.id,
        code=tenant.code,
        name=tenant.name,
        is_active=tenant.is_active,
        current_user_role=membership.role if membership and membership.is_active else None,
        is_current=tenant.id == scope.tenant_id,
        can_manage=can_manage,
        member_count=member_count,
        mailbox_count=mailbox_count,
        create_time=tenant.create_time,
    )


def _member_item(membership: TenantMembership, user: AppUser) -> TenantMemberItem:
    return TenantMemberItem(
        membership_id=membership.id,
        user_id=user.id,
        username=user.username,
        role=membership.role,
        is_active=membership.is_active,
        user_is_active=user.is_active,
        is_platform_admin=user.is_platform_admin,
        create_time=membership.create_time,
    )


def _require_tenant_admin(scope: TenantContext) -> None:
    if scope.role != UserRole.ADMIN and not scope.user.is_platform_admin:
        raise AppError("FORBIDDEN", "当前账号没有租户管理权限", status_code=403)


def _require_platform_admin(scope: TenantContext) -> None:
    if not scope.user.is_platform_admin:
        raise AppError("FORBIDDEN", "只有平台管理员可以创建或停用租户", status_code=403)


def _assert_tenant_manager(
    session: Session,
    scope: TenantContext,
    tenant_id: int,
) -> None:
    if scope.user.is_platform_admin:
        return
    membership = session.scalar(
        select(TenantMembership)
        .where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == scope.user.id,
            TenantMembership.role == UserRole.ADMIN,
            TenantMembership.is_active.is_(True),
        )
        .execution_options(skip_tenant_scope=True)
    )
    if membership is None:
        raise AppError("FORBIDDEN", "当前账号不是该租户管理员", status_code=403)


def _active_admin_count(
    session: Session,
    tenant_id: int,
    *,
    exclude_user_id: int,
) -> int:
    return (
        session.scalar(
            select(func.count(TenantMembership.id)).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id != exclude_user_id,
                TenantMembership.role == UserRole.ADMIN,
                TenantMembership.is_active.is_(True),
            )
        )
        or 0
    )


def _require_audit_key() -> None:
    if not dedicated_audit_key_configured(get_settings().security):
        raise AppError(
            "AUDIT_SECURITY_NOT_READY",
            "请先配置独立审计签名密钥",
            status_code=503,
        )


@contextmanager
def _unscoped(session: Session):
    previous = session.info.get("skip_tenant_scope")
    session.info["skip_tenant_scope"] = True
    try:
        yield
    finally:
        if previous is None:
            session.info.pop("skip_tenant_scope", None)
        else:
            session.info["skip_tenant_scope"] = previous


def _audit(
    session: Session,
    scope: TenantContext,
    request: Request,
    *,
    tenant_id: int,
    action: str,
    resource_type: str,
    resource_id: int,
    detail: dict[str, Any],
) -> None:
    AuditService(audit_signing_key(get_settings().security)).append(
        session,
        tenant_id=tenant_id,
        actor_user_id=scope.user.id,
        actor_username=scope.user.username,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome="success",
        detail=detail,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
