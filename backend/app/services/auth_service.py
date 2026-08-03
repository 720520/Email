"""本地管理后台认证服务。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.security import PasswordHasher
from app.db.models import AppUser, UserRole
from app.repositories import UserRepository


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

    def create_user(
        self,
        session: Session,
        *,
        username: str,
        password: str,
        role: UserRole,
    ) -> AppUser:
        normalized_username = normalize_username(username)
        if self.repository.find_by_username(session, normalized_username) is not None:
            raise ValueError("用户名已存在")
        user = AppUser(
            username=normalized_username,
            password_hash=self.password_hasher.hash(password),
            role=role,
            is_active=True,
        )
        session.add(user)
        session.flush()
        return user


def normalize_username(username: str) -> str:
    normalized = username.strip().casefold()
    if not 3 <= len(normalized) <= 100:
        raise ValueError("用户名长度必须在 3 到 100 个字符之间")
    return normalized
