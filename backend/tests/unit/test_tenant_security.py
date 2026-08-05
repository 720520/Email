from __future__ import annotations

import base64
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.config import SecuritySettings, Settings
from app.core.credential_security import (
    CredentialDecryptionError,
    MailboxCredentialCipher,
)
from app.db.base import Base
from app.db.models import AuditEvent, FundNav, MailboxAccount, Tenant
from app.db.session import (
    DatabaseManager,
    TenantScopeRequiredError,
    TenantScopeViolationError,
    configure_tenant_scope,
)
from app.repositories.fund_nav_repository import FundNavRepository
from app.services.audit_service import AuditEventImmutableError, AuditService
from app.services.foundation_service import FoundationService


def _security_settings() -> SecuritySettings:
    key = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii").rstrip("=")
    return SecuritySettings(
        secret_key="test-session-secret-with-at-least-32-characters",
        credential_encryption_key=key,
        audit_signing_key=key,
    )


def _database(tmp_path: Path) -> DatabaseManager:
    manager = DatabaseManager(f"sqlite:///{(tmp_path / 'tenant-security.db').as_posix()}")
    Base.metadata.create_all(manager.engine)
    with manager.session_factory() as session, session.begin():
        session.info["skip_tenant_scope"] = True
        session.add_all(
            [
                Tenant(id=1, code="tenant-1", name="Tenant 1"),
                Tenant(id=2, code="tenant-2", name="Tenant 2"),
                MailboxAccount(
                    id=1,
                    tenant_id=1,
                    display_name="Mailbox 1",
                    host="imap.one.example",
                    username="one@example.com",
                    is_default=True,
                ),
                MailboxAccount(
                    id=2,
                    tenant_id=2,
                    display_name="Mailbox 2",
                    host="imap.two.example",
                    username="two@example.com",
                    is_default=True,
                ),
            ]
        )
    return manager


def _nav(*, tenant_id: int, mailbox_account_id: int, name: str) -> FundNav:
    return FundNav(
        tenant_id=tenant_id,
        mailbox_account_id=mailbox_account_id,
        product_name=name,
        product_code="SCOPE01",
        nav_date=date(2026, 8, 4),
        unit_nav=Decimal("1.0001"),
        total_nav=Decimal("1.0001"),
        source_file=f"{name}.xlsx",
    )


def test_mailbox_credential_is_encrypted_and_bound_to_scope() -> None:
    cipher = MailboxCredentialCipher.from_security_settings(_security_settings())
    plaintext = "mail-authorization-code"

    encrypted = cipher.encrypt(plaintext, tenant_id=1, mailbox_account_id=10)

    assert plaintext not in encrypted
    assert cipher.decrypt(encrypted, tenant_id=1, mailbox_account_id=10) == plaintext
    with pytest.raises(CredentialDecryptionError):
        cipher.decrypt(encrypted, tenant_id=2, mailbox_account_id=10)
    with pytest.raises(CredentialDecryptionError):
        cipher.decrypt(encrypted, tenant_id=1, mailbox_account_id=11)


def test_foundation_encrypts_legacy_credential_and_audits_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FUND_NAV_EMAIL__PASSWORD", "legacy-authorization-code")
    security = _security_settings()
    settings = Settings(
        app={"environment": "test"},
        database={"url": f"sqlite:///{(tmp_path / 'foundation.db').as_posix()}"},
        storage={"data_directory": str(tmp_path / "data")},
        email={
            "host": "imap.example.com",
            "username": "ops@example.com",
            "password": "legacy-authorization-code",
        },
        security=security.model_dump(),
    )
    manager = DatabaseManager(settings.database_url)
    Base.metadata.create_all(manager.engine)
    try:
        with manager.session_factory() as session, session.begin():
            identity = FoundationService(settings).ensure(session)
        with manager.session_factory() as session:
            session.info["skip_tenant_scope"] = True
            mailbox = session.get(MailboxAccount, identity.mailbox_account_id)
            audit = session.scalar(select(AuditEvent))
        assert mailbox is not None
        assert "legacy-authorization-code" not in (mailbox.credential_ciphertext or "")
        # Settings 的正式优先级是环境变量/.env 高于构造参数；断言必须使用
        # FoundationService 实际收到的最终安全配置，避免开发机密钥污染测试。
        assert MailboxCredentialCipher.from_security_settings(settings.security).decrypt(
            mailbox.credential_ciphertext or "",
            tenant_id=identity.tenant_id,
            mailbox_account_id=identity.mailbox_account_id,
        ) == "legacy-authorization-code"
        assert audit is not None
        assert audit.action == "mailbox.credential.bootstrap"
    finally:
        manager.dispose()


