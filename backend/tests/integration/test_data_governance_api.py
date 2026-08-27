from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import AuditEvent, SourceDocument, Tenant, UserRole
from app.db.session import get_database_manager
from app.services.auth_service import AuthService
from app.services.foundation_service import FoundationService

pytestmark = pytest.mark.anyio


def _seed_stage_one_users() -> tuple[int, int]:
    manager = get_database_manager()
    with manager.session_factory() as session, session.begin():
        session.info["skip_tenant_scope"] = True
        foundation = FoundationService(get_settings()).ensure(session)
        AuthService().create_user(
            session,
            username="governance_admin",
            password="GovernanceAdmin!2026",
            role=UserRole.ADMIN,
            tenant_id=foundation.tenant_id,
            is_platform_admin=False,
        )
        platform = AuthService().create_user(
            session,
            username="governance_platform",
            password="GovernancePlatform!2026",
            role=UserRole.ADMIN,
            tenant_id=foundation.tenant_id,
            is_platform_admin=True,
        )
        second_tenant = Tenant(code="governance-two", name="数据治理租户二", is_active=True)
        session.add(second_tenant)
        session.flush()
        AuthService().create_user(
            session,
            username="governance_two_admin",
            password="GovernanceTwo!2026",
            role=UserRole.ADMIN,
            tenant_id=second_tenant.id,
            is_platform_admin=False,
        )
        return platform.id, second_tenant.id


async def _login(client: AsyncClient, username: str, password: str) -> None:
    response = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text


