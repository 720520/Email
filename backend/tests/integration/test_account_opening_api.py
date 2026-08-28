from __future__ import annotations

import hashlib
from datetime import date

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import (
    AuditEvent,
    CounterpartyInstitution,
    DocumentRelation,
    Entity,
    FundProduct,
    FundProductProfile,
    OrganizationProfile,
    SourceDocument,
    Tenant,
    UserRole,
)
from app.db.session import get_database_manager
from app.services.auth_service import AuthService
from app.services.foundation_service import FoundationService

pytestmark = pytest.mark.anyio


def _seed_account_opening() -> dict[str, int]:
    manager = get_database_manager()
    with manager.session_factory() as session, session.begin():
        session.info["skip_tenant_scope"] = True
        foundation = FoundationService(get_settings()).ensure(session)
        admin = AuthService().create_user(
            session,
            username="opening_admin",
            password="OpeningAdmin!2026",
            role=UserRole.ADMIN,
            tenant_id=foundation.tenant_id,
            is_platform_admin=False,
        )
        operator = AuthService().create_user(
            session,
            username="opening_operator",
            password="OpeningOperator!2026",
            role=UserRole.OPERATOR,
            tenant_id=foundation.tenant_id,
            is_platform_admin=False,
        )
        organization = Entity(
            tenant_id=foundation.tenant_id,
            entity_type="organization",
            display_name="合成开户管理人",
            external_code="SYNTH-OPENING-ORG",
            status="active",
            created_by_user_id=admin.id,
        )
        product_entity = Entity(
            tenant_id=foundation.tenant_id,
            entity_type="product",
            display_name="合成开户产品",
            external_code="SYNTH-OPENING-PRODUCT",
            status="active",
            created_by_user_id=admin.id,
        )
        session.add_all([organization, product_entity])
        session.flush()
        product = FundProduct(
            tenant_id=foundation.tenant_id,
            entity_id=product_entity.id,
            product_code="SYNTH-OPEN-001",
            product_name="合成开户产品",
            source_profile={},
            source_profile_meta={},
            manual_profile={},
        )
        session.add(product)
        session.flush()
        session.add_all(
            [
                OrganizationProfile(tenant_id=foundation.tenant_id, entity_id=organization.id),
                FundProductProfile(
                    tenant_id=foundation.tenant_id,
                    entity_id=product_entity.id,
                    fund_product_id=product.id,
                ),
            ]
        )
        documents: list[SourceDocument] = []
        for key, entity_id, name, content in (
            ("opening-license", organization.id, "合成营业执照.pdf", b"synthetic-license"),
            ("opening-contract", product_entity.id, "合成基金合同.pdf", b"synthetic-contract"),
            (
                "opening-contract-supplement",
                product_entity.id,
                "合成基金合同补件.pdf",
                b"synthetic-contract-supplement",
            ),
        ):
            document = SourceDocument(
                tenant_id=foundation.tenant_id,
                document_key=key,
                entity_id=entity_id,
                document_type=key,
                original_name=name,
                mime_type="application/pdf",
                content_hash=hashlib.sha256(content).hexdigest(),
                storage_path=f"synthetic/{key}.pdf",
                file_size=len(content),
                version=1,
                source_channel="manual_upload",
                sensitivity="normal",
                uploaded_by_user_id=admin.id,
            )
            session.add(document)
            documents.append(document)
        session.flush()
        for document in documents:
            session.add(
                DocumentRelation(
                    tenant_id=foundation.tenant_id,
                    document_id=document.id,
                    entity_id=document.entity_id,
                    relation_type="evidence_for",
                )
            )

        second_tenant = Tenant(code="opening-two", name="合成开户租户二", is_active=True)
        session.add(second_tenant)
        session.flush()
        AuthService().create_user(
            session,
            username="opening_two_admin",
            password="OpeningTwo!2026",
            role=UserRole.ADMIN,
            tenant_id=second_tenant.id,
            is_platform_admin=False,
        )
        foreign_entity = Entity(
            tenant_id=second_tenant.id,
            entity_type="institution",
            display_name="租户二合成券商",
            external_code="SYNTH-FOREIGN-INSTITUTION",
            status="active",
        )
        session.add(foreign_entity)
        session.flush()
        foreign_institution = CounterpartyInstitution(
            tenant_id=second_tenant.id,
            entity_id=foreign_entity.id,
            institution_type="broker",
            full_name="租户二合成券商",
            contact_information={},
            is_active=True,
        )
        session.add(foreign_institution)
        session.flush()
        return {
            "operator_id": operator.id,
            "product_id": product.id,
            "company_document_id": documents[0].id,
            "product_document_id": documents[1].id,
            "supplement_document_id": documents[2].id,
            "foreign_institution_id": foreign_institution.id,
        }


