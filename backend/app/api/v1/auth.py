"""后台登录、退出和当前用户接口。"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.deps import CurrentUser, DatabaseSession, get_session_token_service
from app.api.schemas.auth import LoginRequest, LoginResponse, UserResponse
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import SessionTokenService
from app.services.auth_service import AuthenticationError, AuthService

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    response: Response,
    session: DatabaseSession,
    token_service: Annotated[SessionTokenService, Depends(get_session_token_service)],
) -> LoginResponse:
    try:
        user = AuthService().authenticate(
            session,
            username=payload.username,
            password=payload.password,
        )
    except (AuthenticationError, ValueError) as exc:
        raise AppError("LOGIN_FAILED", "用户名或密码错误", status_code=401) from exc

    now = datetime.now(UTC)
    user.last_login_at = now
    session.commit()
    token = token_service.create(
        user_id=user.id,
        username=user.username,
        token_version=user.token_version,
        now=now,
    )
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
    return LoginResponse(
        user=UserResponse(id=user.id, username=user.username, role=user.role),
        expires_at=(now + token_service.ttl).isoformat(),
    )


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.security.session_cookie_name,
        path=settings.app.api_prefix,
        secure=settings.security.secure_cookie,
        httponly=True,
        samesite="strict",
    )


@router.get("/me", response_model=UserResponse)
def current_user(user: CurrentUser) -> UserResponse:
    return UserResponse(id=user.id, username=user.username, role=user.role)
