from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.db.models import Tenant, UserRole
from app.db.session import get_database_manager
from app.services.auth_service import AuthService
from app.services.foundation_service import FoundationService

pytestmark = pytest.mark.anyio


def _seed_users() -> None:
    manager = get_database_manager()
    with manager.session_factory() as session, session.begin():
        foundation = FoundationService(get_settings()).ensure(session)
        AuthService().create_user(
            session,
            username="filing_admin",
            password="FilingAdmin!2026",
            role=UserRole.ADMIN,
            tenant_id=foundation.tenant_id,
            is_platform_admin=False,
        )
        AuthService().create_user(
            session,
            username="filing_viewer",
            password="FilingViewer!2026",
            role=UserRole.VIEWER,
            tenant_id=foundation.tenant_id,
            is_platform_admin=False,
        )


async def test_legacy_filing_profile_is_read_only_compatible(app: FastAPI) -> None:
    _seed_users()
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as admin,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as viewer,
    ):
        admin_login = await admin.post(
            "/api/v1/auth/login",
            json={"username": "filing_admin", "password": "FilingAdmin!2026"},
        )
        profile = await admin.get("/api/v1/filing-profile")
        update = await admin.put(
            "/api/v1/filing-profile", json={"field_values": {"company_name": "禁止更新"}}
        )
        create = await admin.post(
            "/api/v1/filing-profile/fields",
            json={"label": "禁止新增", "category": "兼容测试", "field_type": "text"},
        )
        first_field_id = profile.json()["fields"][0]["id"]
        patch = await admin.patch(
            f"/api/v1/filing-profile/fields/{first_field_id}",
            json={
                "label": "禁止修改",
                "category": "兼容测试",
                "field_type": "text",
            },
        )
        delete = await admin.delete(f"/api/v1/filing-profile/fields/{first_field_id}")
        upload = await admin.post(
            f"/api/v1/filing-profile/fields/{first_field_id}/files",
            files={"file": ("blocked.txt", b"blocked", "text/plain")},
        )
        viewer_login = await viewer.post(
            "/api/v1/auth/login",
            json={"username": "filing_viewer", "password": "FilingViewer!2026"},
        )
        viewer_profile = await viewer.get("/api/v1/filing-profile")
        exported = await viewer.get("/api/v1/filing-profile/export.txt")

    assert admin_login.status_code == 200
    assert profile.status_code == 200
    assert len(profile.json()["fields"]) >= 40
    assert {update.status_code, create.status_code, patch.status_code, delete.status_code} == {410}
    assert upload.status_code == 410
    assert viewer_login.status_code == 200
    assert viewer_profile.status_code == 200
    assert viewer_profile.json()["can_edit"] is False
    assert exported.status_code == 200


async def test_legacy_filing_field_ids_remain_tenant_isolated(app: FastAPI) -> None:
    _seed_users()
    manager = get_database_manager()
    with manager.session_factory() as session, session.begin():
        session.info["skip_tenant_scope"] = True
        second_tenant = Tenant(code="filing-tenant-2", name="备案测试租户二", is_active=True)
        session.add(second_tenant)
        session.flush()
        AuthService().create_user(
            session,
            username="filing_admin_two",
            password="SyntheticAdmin!2026",
            role=UserRole.ADMIN,
            tenant_id=second_tenant.id,
            is_platform_admin=False,
        )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        await client.post(
            "/api/v1/auth/login",
            json={"username": "filing_admin", "password": "FilingAdmin!2026"},
        )
        first = await client.get("/api/v1/filing-profile")
        await client.post("/api/v1/auth/logout")
        await client.post(
            "/api/v1/auth/login",
            json={"username": "filing_admin_two", "password": "SyntheticAdmin!2026"},
        )
        second = await client.get("/api/v1/filing-profile")
        first_field_id = first.json()["fields"][0]["id"]
        foreign_download = await client.get(
            f"/api/v1/filing-profile/fields/{first_field_id}/files/1/download"
        )

    first_ids = {item["id"] for item in first.json()["fields"]}
    second_ids = {item["id"] for item in second.json()["fields"]}
    assert first_ids.isdisjoint(second_ids)
    assert foreign_download.status_code == 404
