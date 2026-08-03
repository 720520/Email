"""公共 API 依赖导出。"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import InvalidSessionTokenError, SessionTokenService
from app.db.models import AppUser, UserRole
from app.db.session import get_db_session

DatabaseSession = Annotated[Session, Depends(get_db_session)]


def get_session_token_service() -> SessionTokenService:
    settings = get_settings()
    return SessionTokenService(
        settings.security.secret_key.get_secret_value(),
        ttl_minutes=settings.security.session_ttl_minutes,
    )


def get_current_user(
    request: Request,
    session: DatabaseSession,
) -> AppUser:
    settings = get_settings()
    token = request.cookies.get(settings.security.session_cookie_name)
    if not token:
        raise AppError("AUTH_REQUIRED", "请先登录", status_code=401)
    try:
        claims = get_session_token_service().verify(token)
    except InvalidSessionTokenError as exc:
        raise AppError("SESSION_INVALID", "登录状态已失效，请重新登录", status_code=401) from exc

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


def require_roles(*roles: UserRole) -> Callable[..., AppUser]:
    def dependency(user: CurrentUser) -> AppUser:
        if user.role not in roles:
            raise AppError("FORBIDDEN", "当前账号没有执行此操作的权限", status_code=403)
        return user

    return dependency
