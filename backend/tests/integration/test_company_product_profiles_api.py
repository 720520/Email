from __future__ import annotations

import hashlib

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import (
    AuditEvent,
    DocumentRelation,
    Entity,
    FundProduct,
    FundProductProfile,
    OrganizationProfile,
    ProductMaterialAttribution,
    SourceDocument,
    UserRole,
)
from app.db.session import get_database_manager
from app.services.auth_service import AuthService
from app.services.foundation_service import FoundationService

pytestmark = pytest.mark.anyio


def _seed_profiles() -> tuple[int, int]:
    manager = get_database_manager()
    settings = get_settings()
    with manager.session_factory() as session, session.begin():
        session.info["skip_tenant_scope"] = True
        foundation = FoundationService(settings).ensure(session)
        user = AuthService().create_user(
            session,
            username="profile_admin",
            password="ProfileAdmin!2026",
            role=UserRole.ADMIN,
            tenant_id=foundation.tenant_id,
            is_platform_admin=False,
        )
        organization = Entity(
            tenant_id=foundation.tenant_id,
            entity_type="organization",
            display_name="合成公司资料",
            external_code="SYNTH-ORG",
            status="active",
            created_by_user_id=user.id,
        )
        product = Entity(
            tenant_id=foundation.tenant_id,
            entity_type="product",
            display_name="合成产品资料",
            external_code="SYNTH-PRODUCT",
            status="active",
            created_by_user_id=user.id,
        )
        session.add_all([organization, product])
        session.flush()
        fund_product = FundProduct(
            tenant_id=foundation.tenant_id,
            entity_id=product.id,
            product_code="SYNTH-PRODUCT",
            product_name="合成产品资料",
            source_profile={},
            source_profile_meta={},
            manual_profile={},
        )
        session.add(fund_product)
        session.flush()
        session.add_all(
            [
                OrganizationProfile(tenant_id=foundation.tenant_id, entity_id=organization.id),
                FundProductProfile(
                    tenant_id=foundation.tenant_id,
                    entity_id=product.id,
                    fund_product_id=fund_product.id,
                ),
            ]
        )
        company_content = b"synthetic-company-document"
        product_content = b"synthetic-unassigned-product-document"
        company_path = settings.data_directory / "stage2/company.pdf"
        product_path = settings.data_directory / "stage2/product.pdf"
        company_path.parent.mkdir(parents=True, exist_ok=True)
        company_path.write_bytes(company_content)
        product_path.write_bytes(product_content)
        company_document = SourceDocument(
            tenant_id=foundation.tenant_id,
            document_key="synthetic-company",
            entity_id=organization.id,
            document_type="business_license",
            original_name="synthetic-company.pdf",
            mime_type="application/pdf",
            content_hash=hashlib.sha256(company_content).hexdigest(),
            storage_path="stage2/company.pdf",
            file_size=len(company_content),
            version=1,
            source_channel="manual_upload",
            sensitivity="normal",
            uploaded_by_user_id=user.id,
        )
        product_document = SourceDocument(
            tenant_id=foundation.tenant_id,
            document_key="synthetic-product",
            entity_id=None,
            document_type="fund_contract_file",
            original_name="synthetic-product.pdf",
            mime_type="application/pdf",
            content_hash=hashlib.sha256(product_content).hexdigest(),
            storage_path="stage2/product.pdf",
            file_size=len(product_content),
            version=1,
            source_channel="manual_upload",
            sensitivity="normal",
            uploaded_by_user_id=user.id,
        )
        session.add_all([company_document, product_document])
        session.flush()
        session.add_all(
            [
                DocumentRelation(
                    tenant_id=foundation.tenant_id,
                    document_id=company_document.id,
                    entity_id=organization.id,
                    relation_type="legacy_company_material",
                ),
                ProductMaterialAttribution(
                    tenant_id=foundation.tenant_id,
                    document_id=product_document.id,
                    status="pending",
                ),
            ]
        )
        return product.id, product_document.id


async def test_company_product_split_and_manual_attribution(app: FastAPI) -> None:
    product_entity_id, product_document_id = _seed_profiles()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": "profile_admin", "password": "ProfileAdmin!2026"},
        )
        company = await client.get("/api/v2/profiles/company")
        products = await client.get("/api/v2/profiles/products")
        product_before = await client.get(f"/api/v2/profiles/products/{product_entity_id}")
        pending = await client.get("/api/v2/product-material-attributions")
        assigned = await client.post(
            f"/api/v2/product-material-attributions/{pending.json()[0]['id']}/assign",
            json={"product_entity_id": product_entity_id, "notes": "合成归属测试"},
        )
        product_after = await client.get(f"/api/v2/profiles/products/{product_entity_id}")
        repeated = await client.post(
            f"/api/v2/product-material-attributions/{pending.json()[0]['id']}/assign",
            json={"product_entity_id": product_entity_id},
        )
        legacy_write = await client.put(
            "/api/v1/filing-profile", json={"field_values": {"company_name": "禁止写入"}}
        )

    assert login.status_code == 200
    assert company.status_code == 200
    assert [item["document_type"] for item in company.json()["documents"]] == ["business_license"]
    assert products.status_code == 200
    assert products.json()[0]["entity"]["id"] == product_entity_id
    assert product_before.json()["documents"] == []
    assert len(pending.json()) == 1
    assert pending.json()[0]["document"]["id"] == product_document_id
    assert assigned.status_code == 200
    assert assigned.json()["status"] == "assigned"
    assert [item["id"] for item in product_after.json()["documents"]] == [product_document_id]
    assert repeated.status_code == 409
    assert legacy_write.status_code == 410

    with get_database_manager().session_factory() as session:
        action = session.scalar(
            select(AuditEvent.action)
            .where(AuditEvent.action == "product_material.assign")
            .execution_options(skip_tenant_scope=True)
        )
    assert action == "product_material.assign"
