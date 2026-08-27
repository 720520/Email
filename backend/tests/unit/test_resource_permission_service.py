from __future__ import annotations

from app.api.deps import TenantContext
from app.core.config import get_settings
from app.db.models import ResourceGrant, UserRole
from app.db.session import configure_tenant_scope, get_database_manager
from app.services.auth_service import AuthService
from app.services.foundation_service import FoundationService
from app.services.resource_permission_service import (
    ResourceAction,
    ResourcePermissionService,
    ResourceSensitivity,
)


def _scope(user, tenant_id: int, role: UserRole) -> TenantContext:
    return TenantContext(
        user=user,
        tenant_id=tenant_id,
        tenant_code="test",
        tenant_name="合成测试租户",
        role=role,
        mailbox_ids=(),
        content_mailbox_ids=(),
        operable_mailbox_ids=(),
        manageable_mailbox_ids=(),
    )


def test_platform_admin_requires_explicit_sensitive_grant(app) -> None:
    del app
    manager = get_database_manager()
    with manager.session_factory() as session, session.begin():
        foundation = FoundationService(get_settings()).ensure(session)
        user = AuthService().create_user(
            session,
            username="permission_platform",
            password="PermissionPlatform!2026",
            role=UserRole.ADMIN,
            tenant_id=foundation.tenant_id,
            is_platform_admin=True,
        )

    with manager.session_factory() as session, session.begin():
        configure_tenant_scope(session, tenant_id=foundation.tenant_id, mailbox_ids=())
        service = ResourcePermissionService()
        scope = _scope(user, foundation.tenant_id, UserRole.ADMIN)
        assert service.allows(session, scope, ResourceAction.READ) is True
        assert (
            service.allows(
                session,
                scope,
                ResourceAction.DOWNLOAD,
                sensitivity=ResourceSensitivity.HIGHLY_SENSITIVE,
            )
            is False
        )
        session.add(
            ResourceGrant(
                tenant_id=foundation.tenant_id,
                user_id=user.id,
                permissions=["download", "sensitive_read"],
                sensitivity_ceiling="highly_sensitive",
                is_active=True,
                granted_by_user_id=user.id,
            )
        )
        session.flush()
        assert (
            service.allows(
                session,
                scope,
                ResourceAction.DOWNLOAD,
                sensitivity=ResourceSensitivity.HIGHLY_SENSITIVE,
            )
            is True
        )
