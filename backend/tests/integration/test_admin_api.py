from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from email.message import EmailMessage

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security import PasswordHasher
from app.db.base import Base
from app.db.models import (
    AppUser,
    AttachmentRecord,
    AttachmentStatus,
    EmailRecord,
    EmailStatus,
    ExceptionRecord,
    ExceptionSeverity,
    FundNav,
    UserRole,
)


def _seed_admin_data() -> int:
    from app.core.config import get_settings
    from app.db.session import get_database_manager

    manager = get_database_manager()
    Base.metadata.create_all(manager.engine)
    now = datetime.now(UTC)
    message = EmailMessage()
    message["Subject"] = "基金净值 2026-07-29"
    message["From"] = "custodian@example.com"
    message.set_content("您好，基金净值报告见附件。")
    eml_path = get_settings().data_directory / "2026/07/29/emails/api-mailbox_1.eml"
    eml_path.parent.mkdir(parents=True, exist_ok=True)
    eml_path.write_bytes(message.as_bytes())
    with manager.session_factory() as session, session.begin():
        user = AppUser(
            username="admin",
            password_hash=PasswordHasher().hash("AdminPass!2026"),
            role=UserRole.ADMIN,
            token_version=1,
            is_active=True,
        )
        session.add(user)
        email = EmailRecord(
            mailbox="imap.example.com/INBOX",
            mailbox_key="api-mailbox",
            uid_validity="1",
            message_uid="1",
            subject="基金净值 2026-07-29",
            sender="custodian@example.com",
            receive_time=now,
            attachment_count=1,
            status=EmailStatus.SUCCESS,
            eml_path=eml_path.relative_to(get_settings().data_directory).as_posix(),
        )
        session.add(email)
        session.flush()
        attachment = AttachmentRecord(
            email_id=email.id,
            original_name="净值.xlsx",
            stored_path="2026/07/29/attachments/净值.xlsx",
            sha256="a" * 64,
            file_type="xlsx",
            parse_status=AttachmentStatus.PARTIAL_SUCCESS,
        )
        session.add(attachment)
        session.flush()
        nav = FundNav(
            product_name="吉余测试一号私募证券投资基金",
            product_code="JYTEST01",
            nav_date=date.today(),
            unit_nav=Decimal("1.12345678"),
            total_nav=Decimal("1.23456789"),
            asset_value=Decimal("10000000.0000"),
            source_file="净值.xlsx",
            attachment_id=attachment.id,
        )
        session.add(nav)
        exception = ExceptionRecord(
            email_id=email.id,
            attachment_id=attachment.id,
            exception_type="empty_nav",
            severity=ExceptionSeverity.ERROR,
            raw_data={"product_code": "JYTEST02", "product_name": "吉余测试二号"},
            message="单位净值为空",
        )
        session.add(exception)
        session.add(
            ExceptionRecord(
                email_id=email.id,
                attachment_id=attachment.id,
                exception_type="custodian_specific_warning",
                severity=ExceptionSeverity.WARNING,
                message="托管平台自定义提示",
            )
        )
        session.flush()
        return exception.id


