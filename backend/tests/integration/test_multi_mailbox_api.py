from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import MailboxAccount, MailboxUserGrant, UserRole
from app.db.session import get_database_manager
from app.services.auth_service import AuthService
from app.services.foundation_service import FoundationService


def _seed_users() -> tuple[int, int, int]:
    with get_database_manager().session_factory() as session, session.begin():
        identity = FoundationService(get_settings()).ensure(session)
        admin = AuthService().create_user(
            session,
            username="mailbox_admin",
            password="MailboxAdmin!2026",
            role=UserRole.ADMIN,
            tenant_id=identity.tenant_id,
        )
        viewer = AuthService().create_user(
            session,
            username="mailbox_viewer",
            password="MailboxViewer!2026",
            role=UserRole.VIEWER,
            tenant_id=identity.tenant_id,
        )
        return identity.tenant_id, admin.id, viewer.id


def test_multi_mailbox_create_scope_grant_and_secret_redaction(app: FastAPI) -> None:
    tenant_id, _, viewer_id = _seed_users()
    with TestClient(app) as client:
        assert client.post(
            "/api/v1/auth/login",
            json={"username": "mailbox_admin", "password": "MailboxAdmin!2026"},
        ).status_code == 200

        security = client.get("/api/v1/mailboxes/security-status")
        created = client.post(
            "/api/v1/mailboxes",
            json={
                "display_name": "163 运营邮箱",
                "host": "imap.163.com",
                "port": 993,
                "username": "ops@example.com",
                "credential": "test-authorization-code",
                "use_ssl": True,
                "start_tls": False,
                "folder": "INBOX",
            },
        )
        mailbox_id = created.json()["id"]
        listed = client.get("/api/v1/mailboxes")
        duplicate = client.post(
            "/api/v1/mailboxes",
            json={
                "display_name": "重复邮箱",
                "host": "imap.163.com",
                "username": "ops@example.com",
                "credential": "another-code",
            },
        )
        granted = client.put(
            f"/api/v1/mailboxes/{mailbox_id}/grants/{viewer_id}",
            json={
                "can_read_metadata": True,
                "can_read_content": False,
                "can_operate": False,
                "can_manage_credentials": False,
                "is_active": True,
            },
        )
        client.post("/api/v1/auth/logout")
        assert client.post(
            "/api/v1/auth/login",
            json={"username": "mailbox_viewer", "password": "MailboxViewer!2026"},
        ).status_code == 200
        viewer_list = client.get("/api/v1/mailboxes")
        forbidden_create = client.post(
            "/api/v1/mailboxes",
            json={
                "display_name": "越权邮箱",
                "host": "imap.example.com",
                "username": "forbidden@example.com",
            },
        )
        forbidden_operation = client.post(f"/api/v1/mailboxes/{mailbox_id}/sync")

    assert security.status_code == 200
    assert security.json()["ready_for_credentials"] is True
    assert created.status_code == 201
    assert created.json()["provider_type"] == "netease_163"
    assert created.json()["credential_configured"] is True
    assert "credential" not in created.json()
    assert "credential_ciphertext" not in created.json()
    assert listed.status_code == 200
    assert len(listed.json()) == 2
    assert duplicate.status_code == 409
    assert granted.status_code == 200
    assert granted.json()["user_id"] == viewer_id
    assert viewer_list.status_code == 200
    assert {item["id"] for item in viewer_list.json()} == {1, mailbox_id}
    viewer_mailbox = next(item for item in viewer_list.json() if item["id"] == mailbox_id)
    assert viewer_mailbox["permissions"] == {
        "can_read_metadata": True,
        "can_read_content": False,
        "can_operate": False,
        "can_manage_credentials": False,
    }
    assert forbidden_create.status_code == 403
    assert forbidden_operation.status_code == 403

    with get_database_manager().session_factory() as session:
        session.info["skip_tenant_scope"] = True
        mailbox = session.scalar(
            select(MailboxAccount).where(
                MailboxAccount.tenant_id == tenant_id,
                MailboxAccount.id == mailbox_id,
            )
        )
        grant = session.scalar(
            select(MailboxUserGrant).where(
                MailboxUserGrant.tenant_id == tenant_id,
                MailboxUserGrant.mailbox_account_id == mailbox_id,
                MailboxUserGrant.user_id == viewer_id,
            )
        )
        assert mailbox is not None
        assert mailbox.credential_ciphertext
        assert "test-authorization-code" not in mailbox.credential_ciphertext
        assert mailbox.configuration_source == "database"
        assert grant is not None


def test_mailbox_id_filter_cannot_escape_granted_scope(app: FastAPI) -> None:
    _, _, _ = _seed_users()
    with get_database_manager().session_factory() as session, session.begin():
        session.info["skip_tenant_scope"] = True
        identity = FoundationService(get_settings()).ensure(session)
        mailbox = MailboxAccount(
            tenant_id=identity.tenant_id,
            display_name="未授权邮箱",
            host="imap.hidden.example",
            username="hidden@example.com",
            configuration_source="database",
            is_default=False,
            is_enabled=True,
        )
        session.add(mailbox)
        session.flush()
        hidden_id = mailbox.id

    with TestClient(app) as client:
        assert client.post(
            "/api/v1/auth/login",
            json={"username": "mailbox_viewer", "password": "MailboxViewer!2026"},
        ).status_code == 200
        filtered = client.get(
            "/api/v1/emails",
            params={"mailbox_account_id": hidden_id},
        )
        connection = client.get(
            "/api/v1/emails/connection",
            params={"mailbox_account_id": hidden_id},
        )

    assert filtered.status_code == 403
    assert connection.status_code == 409
