from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import AppUser, AuditEvent, TenantMembership, UserRole
from app.db.session import get_database_manager
from app.services.auth_service import AuthService
from app.services.foundation_service import FoundationService

pytestmark = pytest.mark.anyio


def _seed_platform_admin() -> tuple[int, int]:
    manager = get_database_manager()
    with manager.session_factory() as session, session.begin():
        foundation = FoundationService(get_settings()).ensure(session)
        user = AuthService().create_user(
            session,
            username="platform_admin",
            password="PlatformAdmin!2026",
            role=UserRole.ADMIN,
            tenant_id=foundation.tenant_id,
            is_platform_admin=True,
        )
        return user.id, foundation.tenant_id


async def test_tenant_creation_login_selection_and_switch_are_closed_loop(app: FastAPI) -> None:
    platform_user_id, default_tenant_id = _seed_platform_admin()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        first_login = await client.post(
            "/api/v1/auth/login",
            json={"username": "platform_admin", "password": "PlatformAdmin!2026"},
        )
        created = await client.post(
            "/api/v1/tenants",
            json={"code": "qianguo", "name": "千果私募"},
        )
        qianguo_id = created.json()["id"]
        member = await client.post(
            f"/api/v1/tenants/{qianguo_id}/members",
            json={
                "username": "qianguo_operator",
                "password": "QianguoUser!2026",
                "role": "operator",
            },
        )
        await client.post("/api/v1/auth/logout")

        selection = await client.post(
            "/api/v1/auth/login",
            json={"username": "platform_admin", "password": "PlatformAdmin!2026"},
        )
        unauthenticated_after_selection = await client.get("/api/v1/auth/me")
        selected_login = await client.post(
            "/api/v1/auth/login",
            json={
                "username": "platform_admin",
                "password": "PlatformAdmin!2026",
                "tenant_id": qianguo_id,
            },
        )
        available = await client.get("/api/v1/auth/tenants")
        switched = await client.post(
            "/api/v1/auth/switch-tenant",
            json={"tenant_id": default_tenant_id},
        )
        current = await client.get("/api/v1/auth/me")

    assert first_login.status_code == 200
    assert created.status_code == 201
    assert created.json()["code"] == "qianguo"
    assert created.json()["is_current"] is False
    assert member.status_code == 201
    assert member.json()["username"] == "qianguo_operator"
    assert selection.status_code == 200
    assert selection.json()["requires_tenant_selection"] is True
    assert selection.json()["user"] is None
    assert {item["name"] for item in selection.json()["tenants"]} == {
        "默认业务账套",
        "千果私募",
    }
    assert unauthenticated_after_selection.status_code == 401
    assert selected_login.status_code == 200
    assert selected_login.json()["user"]["tenant_id"] == qianguo_id
    assert sum(item["is_current"] for item in available.json()) == 1
    assert switched.status_code == 200
    assert current.json()["tenant_id"] == default_tenant_id

    with get_database_manager().session_factory() as session:
        actions = set(
            session.scalars(
                select(AuditEvent.action)
                .where(AuditEvent.actor_user_id == platform_user_id)
                .execution_options(skip_tenant_scope=True)
            )
        )
    assert {
        "tenant.create",
        "tenant.member.create",
        "auth.tenant.switch_out",
        "auth.tenant.switch_in",
    }.issubset(actions)


