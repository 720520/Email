from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.db.models import (
    FundNav,
    MailboxAccount,
    Tenant,
    UserRole,
)
from app.db.session import configure_tenant_scope, get_database_manager
from app.services.auth_service import AuthService
from app.services.foundation_service import FoundationService

pytestmark = pytest.mark.anyio


def _seed_two_tenants() -> tuple[int, int]:
    manager = get_database_manager()
    with manager.session_factory() as session, session.begin():
        session.info["skip_tenant_scope"] = True
        default_identity = FoundationService(get_settings()).ensure(session)
        first_user = AuthService().create_user(
            session,
            username="tenant_one_admin",
            password="TenantOne!2026",
            role=UserRole.ADMIN,
            tenant_id=default_identity.tenant_id,
        )
        second_tenant = Tenant(code="tenant-2", name="Tenant 2", is_active=True)
        session.add(second_tenant)
        session.flush()
        second_mailbox = MailboxAccount(
            tenant_id=second_tenant.id,
            display_name="Tenant 2 Mailbox",
            host="imap.tenant-two.example",
            username="ops@tenant-two.example",
            is_default=True,
            is_enabled=True,
        )
        session.add(second_mailbox)
        session.flush()
        AuthService().create_user(
            session,
            username="tenant_two_admin",
            password="TenantTwo!2026",
            role=UserRole.ADMIN,
            tenant_id=second_tenant.id,
        )

    with manager.session_factory() as session, session.begin():
        configure_tenant_scope(
            session,
            tenant_id=default_identity.tenant_id,
            mailbox_ids=(default_identity.mailbox_account_id,),
        )
        session.add(
            _nav(
                tenant_id=default_identity.tenant_id,
                mailbox_account_id=default_identity.mailbox_account_id,
                product_name="Tenant One Fund",
            )
        )
    with manager.session_factory() as session, session.begin():
        configure_tenant_scope(
            session,
            tenant_id=second_tenant.id,
            mailbox_ids=(second_mailbox.id,),
        )
        session.add(
            _nav(
                tenant_id=second_tenant.id,
                mailbox_account_id=second_mailbox.id,
                product_name="Tenant Two Fund",
            )
        )
    return first_user.id, second_tenant.id


def _nav(*, tenant_id: int, mailbox_account_id: int, product_name: str) -> FundNav:
    return FundNav(
        tenant_id=tenant_id,
        mailbox_account_id=mailbox_account_id,
        product_name=product_name,
        product_code="SAMECODE",
        nav_date=date(2026, 8, 4),
        unit_nav=Decimal("1.0000"),
        total_nav=Decimal("1.0000"),
        source_file=f"{product_name}.xlsx",
    )


async def test_api_never_returns_another_tenants_nav(app: FastAPI) -> None:
    _seed_two_tenants()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        first_login = await client.post(
            "/api/v1/auth/login",
            json={"username": "tenant_one_admin", "password": "TenantOne!2026"},
        )
        first_result = await client.get("/api/v1/fund-nav")
        await client.post("/api/v1/auth/logout")
        second_login = await client.post(
            "/api/v1/auth/login",
            json={"username": "tenant_two_admin", "password": "TenantTwo!2026"},
        )
        second_result = await client.get("/api/v1/fund-nav")

    assert first_login.status_code == 200
    assert first_result.status_code == 200
    assert [item["product_name"] for item in first_result.json()["items"]] == ["Tenant One Fund"]
    assert second_login.status_code == 200
    assert second_result.status_code == 200
    assert [item["product_name"] for item in second_result.json()["items"]] == ["Tenant Two Fund"]
