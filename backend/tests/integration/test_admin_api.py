from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from email.message import EmailMessage

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.models import (
    AttachmentRecord,
    AttachmentStatus,
    EmailRecord,
    EmailStatus,
    ExceptionRecord,
    ExceptionSeverity,
    FundNav,
    FundProduct,
    UserRole,
)


def _seed_admin_data() -> int:
    from app.core.config import get_settings
    from app.db.session import configure_tenant_scope, get_database_manager
    from app.services.auth_service import AuthService
    from app.services.foundation_service import FoundationService

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
        identity = FoundationService(get_settings()).ensure(session)
        AuthService().create_user(
            session,
            username="admin",
            password="AdminPass!2026",
            role=UserRole.ADMIN,
            tenant_id=identity.tenant_id,
        )
        configure_tenant_scope(
            session,
            tenant_id=identity.tenant_id,
            mailbox_ids=(identity.mailbox_account_id,),
        )
        email = EmailRecord(
            tenant_id=identity.tenant_id,
            mailbox_account_id=identity.mailbox_account_id,
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
            tenant_id=identity.tenant_id,
            mailbox_account_id=identity.mailbox_account_id,
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
            tenant_id=identity.tenant_id,
            mailbox_account_id=identity.mailbox_account_id,
            product_name="吉余测试一号私募证券投资基金",
            product_code="JYTEST01",
            master_product_code="JYTEST01",
            asset_code="JYTEST01(总)",
            registration_code="JYTEST01",
            share_class="总份额",
            nav_date=date.today(),
            unit_nav=Decimal("1.12345678"),
            total_nav=Decimal("1.23456789"),
            asset_value=Decimal("10000000.0000"),
            paid_in_capital=Decimal("9000000.0000"),
            total_assets=Decimal("10010000.0000"),
            total_assets_nav_ratio=Decimal("1.001"),
            source_file="净值.xlsx",
            attachment_id=attachment.id,
        )
        session.add(nav)
        session.add(
            FundProduct(
                tenant_id=identity.tenant_id,
                product_name="吉余测试一号私募证券投资基金",
                product_code="JYTEST01",
                source_investment_manager_info="附件经理信息",
                source_investment_strategy_info="附件策略信息",
                latest_source_file="净值.xlsx",
                latest_source_date=date.today(),
            )
        )
        exception = ExceptionRecord(
            tenant_id=identity.tenant_id,
            mailbox_account_id=identity.mailbox_account_id,
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
                tenant_id=identity.tenant_id,
                mailbox_account_id=identity.mailbox_account_id,
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
        product_summary = client.get("/api/v1/fund-products/summary")
        product_list = client.get("/api/v1/fund-products")
        product_detail = client.get("/api/v1/fund-products/1")
        product_updated = client.patch(
            "/api/v1/fund-products/1/profile",
            json={"investment_manager_info": "人工经理信息"},
        )
        report_templates = client.get("/api/v1/reports/templates")
        report_fields = client.get("/api/v1/reports/product-fields/1")
        report_field_updated = client.patch(
            "/api/v1/reports/product-fields/1/inception_date",
            json={"value": "2026-01-01", "reason": "合同运营复核"},
        )
        contract_uploaded = client.post(
            "/api/v1/reports/contracts/1",
            files={
                "file": (
                    "测试合同.txt",
                    "基金管理人：吉余私募基金管理有限公司\n"
                    "托管机构：测试托管机构\n风险等级：R4\n管理费率：1.00%".encode(),
                    "text/plain",
                )
            },
        )
        report_preview = client.post(
            "/api/v1/reports/preview",
            json={"fund_product_id": 1},
        )
        report_definition = client.post(
            "/api/v1/reports/definitions",
            json={
                "name": "测试周报",
                "fund_product_id": 1,
                "template_key": "builtin:weekly",
                "sections": ["product_info", "performance", "nav_chart"],
            },
        )
        report_generated = client.post(
            "/api/v1/reports/generate",
            json={"definition_id": 1},
        )
        report_runs = client.get("/api/v1/reports/runs")
        report_download = client.get("/api/v1/reports/runs/1/download")
        exceptions = client.get("/api/v1/exceptions", params={"category": "净值为空"})
        other_exceptions = client.get(
            "/api/v1/exceptions",
            params={"category": "其他异常"},
        )
        resolved = client.patch(
            f"/api/v1/exceptions/{exception_id}/status",
            json={"status": "resolved"},
        )
        audit_events = client.get("/api/v1/audit-events")
        logout = client.post("/api/v1/auth/logout")
        after_logout = client.get("/api/v1/auth/me")

    assert unauthorized.status_code == 401
    assert login.status_code == 200
    assert login.json()["user"] == {
        "id": 1,
        "username": "admin",
        "role": "admin",
        "tenant_id": 1,
        "tenant_code": "default",
        "tenant_name": "默认业务账套",
        "is_platform_admin": True,
    }
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
    assert product_summary.json()["product_count"] == 1
    assert product_summary.json()["latest_asset_value"] == "10000000.0000"
    assert product_list.json()["items"][0]["share_count"] == 1
    assert product_detail.json()["latest_snapshots"][0]["available_field_count"] >= 9
    assert product_updated.json()["investment_manager_info"] == "人工经理信息"
    assert product_updated.json()["investment_manager_manual"] is True
    assert product_updated.json()["source_investment_manager_info"] == "附件经理信息"
    assert report_templates.json()[0]["key"] == "builtin:weekly"
    assert report_fields.status_code == 200
    assert report_field_updated.status_code == 200
    assert next(
        item for item in report_field_updated.json()["fields"] if item["key"] == "inception_date"
    )["is_manual"] is True
    assert contract_uploaded.status_code == 200
    assert (
        contract_uploaded.json()["extracted_fields"]["manager_name"]
        == "吉余私募基金管理有限公司"
    )
    assert report_preview.status_code == 200
    assert report_preview.json()["nav_series"][-1]["unit_nav"] == "1.12345678"
    assert report_definition.status_code == 200
    assert report_generated.status_code == 200
    assert report_runs.json()[0]["status"] == "success"
    assert report_download.status_code == 200
    assert report_download.content.startswith(b"PK")
    assert exceptions.json()["items"][0]["category"] == "净值为空"
    assert other_exceptions.json()["total"] == 1
    assert exceptions.json()["items"][0]["email_id"] == 1
    assert other_exceptions.json()["items"][0]["category"] == "其他异常"
    assert resolved.json()["status"] == "resolved"
    assert audit_events.status_code == 200
    assert audit_events.json()["total"] >= 5
    assert all(item["event_hash"] for item in audit_events.json()["items"])
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
    from app.services.auth_service import AuthService

    with get_database_manager().session_factory() as session, session.begin():
        AuthService().create_user(
            session,
            username="viewer",
            password="ViewerPass!2026",
            role=UserRole.VIEWER,
            tenant_id=1,
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
        product_profile_forbidden = client.patch(
            "/api/v1/fund-products/1/profile",
            json={"investment_manager_info": "越权修改"},
        )

    assert login.status_code == 200
    assert readable.status_code == 200
    assert email_readable.status_code == 200
    assert forbidden.status_code == 403
    assert connection_forbidden.status_code == 403
    assert sync_forbidden.status_code == 403
    assert product_profile_forbidden.status_code == 403