async def _login(client: AsyncClient, username: str, password: str) -> None:
    response = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text


async def _create_template(
    client: AsyncClient,
    *,
    scope: str,
    institution_id: int | None,
    account_type: str,
    name: str,
    code: str,
    item_name: str,
    source_scope: str,
    version: int = 1,
) -> dict:
    response = await client.post(
        "/api/v2/requirement-templates",
        json={
            "template_scope": scope,
            "institution_id": institution_id,
            "account_type": account_type,
            "fund_type": "all" if scope == "regulatory" else "private_securities",
            "name": name,
            "version": version,
            "effective_from": "2026-01-01",
            "items": [
                {
                    "requirement_code": code,
                    "name": item_name,
                    "source_scope": source_scope,
                    "required": True,
                    "original_required": False,
                    "sort_order": 10,
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_institution_templates_application_freeze_and_supplement_history(
    app: FastAPI,
) -> None:
    seeded = _seed_account_opening()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        await _login(client, "opening_admin", "OpeningAdmin!2026")
        broker_a = await client.post(
            "/api/v2/institutions",
            json={
                "institution_type": "broker",
                "full_name": "甲合成证券股份有限公司",
                "short_name": "甲合成证券",
                "license_code": "SYNTH-LICENSE-A",
                "contact_information": {"contact": "合成联系人甲"},
            },
        )
        broker_b = await client.post(
            "/api/v2/institutions",
            json={
                "institution_type": "broker",
                "full_name": "乙合成证券股份有限公司",
                "short_name": "乙合成证券",
                "contact_information": {},
            },
        )
        assert broker_a.status_code == broker_b.status_code == 201
        foreign_patch = await client.patch(
            f"/api/v2/institutions/{seeded['foreign_institution_id']}",
            json={"short_name": "禁止跨租户修改"},
        )
        assert foreign_patch.status_code == 404
        broker_a_id = broker_a.json()["id"]
        broker_b_id = broker_b.json()["id"]
        await _create_template(
            client,
            scope="regulatory",
            institution_id=None,
            account_type="securities",
            name="证券账户监管基础清单",
            code="obsolete_business_license",
            item_name="旧版营业执照要求",
            source_scope="organization",
        )
        await _create_template(
            client,
            scope="regulatory",
            institution_id=None,
            account_type="securities",
            name="证券账户监管基础清单",
            code="business_license",
            item_name="管理人营业执照",
            source_scope="organization",
            version=2,
        )
        await _create_template(
            client,
            scope="regulatory",
            institution_id=None,
            account_type="securities",
            name="基金合同监管要求",
            code="fund_contract",
            item_name="监管基金合同",
            source_scope="organization",
            version=99,
        )
        await _create_template(
            client,
            scope="institution",
            institution_id=broker_a_id,
            account_type="securities",
            name="甲证券材料清单",
            code="fund_contract",
            item_name="基金合同",
            source_scope="product",
        )
        await _create_template(
            client,
            scope="institution",
            institution_id=broker_a_id,
            account_type="futures",
            name="甲期货材料清单",
            code="futures_form",
            item_name="期货开户申请表",
            source_scope="product",
        )
        await _create_template(
            client,
            scope="institution",
            institution_id=broker_b_id,
            account_type="securities",
            name="乙证券材料清单",
            code="fund_contract",
            item_name="基金合同",
            source_scope="product",
        )
        await client.post("/api/v1/auth/logout")

        await _login(client, "opening_operator", "OpeningOperator!2026")
        application = await client.post(
            "/api/v2/account-applications",
            json={
                "product_id": seeded["product_id"],
                "institution_id": broker_a_id,
                "account_type": "securities",
                "settlement_mode": "third_party_custody",
                "fund_type": "private_securities",
                "application_date": date(2026, 8, 28).isoformat(),
            },
        )
        assert application.status_code == 201, application.text
        body = application.json()
        application_id = body["id"]
        requirement_by_code = {item["requirement_code"]: item for item in body["requirements"]}
        assert set(requirement_by_code) == {"business_license", "fund_contract"}
        assert {item["source_scope"] for item in body["requirements"]} == {
            "organization",
            "product",
        }

        second_institution_application = await client.post(
            "/api/v2/account-applications",
            json={
                "product_id": seeded["product_id"],
                "institution_id": broker_b_id,
                "account_type": "securities",
                "settlement_mode": "third_party_custody",
                "fund_type": "private_securities",
                "application_date": "2026-08-28",
            },
        )
        assert second_institution_application.status_code == 201
        futures_application = await client.post(
            "/api/v2/account-applications",
            json={
                "product_id": seeded["product_id"],
                "institution_id": broker_a_id,
                "account_type": "futures",
                "settlement_mode": "margin",
                "fund_type": "private_securities",
                "application_date": "2026-08-28",
            },
        )
        assert futures_application.status_code == 201
        futures_requirements = futures_application.json()["requirements"]
        assert [item["requirement_code"] for item in futures_requirements] == ["futures_form"]

        company_requirement = requirement_by_code["business_license"]
        product_requirement = requirement_by_code["fund_contract"]
        company_attached = await client.put(
            f"/api/v2/account-applications/{application_id}/requirements/{company_requirement['id']}",
            json={"document_id": seeded["company_document_id"]},
        )
        assert company_attached.status_code == 200
        product_attached = await client.put(
            f"/api/v2/account-applications/{application_id}/requirements/{product_requirement['id']}",
            json={"document_id": seeded["product_document_id"]},
        )
        assert product_attached.status_code == 200
        submitted = await client.post(f"/api/v2/account-applications/{application_id}/submit")
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["status"] == "submitted"
        frozen = await client.put(
            f"/api/v2/account-applications/{application_id}/requirements/{product_requirement['id']}",
            json={"document_id": seeded["supplement_document_id"]},
        )
        assert frozen.status_code == 409
        await client.post("/api/v1/auth/logout")

        await _login(client, "opening_admin", "OpeningAdmin!2026")
        supplement_requested = await client.post(
            f"/api/v2/account-applications/{application_id}/review",
            json={
                "action": "request_supplement",
                "requirement_ids": [product_requirement["id"]],
                "comment": "请补充合成签署页",
            },
        )
        assert supplement_requested.status_code == 200
        assert supplement_requested.json()["status"] == "supplement_required"
        await client.post("/api/v1/auth/logout")

        await _login(client, "opening_operator", "OpeningOperator!2026")
        supplemented = await client.post(
            f"/api/v2/account-applications/{application_id}/supplements",
            json={
                "requirement_id": product_requirement["id"],
                "document_id": seeded["supplement_document_id"],
                "comment": "合成补件材料",
            },
        )
        assert supplemented.status_code == 201, supplemented.text
        assert (
            supplemented.json()["supplements"][0]["document_id"] == seeded["supplement_document_id"]
        )
        current_requirement = next(
            item
            for item in supplemented.json()["requirements"]
            if item["id"] == product_requirement["id"]
        )
        assert current_requirement["document_id"] == seeded["product_document_id"]
        resubmitted = await client.post(f"/api/v2/account-applications/{application_id}/submit")
        assert resubmitted.status_code == 200
        await client.post("/api/v1/auth/logout")

        await _login(client, "opening_admin", "OpeningAdmin!2026")
        approved = await client.post(
            f"/api/v2/account-applications/{application_id}/review",
            json={"action": "approve", "comment": "合成审批通过"},
        )
        assert approved.status_code == 200, approved.text
        opened = await client.post(
            f"/api/v2/account-applications/{application_id}/review",
            json={"action": "open"},
        )
        assert opened.status_code == 200
        closed = await client.post(
            f"/api/v2/account-applications/{application_id}/review",
            json={"action": "close"},
        )
        assert closed.status_code == 200
        assert closed.json()["status"] == "closed"
        assert closed.json()["completed_date"] is not None
        assert closed.json()["closed_date"] is not None
        event_types = [event["event_type"] for event in closed.json()["events"]]
        assert event_types == [
            "created",
            "material_attached",
            "material_attached",
            "submitted",
            "supplement_requested",
            "supplement_added",
            "submitted",
            "approved",
            "opened",
            "closed",
        ]

    with get_database_manager().session_factory() as session:
        actions = set(
            session.scalars(
                select(AuditEvent.action)
                .where(AuditEvent.resource_id == str(application_id))
                .execution_options(skip_tenant_scope=True)
            )
        )
    assert {
        "account_application.create",
        "account_application.material.attach",
        "account_application.submit",
        "account_application.request_supplement",
        "account_application.supplement.add",
        "account_application.approve",
        "account_application.open",
        "account_application.close",
    }.issubset(actions)