async def test_tenant_admin_permissions_and_last_admin_guard(app: FastAPI) -> None:
    platform_user_id, default_tenant_id = _seed_platform_admin()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        await client.post(
            "/api/v1/auth/login",
            json={"username": "platform_admin", "password": "PlatformAdmin!2026"},
        )
        tenant = (
            await client.post(
                "/api/v1/tenants",
                json={"code": "jiyu", "name": "吉余私募"},
            )
        ).json()
        jiyu_id = tenant["id"]
        new_admin = await client.post(
            f"/api/v1/tenants/{jiyu_id}/members",
            json={
                "username": "jiyu_admin",
                "password": "JiyuAdmin!2026",
                "role": "admin",
            },
        )
        with get_database_manager().session_factory() as session, session.begin():
            AuthService().create_user(
                session,
                username="shared_identity",
                password="SharedIdentity!2026",
                role=UserRole.VIEWER,
                tenant_id=default_tenant_id,
                is_platform_admin=False,
            )
        await client.post("/api/v1/auth/logout")
        tenant_admin_login = await client.post(
            "/api/v1/auth/login",
            json={"username": "jiyu_admin", "password": "JiyuAdmin!2026"},
        )
        forbidden_create = await client.post(
            "/api/v1/tenants",
            json={"code": "blocked", "name": "不能创建"},
        )
        own_tenant_list = await client.get("/api/v1/tenants")
        own_member = await client.post(
            f"/api/v1/tenants/{jiyu_id}/members",
            json={
                "username": "jiyu_viewer",
                "password": "JiyuViewer!2026",
                "role": "viewer",
            },
        )
        forbidden_cross_tenant_identity = await client.post(
            f"/api/v1/tenants/{jiyu_id}/members",
            json={"username": "shared_identity", "role": "viewer"},
        )
        other_tenant_members = await client.get(f"/api/v1/tenants/{default_tenant_id}/members")
        last_admin = await client.put(
            f"/api/v1/tenants/{jiyu_id}/members/{new_admin.json()['user_id']}",
            json={"role": "viewer", "is_active": False},
        )

    assert tenant_admin_login.status_code == 200
    assert tenant_admin_login.json()["user"]["is_platform_admin"] is False
    assert forbidden_create.status_code == 403
    assert [item["id"] for item in own_tenant_list.json()] == [jiyu_id]
    assert own_member.status_code == 201
    assert forbidden_cross_tenant_identity.status_code == 403
    assert other_tenant_members.status_code == 403
    # 平台管理员也是该新租户的管理员，因此此时仍可撤销当前租户管理员。
    assert last_admin.status_code == 200
    assert platform_user_id != new_admin.json()["user_id"]


async def test_rejects_removing_the_only_tenant_admin(app: FastAPI) -> None:
    platform_user_id, _ = _seed_platform_admin()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        await client.post(
            "/api/v1/auth/login",
            json={"username": "platform_admin", "password": "PlatformAdmin!2026"},
        )
        only_admin = await client.put(
            f"/api/v1/tenants/1/members/{platform_user_id}",
            json={"role": "viewer", "is_active": False},
        )

    assert only_admin.status_code == 409
    assert only_admin.json()["error"]["code"] == "TENANT_LAST_ADMIN"


async def test_member_validation_and_permissions_fail_closed(app: FastAPI) -> None:
    _, default_tenant_id = _seed_platform_admin()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        await client.post(
            "/api/v1/auth/login",
            json={"username": "platform_admin", "password": "PlatformAdmin!2026"},
        )
        operator = await client.post(
            f"/api/v1/tenants/{default_tenant_id}/members",
            json={
                "username": "tenant_operator",
                "password": "TenantOperator!2026",
                "role": "operator",
            },
        )
        short_username = await client.post(
            f"/api/v1/tenants/{default_tenant_id}/members",
            json={"username": " a ", "password": "LongEnough!2026", "role": "viewer"},
        )
        short_password = await client.post(
            f"/api/v1/tenants/{default_tenant_id}/members",
            json={"username": "valid_viewer", "password": "12345", "role": "viewer"},
        )
        six_character_password = await client.post(
            f"/api/v1/tenants/{default_tenant_id}/members",
            json={"username": "six_char_viewer", "password": "123456", "role": "viewer"},
        )
        await client.post("/api/v1/auth/logout")
        await client.post(
            "/api/v1/auth/login",
            json={"username": "tenant_operator", "password": "TenantOperator!2026"},
        )
        forbidden = await client.post(
            f"/api/v1/tenants/{default_tenant_id}/members",
            json={
                "username": "must_not_be_created",
                "password": "MustNotExist!2026",
                "role": "admin",
            },
        )

    assert operator.status_code == 201
    assert short_username.status_code == 422
    assert short_password.status_code == 422
    assert six_character_password.status_code == 201
    assert forbidden.status_code == 403
    with get_database_manager().session_factory() as session:
        assert session.scalar(
            select(AppUser).where(AppUser.username == "must_not_be_created")
        ) is None
        assert session.scalar(
            select(TenantMembership)
            .join(AppUser, TenantMembership.user_id == AppUser.id)
            .where(AppUser.username == "must_not_be_created")
            .execution_options(skip_tenant_scope=True)
        ) is None