async def test_stage_one_entities_facts_documents_permissions_and_audit(app: FastAPI) -> None:
    platform_user_id, _ = _seed_stage_one_users()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        await _login(client, "governance_admin", "GovernanceAdmin!2026")
        entity = await client.post(
            "/api/v2/entities",
            json={
                "entity_type": "organization",
                "display_name": "合成数据管理人",
                "external_code": "SYNTHETIC-ORG-001",
            },
        )
        assert entity.status_code == 201, entity.text
        entity_id = entity.json()["id"]
        definition = await client.post(
            "/api/v2/field-definitions",
            json={
                "entity_type": "organization",
                "field_code": "registration_status",
                "label": "登记状态",
                "data_type": "string",
                "category": "登记信息",
                "sensitivity": "normal",
            },
        )
        assert definition.status_code == 201, definition.text
        fact = await client.post(
            f"/api/v2/entities/{entity_id}/facts",
            json={
                "field_definition_id": definition.json()["id"],
                "value": "合成测试状态",
                "status": "confirmed",
                "valid_from": datetime(2026, 8, 27, tzinfo=UTC).isoformat(),
                "source_type": "manual",
            },
        )
        assert fact.status_code == 201, fact.text
        assert fact.json()["reviewed_by_user_id"] is not None
        sensitive_definition = await client.post(
            "/api/v2/field-definitions",
            json={
                "entity_type": "organization",
                "field_code": "synthetic_identity_summary",
                "label": "合成敏感摘要",
                "data_type": "string",
                "category": "敏感信息",
                "sensitivity": "highly_sensitive",
            },
        )
        sensitive_fact = await client.post(
            f"/api/v2/entities/{entity_id}/facts",
            json={
                "field_definition_id": sensitive_definition.json()["id"],
                "value": "仅用于权限测试的合成值",
                "status": "confirmed",
                "valid_from": datetime(2026, 8, 27, tzinfo=UTC).isoformat(),
                "source_type": "manual",
            },
        )
        assert sensitive_fact.status_code == 201, sensitive_fact.text

        normal = await client.post(
            "/api/v2/documents",
            data={
                "entity_id": str(entity_id),
                "document_type": "business_license",
                "sensitivity": "normal",
            },
            files={"file": ("synthetic-license.pdf", b"normal-evidence", "application/pdf")},
        )
        assert normal.status_code == 201, normal.text
        sensitive = await client.post(
            "/api/v2/documents",
            data={
                "entity_id": str(entity_id),
                "document_type": "identity_document",
                "sensitivity": "highly_sensitive",
            },
            files={"file": ("synthetic-id.pdf", b"synthetic-sensitive", "application/pdf")},
        )
        assert sensitive.status_code == 201, sensitive.text
        version_two = await client.post(
            "/api/v2/documents",
            data={
                "entity_id": str(entity_id),
                "document_key": normal.json()["document_key"],
                "document_type": "business_license",
                "sensitivity": "normal",
            },
            files={"file": ("synthetic-license-v2.pdf", b"normal-evidence-v2", "application/pdf")},
        )
        assert version_two.status_code == 201
        assert version_two.json()["version"] == 2
        await client.post("/api/v1/auth/logout")

        await _login(client, "governance_platform", "GovernancePlatform!2026")
        documents_before = await client.get(f"/api/v2/documents?entity_id={entity_id}")
        facts_before = await client.get(f"/api/v2/entities/{entity_id}/facts")
        denied = await client.get(sensitive.json()["download_url"])
        allowed_normal = await client.get(normal.json()["download_url"])
        grant = await client.post(
            "/api/v2/permissions/grants",
            json={
                "user_id": platform_user_id,
                "entity_id": entity_id,
                "permissions": ["read", "download", "sensitive_read"],
                "sensitivity_ceiling": "highly_sensitive",
            },
        )
        allowed_sensitive = await client.get(sensitive.json()["download_url"])
        facts_after = await client.get(f"/api/v2/entities/{entity_id}/facts")

    assert [item["sensitivity"] for item in documents_before.json()] == ["normal", "normal"]
    assert [item["id"] for item in facts_before.json()] == [fact.json()["id"]]
    assert denied.status_code == 403
    assert allowed_normal.status_code == 200
    assert allowed_normal.content == b"normal-evidence"
    assert grant.status_code == 200, grant.text
    assert allowed_sensitive.status_code == 200
    assert allowed_sensitive.content == b"synthetic-sensitive"
    assert {item["id"] for item in facts_after.json()} == {
        fact.json()["id"],
        sensitive_fact.json()["id"],
    }

    with get_database_manager().session_factory() as session:
        documents = list(
            session.scalars(
                select(SourceDocument)
                .where(SourceDocument.document_key == normal.json()["document_key"])
                .order_by(SourceDocument.version)
                .execution_options(skip_tenant_scope=True)
            )
        )
        audit_actions = set(
            session.scalars(select(AuditEvent.action).execution_options(skip_tenant_scope=True))
        )
    assert [item.version for item in documents] == [1, 2]
    assert documents[0].content_hash != documents[1].content_hash
    assert {
        "entity.create",
        "field_definition.create",
        "field_value.append",
        "source_document.version.upload",
        "source_document.download",
        "resource_grant.upsert",
    }.issubset(audit_actions)


async def test_stage_one_cross_tenant_ids_fail_closed(app: FastAPI) -> None:
    _seed_stage_one_users()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        await _login(client, "governance_admin", "GovernanceAdmin!2026")
        entity = await client.post(
            "/api/v2/entities",
            json={"entity_type": "product", "display_name": "租户一合成产品"},
        )
        document = await client.post(
            "/api/v2/documents",
            data={"entity_id": str(entity.json()["id"]), "document_type": "fund_contract"},
            files={"file": ("synthetic-contract.pdf", b"tenant-one", "application/pdf")},
        )
        await client.post("/api/v1/auth/logout")
        await _login(client, "governance_two_admin", "GovernanceTwo!2026")
        entity_read = await client.get(f"/api/v2/entities/{entity.json()['id']}")
        document_read = await client.get(document.json()["download_url"])
        relation_upload = await client.post(
            "/api/v2/documents",
            data={"entity_id": str(entity.json()["id"]), "document_type": "cross_tenant"},
            files={"file": ("must-not-write.txt", b"blocked", "text/plain")},
        )

    assert entity_read.status_code == 404
    assert document_read.status_code == 404
    assert relation_upload.status_code == 404
