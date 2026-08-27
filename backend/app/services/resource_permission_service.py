"""统一资源权限入口；业务模块不得自行拼接角色判断。"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import TenantContext
from app.core.errors import AppError
from app.db.models import ResourceGrant, UserRole


class ResourceAction(StrEnum):
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    APPROVE = "approve"
    DOWNLOAD = "download"
    EXPORT = "export"
    SENSITIVE_READ = "sensitive_read"


class ResourceSensitivity(StrEnum):
    NORMAL = "normal"
    SENSITIVE = "sensitive"
    HIGHLY_SENSITIVE = "highly_sensitive"


_SENSITIVITY_LEVEL = {
    ResourceSensitivity.NORMAL: 0,
    ResourceSensitivity.SENSITIVE: 1,
    ResourceSensitivity.HIGHLY_SENSITIVE: 2,
}


class ResourcePermissionService:
    """默认拒绝的租户资源策略，支持实体级和租户级显式授权。"""

    def require(
        self,
        session: Session,
        scope: TenantContext,
        action: ResourceAction,
        *,
        entity_id: int | None = None,
        sensitivity: ResourceSensitivity = ResourceSensitivity.NORMAL,
    ) -> None:
        if self.allows(
            session,
            scope,
            action,
            entity_id=entity_id,
            sensitivity=sensitivity,
        ):
            return
        raise AppError("RESOURCE_FORBIDDEN", "当前账号没有访问该业务资源的权限", status_code=403)

    def allows(
        self,
        session: Session,
        scope: TenantContext,
        action: ResourceAction,
        *,
        entity_id: int | None = None,
        sensitivity: ResourceSensitivity = ResourceSensitivity.NORMAL,
    ) -> bool:
        grants = list(
            session.scalars(
                select(ResourceGrant).where(
                    ResourceGrant.user_id == scope.user.id,
                    ResourceGrant.is_active.is_(True),
                    or_(ResourceGrant.entity_id == entity_id, ResourceGrant.entity_id.is_(None)),
                )
            )
        )
        if any(self._grant_allows(item, action, sensitivity) for item in grants):
            return True

        # 平台管理员只是平台身份，不自动获得租户敏感资料明文权限。
        if scope.user.is_platform_admin and sensitivity != ResourceSensitivity.NORMAL:
            return False
        if scope.role == UserRole.ADMIN:
            return True
        if scope.role == UserRole.OPERATOR:
            return sensitivity == ResourceSensitivity.NORMAL and action in {
                ResourceAction.READ,
                ResourceAction.CREATE,
                ResourceAction.UPDATE,
                ResourceAction.DOWNLOAD,
            }
        return sensitivity == ResourceSensitivity.NORMAL and action == ResourceAction.READ

    @staticmethod
    def _grant_allows(
        grant: ResourceGrant,
        action: ResourceAction,
        sensitivity: ResourceSensitivity,
    ) -> bool:
        try:
            ceiling = ResourceSensitivity(grant.sensitivity_ceiling)
        except ValueError:
            return False
        return (
            action.value in set(grant.permissions or [])
            and _SENSITIVITY_LEVEL[sensitivity] <= _SENSITIVITY_LEVEL[ceiling]
        )