def test_business_data_access_is_default_deny_and_tenant_scoped(tmp_path: Path) -> None:
    manager = _database(tmp_path)
    try:
        with manager.session_factory() as session, session.begin():
            configure_tenant_scope(session, tenant_id=1, mailbox_ids=(1,))
            session.add(_nav(tenant_id=1, mailbox_account_id=1, name="Tenant 1 Fund"))
        with manager.session_factory() as session, session.begin():
            configure_tenant_scope(session, tenant_id=2, mailbox_ids=(2,))
            session.add(_nav(tenant_id=2, mailbox_account_id=2, name="Tenant 2 Fund"))

        with manager.session_factory() as session:
            configure_tenant_scope(session, tenant_id=1, mailbox_ids=(1,))
            visible = list(session.scalars(select(FundNav)))
        assert [item.product_name for item in visible] == ["Tenant 1 Fund"]

        with manager.session_factory() as session:
            with pytest.raises(TenantScopeRequiredError):
                session.scalar(select(FundNav))
            with pytest.raises(TenantScopeRequiredError):
                session.scalar(select(func.count()).select_from(FundNav))
            with pytest.raises(TenantScopeRequiredError):
                session.scalar(select(MailboxAccount))

        with manager.session_factory() as session, pytest.raises(TenantScopeViolationError):
            configure_tenant_scope(session, tenant_id=1, mailbox_ids=(1,))
            session.add(_nav(tenant_id=2, mailbox_account_id=2, name="Invalid"))
            session.flush()
    finally:
        manager.dispose()


def test_duplicate_lookup_spans_authorized_tenant_not_mailbox(tmp_path: Path) -> None:
    manager = _database(tmp_path)
    try:
        with manager.session_factory() as session, session.begin():
            configure_tenant_scope(session, tenant_id=1, mailbox_ids=(1,))
            mailbox = MailboxAccount(
                id=3,
                tenant_id=1,
                display_name="Mailbox 3",
                host="imap.three.example",
                username="three@example.com",
            )
            session.add(mailbox)
        with manager.session_factory() as session, session.begin():
            configure_tenant_scope(session, tenant_id=1, mailbox_ids=(1,))
            first = FundNavRepository().insert_if_absent(
                session,
                _nav(tenant_id=1, mailbox_account_id=1, name="First Source"),
            )
            assert first.inserted is True
        with manager.session_factory() as session, session.begin():
            configure_tenant_scope(session, tenant_id=1, mailbox_ids=(3,))
            duplicate = FundNavRepository().insert_if_absent(
                session,
                _nav(tenant_id=1, mailbox_account_id=3, name="Second Source"),
            )
            assert duplicate.inserted is False
            assert duplicate.record.mailbox_account_id == 1
    finally:
        manager.dispose()


def test_audit_log_redacts_secrets_chains_events_and_rejects_update(tmp_path: Path) -> None:
    manager = _database(tmp_path)
    service = AuditService(bytes(range(32)))
    try:
        with manager.session_factory() as session, session.begin():
            configure_tenant_scope(session, tenant_id=1, mailbox_ids=(1,))
            first = service.append(
                session,
                tenant_id=1,
                actor_user_id=None,
                actor_username="tester",
                mailbox_account_id=1,
                action="mailbox.test",
                resource_type="mailbox_account",
                resource_id=1,
                outcome="success",
                detail={"password": "must-not-be-stored", "message_count": 2},
            )
            second = service.append(
                session,
                tenant_id=1,
                actor_user_id=None,
                actor_username="tester",
                action="nav.export",
                resource_type="job_run",
                outcome="success",
            )
            assert first.detail == {"password": "[REDACTED]", "message_count": 2}
            assert second.previous_hash == first.event_hash

        with manager.session_factory() as session:
            assert service.verify_tenant_chain(session, tenant_id=1) == (True, None)

        with manager.session_factory() as session:
            configure_tenant_scope(session, tenant_id=1, mailbox_ids=(1,))
            event = session.scalar(select(AuditEvent).order_by(AuditEvent.id))
            assert event is not None
            event.outcome = "tampered"
            with pytest.raises(AuditEventImmutableError):
                session.commit()
    finally:
        manager.dispose()
