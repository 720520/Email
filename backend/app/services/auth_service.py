"""本地管理后台认证服务。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import PasswordHasher
from app.db.models import (
    AppUser,
    MailboxAccount,
    MailboxUserGrant,
    Tenant,
    TenantMembership,
    UserRole,
)
from app.repositories import UserRepository
from app.services.foundation_service import DEFAULT_TENANT_CODE


class AuthenticationError(ValueError):
    pass


class AuthService:
    def __init__(
        self,
        *,
        repository: UserRepository | None = None,
        password_hasher: PasswordHasher | None = None,
    ) -> None:
        self.repository = repository or UserRepository()
        self.password_hasher = password_hasher or PasswordHasher()

    def authenticate(self, session: Session, *, username: str, password: str) -> AppUser:
        normalized_username = normalize_username(username)
        user = self.repository.find_by_username(session, normalized_username)
        if user is None or not self.password_hasher.verify(password, user.password_hash):
            raise AuthenticationError("用户名或密码错误")
        if not user.is_active:
            raise AuthenticationError("用户名或密码错误")
        return user

    def create_identity(
        self,
        session: Session,
        *,
        username: str,
        password: str,
        role: UserRole,
        is_platform_admin: bool = False,
    ) -> AppUser:
        """只创建全局登录身份，租户成员关系由调用方在同一事务中建立。"""

        normalized_username = normalize_username(username)
        if self.repository.find_by_username(session, normalized_username) is not None:
            raise ValueError("用户名已存在")
        user = AppUser(
            username=normalized_username,
            password_hash=self.password_hasher.hash(password),
            role=role,
            is_platform_admin=is_platform_admin,
            is_active=True,
        )
        session.add(user)
        session.flush()
        return user

    def create_user(
        self,
        session: Session,
        *,
        username: str,
        password: str,
        role: UserRole,
        tenant_id: int | None = None,
        is_platform_admin: bool | None = None,
    ) -> AppUser:
        """创建身份和授权；这是少数允许显式跨安全边界表的初始化入口。"""

        previous_skip = session.info.get("skip_tenant_scope")
        session.info["skip_tenant_scope"] = True
        try:
            user = self._create_user_unscoped(
                session,
                username=username,
                password=password,
                role=role,
                tenant_id=tenant_id,
                is_platform_admin=(
                    role == UserRole.ADMIN
                    if is_platform_admin is None
                    else is_platform_admin
                ),
            )
            session.flush()
            return user
        finally:
            if previous_skip is None:
                session.info.pop("skip_tenant_scope", None)
            else:
                session.info["skip_tenant_scope"] = previous_skip

    def _create_user_unscoped(
        self,
        session: Session,
        *,
        username: str,
        password: str,
        role: UserRole,
        tenant_id: int | None,
        is_platform_admin: bool,
    ) -> AppUser:
        normalized_username = normalize_username(username)
        if self.repository.find_by_username(session, normalized_username) is not None:
            raise ValueError("用户名已存在")
        user = AppUser(
            username=normalized_username,
            password_hash=self.password_hasher.hash(password),
            role=role,
            is_platform_admin=is_platform_admin,
            is_active=True,
        )
        session.add(user)
        session.flush()
        tenant = (
            session.get(Tenant, tenant_id)
            if tenant_id is not None
            else session.scalar(select(Tenant).where(Tenant.code == DEFAULT_TENANT_CODE))
        )
        if tenant is None or not tenant.is_active:
            raise ValueError("默认业务账套不存在，请先执行数据库迁移")
        session.add(
            TenantMembership(
                tenant_id=tenant.id,
                user_id=user.id,
                role=role,
                is_active=True,
            )
        )
        mailbox = session.scalar(
            select(MailboxAccount).where(
                MailboxAccount.tenant_id == tenant.id,
                MailboxAccount.is_default.is_(True),
            )
        )
        if mailbox is not None:
            session.add(
                MailboxUserGrant(
                    tenant_id=tenant.id,
                    mailbox_account_id=mailbox.id,
                    user_id=user.id,
                    can_read_metadata=True,
                    can_read_content=True,
                    can_operate=role in {UserRole.ADMIN, UserRole.OPERATOR},
                    can_manage_credentials=role == UserRole.ADMIN,
                    is_active=True,
                )
            )
        return user


def normalize_username(username: str) -> str:
    normalized = username.strip().casefold()
    if not 3 <= len(normalized) <= 100:
        raise ValueError("用户名长度必须在 3 到 100 个字符之间")
    return normalized
