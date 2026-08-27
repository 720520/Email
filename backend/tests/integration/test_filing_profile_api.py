from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import AuditEvent, FilingField, FilingFileVersion, Tenant, UserRole
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
        )
        AuthService().create_user(
            session,
            username="filing_viewer",
            password="FilingViewer!2026",
            role=UserRole.VIEWER,
            tenant_id=foundation.tenant_id,
        )


async def test_dynamic_fields_file_versions_permissions_and_audit(app: FastAPI) -> None:
    _seed_users()
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://testserver") as admin,
        AsyncClient(transport=transport, base_url="http://testserver") as viewer,
    ):
        assert (
            await admin.post(
                "/api/v1/auth/login",
                json={"username": "filing_admin", "password": "FilingAdmin!2026"},
            )
        ).status_code == 200
        initial = await admin.get("/api/v1/filing-profile")
        created = await admin.post(
            "/api/v1/filing-profile/fields",
            json={
                "label": "最新公司章程",
                "category": "自定义文件",
                "field_type": "file",
                "sensitive": False,
                "multiline": False,
                "source_forms": ["变更后更新"],
                "sort_order": 999,
            },
        )
        field_id = created.json()["id"]
        updated = await admin.patch(
            f"/api/v1/filing-profile/fields/{field_id}",
            json={
                "label": "公司章程最新版",
                "category": "公司证照",
                "field_type": "file",
                "sensitive": False,
                "multiline": False,
                "source_forms": ["工商变更后更新"],
                "sort_order": 15,
            },
        )
        version_one = await admin.post(
            f"/api/v1/filing-profile/fields/{field_id}/files",
            files={"file": ("章程-v1.pdf", b"first-version", "application/pdf")},
        )
        version_two = await admin.post(
            f"/api/v1/filing-profile/fields/{field_id}/files",
            files={"file": ("章程-v2.pdf", b"second-version", "application/pdf")},
        )

        assert (
            await viewer.post(
                "/api/v1/auth/login",
                json={"username": "filing_viewer", "password": "FilingViewer!2026"},
            )
        ).status_code == 200
        viewer_profile = await viewer.get("/api/v1/filing-profile")
        forbidden_create = await viewer.post(
            "/api/v1/filing-profile/fields",
            json={"label": "越权字段", "category": "测试", "field_type": "text"},
        )
        downloaded = await viewer.get(version_one.json()["download_url"])

        archived = await admin.delete(f"/api/v1/filing-profile/fields/{field_id}")

    assert initial.status_code == 200
    assert initial.json()["can_edit"] is True
    assert len(initial.json()["fields"]) >= 40
    assert created.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["label"] == "公司章程最新版"
    assert version_one.status_code == 200
    assert version_one.json()["version"] == 1
    assert version_two.status_code == 200
    assert version_two.json()["version"] == 2
    assert viewer_profile.status_code == 200
    assert viewer_profile.json()["can_edit"] is False
    assert forbidden_create.status_code == 403
    assert downloaded.status_code == 200
    assert downloaded.content == b"first-version"
    assert archived.status_code == 204

    with get_database_manager().session_factory() as session:
        field = session.scalar(
            select(FilingField)
            .where(FilingField.id == field_id)
            .execution_options(skip_tenant_scope=True)
        )
        versions = list(
            session.scalars(
                select(FilingFileVersion)
                .where(FilingFileVersion.field_id == field_id)
                .execution_options(skip_tenant_scope=True)
            )
        )
        actions = set(
            session.scalars(
                select(AuditEvent.action)
                .where(AuditEvent.resource_type.in_(("filing_field", "filing_file_version")))
                .execution_options(skip_tenant_scope=True)
            )
        )
    assert field is not None and field.is_active is False
    assert len(versions) == 2
    assert {
        "filing_field.create",
        "filing_field.update",
        "filing_field.archive",
        "filing_file.version.upload",
        "filing_file.version.download",
    }.issubset(actions)


async def test_filing_files_and_fields_are_isolated_between_tenants(app: FastAPI) -> None:
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
        )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        first_login = await client.post(
            "/api/v1/auth/login",
            json={"username": "filing_admin", "password": "FilingAdmin!2026"},
        )
        created = await client.post(
            "/api/v1/filing-profile/fields",
            json={
                "label": "合成测试文件",
                "category": "隔离测试",
                "field_type": "file",
            },
        )
        field_id = created.json()["id"]
        uploaded = await client.post(
            f"/api/v1/filing-profile/fields/{field_id}/files",
            files={"file": ("synthetic.txt", b"tenant-one-only", "text/plain")},
        )
        version_id = uploaded.json()["id"]
        await client.post("/api/v1/auth/logout")

        second_login = await client.post(
            "/api/v1/auth/login",
            json={"username": "filing_admin_two", "password": "SyntheticAdmin!2026"},
        )
        second_profile = await client.get("/api/v1/filing-profile")
        forbidden_download = await client.get(
            f"/api/v1/filing-profile/fields/{field_id}/files/{version_id}/download"
        )
        forbidden_upload = await client.post(
            f"/api/v1/filing-profile/fields/{field_id}/files",
            files={"file": ("cross-tenant.txt", b"must-not-be-written", "text/plain")},
        )
        forbidden_delete = await client.delete(f"/api/v1/filing-profile/fields/{field_id}")

    assert first_login.status_code == 200
    assert created.status_code == 200
    assert uploaded.status_code == 200
    assert second_login.status_code == 200
    assert second_profile.status_code == 200
    assert all(item["id"] != field_id for item in second_profile.json()["fields"])
    assert forbidden_download.status_code == 404
    assert forbidden_upload.status_code == 404
    assert forbidden_delete.status_code == 404

    with manager.session_factory() as session:
        versions = list(
            session.scalars(
                select(FilingFileVersion)
                .where(FilingFileVersion.field_id == field_id)
                .execution_options(skip_tenant_scope=True)
            )
        )
    assert len(versions) == 1
    assert versions[0].content_hash == uploaded.json()["content_hash"]