def test_login_and_protected_operational_queries(app: FastAPI) -> None:
    exception_id = _seed_admin_data()
    with TestClient(app) as client:
        unauthorized = client.get("/api/v1/dashboard")
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "ADMIN", "password": "AdminPass!2026"},
        )
        dashboard = client.get("/api/v1/dashboard")
        emails = client.get("/api/v1/emails", params={"keyword": "基金净值"})
        email_connection = client.get("/api/v1/emails/connection")
        email_detail = client.get("/api/v1/emails/1")
        raw_email = client.get("/api/v1/emails/1/raw")
        connection_test = client.post("/api/v1/emails/connection/test")
        email_sync = client.post("/api/v1/emails/sync")
        nav = client.get("/api/v1/fund-nav", params={"keyword": "JYTEST01"})
        exact_nav = client.get(
            "/api/v1/fund-nav",
            params={"product_code": "jytest01"},
        )
        latest_nav_date = client.get("/api/v1/fund-nav/latest-date")
        products = client.get("/api/v1/fund-nav/products", params={"keyword": "测试一号"})
        archived_products = client.get("/api/v1/fund-nav/products")
        history = client.get(
            "/api/v1/fund-nav/history",
            params={"product_code": "jytest01"},
        )
        exceptions = client.get("/api/v1/exceptions", params={"category": "净值为空"})
        other_exceptions = client.get(
            "/api/v1/exceptions",
            params={"category": "其他异常"},
        )
        resolved = client.patch(
            f"/api/v1/exceptions/{exception_id}/status",
            json={"status": "resolved"},
        )
        logout = client.post("/api/v1/auth/logout")
        after_logout = client.get("/api/v1/auth/me")

    assert unauthorized.status_code == 401
    assert login.status_code == 200
    assert login.json()["user"] == {"id": 1, "username": "admin", "role": "admin"}
    assert "HttpOnly" in login.headers["set-cookie"]
    assert dashboard.status_code == 200
    assert dashboard.json()["fund_count"] == 1
    assert emails.json()["total"] == 1
    assert email_connection.status_code == 200
    assert email_detail.status_code == 200
    assert email_detail.json()["original_available"] is True
    assert email_detail.json()["body_text"] == "您好，基金净值报告见附件。"
    assert email_detail.json()["attachments"][0]["id"] == 1
    assert raw_email.status_code == 200
    assert raw_email.headers["content-type"].startswith("message/rfc822")
    assert email_connection.json()["configured"] is False
    assert "password" not in email_connection.json()
    assert connection_test.status_code == 200
    assert connection_test.json()["success"] is False
    assert connection_test.json()["message"] == "未配置 email.host"
    assert email_sync.status_code == 200
    assert email_sync.json()["success"] is False
    assert email_sync.json()["job_run_id"] > 0
    assert nav.json()["items"][0]["unit_nav"] == "1.12345678"
    assert exact_nav.json()["total"] == 1
    assert exact_nav.json()["items"][0]["fund_group_name"] == "吉余测试一号私募证券投资基金"
    assert latest_nav_date.json() == {"latest_nav_date": date.today().isoformat()}
    assert products.json()[0]["product_code"] == "JYTEST01"
    assert archived_products.json()[0]["product_code"] == "JYTEST01"
    assert archived_products.json()[0]["share_class"] is None
    assert history.json()["points"][0]["nav_date"] == date.today().isoformat()
    assert exceptions.json()["items"][0]["category"] == "净值为空"
    assert other_exceptions.json()["total"] == 1
    assert exceptions.json()["items"][0]["email_id"] == 1
    assert other_exceptions.json()["items"][0]["category"] == "其他异常"
    assert resolved.json()["status"] == "resolved"
    assert logout.status_code == 204
    assert after_logout.status_code == 401


def test_login_failure_uses_generic_message(app: FastAPI) -> None:
    _seed_admin_data()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "wrong"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "用户名或密码错误"


def test_viewer_can_read_but_cannot_change_exception_status(app: FastAPI) -> None:
    exception_id = _seed_admin_data()
    from app.db.session import get_database_manager

    with get_database_manager().session_factory() as session, session.begin():
        session.add(
            AppUser(
                username="viewer",
                password_hash=PasswordHasher().hash("ViewerPass!2026"),
                role=UserRole.VIEWER,
                token_version=1,
                is_active=True,
            )
        )
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "viewer", "password": "ViewerPass!2026"},
        )
        readable = client.get("/api/v1/exceptions")
        email_readable = client.get("/api/v1/emails/1")
        forbidden = client.patch(
            f"/api/v1/exceptions/{exception_id}/status",
            json={"status": "resolved"},
        )
        connection_forbidden = client.post("/api/v1/emails/connection/test")
        sync_forbidden = client.post("/api/v1/emails/sync")

    assert login.status_code == 200
    assert readable.status_code == 200
    assert email_readable.status_code == 200
    assert forbidden.status_code == 403
    assert connection_forbidden.status_code == 403
    assert sync_forbidden.status_code == 403
