from __future__ import annotations

from datetime import date

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from app.api.deps import TenantContext
from app.api.v1.onlyoffice import get_onlyoffice_file, save_onlyoffice_callback
from app.api.v1.reports import create_onlyoffice_view_session
from app.core.config import OnlyOfficeSettings
from app.core.errors import AppError
from app.core.files import atomic_write_bytes
from app.db.models import FundProduct, ReportFileVersion, ReportRun, UserRole
from app.services.onlyoffice_service import OnlyOfficeService


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
    )


@pytest.mark.anyio
async def test_viewer_session_file_access_and_tenant_isolation(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    from app.core.config import get_settings
    from app.db.session import configure_tenant_scope, get_database_manager
    from app.services.auth_service import AuthService
    from app.services.foundation_service import FoundationService

    manager = get_database_manager()
    with manager.session_factory() as session:
        identity = FoundationService(get_settings()).ensure(session)
        user = AuthService().create_user(
            session,
            username="onlyoffice-viewer",
            password="ViewerPass!2026",
            role=UserRole.VIEWER,
            tenant_id=identity.tenant_id,
        )
        configure_tenant_scope(
            session,
            tenant_id=identity.tenant_id,
            mailbox_ids=(identity.mailbox_account_id,),
        )
        product = FundProduct(
            tenant_id=identity.tenant_id,
            product_code="OO-001",
            product_name="OnlyOffice 测试基金",
        )
        session.add(product)
        session.flush()
        run = ReportRun(
            tenant_id=identity.tenant_id,
            fund_product_id=product.id,
            template_key="builtin:weekly",
            report_date=date(2026, 8, 21),
            status="success",
        )
        session.add(run)
        session.flush()
        relative_path = "tenants/1/reporting/runs/onlyoffice-test.pptx"
        content = b"PK\x03\x04onlyoffice-test"
        atomic_write_bytes(get_settings().data_directory / relative_path, content)
        version = ReportFileVersion(
            tenant_id=identity.tenant_id,
            report_run_id=run.id,
            version=1,
            source="generated",
            filename="onlyoffice-test.pptx",
            stored_path=relative_path,
            content_hash="a" * 64,
            file_size=len(content),
            created_by_user_id=user.id,
        )
        session.add(version)
        session.flush()
        run.current_version_id = version.id
        session.commit()
        scope = TenantContext(
            user=user,
            tenant_id=identity.tenant_id,
            tenant_code="default",
            tenant_name="默认业务账套",
            role=UserRole.VIEWER,
            mailbox_ids=(identity.mailbox_account_id,),
            content_mailbox_ids=(identity.mailbox_account_id,),
            operable_mailbox_ids=(),
            manageable_mailbox_ids=(),
        )
        monkeypatch.setattr(OnlyOfficeService, "ensure_ready", lambda self: None)
        result = create_onlyoffice_view_session(
            run.id,
            _request(f"/api/v1/reports/runs/{run.id}/onlyoffice/session"),
            session,
            scope,
        )
        assert result.config["editorConfig"]["mode"] == "view"
        assert result.config["document"]["permissions"]["edit"] is False
        file_token = str(result.config["document"]["url"]).rsplit("/", 1)[1]

    with manager.session_factory() as public_session:
        response = get_onlyoffice_file(file_token, public_session)
        assert str(response.path).endswith("onlyoffice-test.pptx")

        token_service = OnlyOfficeService(get_settings().onlyoffice)
        wrong_tenant = token_service.create_file_token(
            tenant_id=identity.tenant_id + 1,
            run_id=run.id,
            version_id=version.id,
        )
        with pytest.raises(AppError) as error:
            get_onlyoffice_file(wrong_tenant, public_session)
        assert error.value.status_code == 404


def test_onlyoffice_unavailable_keeps_clear_error(app: FastAPI) -> None:
    del app
    service = OnlyOfficeService(OnlyOfficeSettings(enabled=False))
    from app.services.onlyoffice_service import OnlyOfficeUnavailableError

    with pytest.raises(OnlyOfficeUnavailableError, match="尚未启用"):
        service.ensure_ready()


@pytest.mark.anyio
async def test_operator_can_edit_and_callback_creates_file_version(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app
    from app.api.v1 import onlyoffice as onlyoffice_api
    from app.core.config import get_settings
    from app.db.session import configure_tenant_scope, get_database_manager
    from app.services.auth_service import AuthService
    from app.services.foundation_service import FoundationService

    manager = get_database_manager()
    with manager.session_factory() as session:
        identity = FoundationService(get_settings()).ensure(session)
        user = AuthService().create_user(
            session,
            username="onlyoffice-operator",
            password="OperatorPass!2026",
            role=UserRole.OPERATOR,
            tenant_id=identity.tenant_id,
        )
        configure_tenant_scope(
            session,
            tenant_id=identity.tenant_id,
            mailbox_ids=(identity.mailbox_account_id,),
        )
        product = FundProduct(
            tenant_id=identity.tenant_id,
            product_code="OO-EDIT-001",
            product_name="OnlyOffice 编辑测试基金",
        )
        session.add(product)
        session.flush()
        run = ReportRun(
            tenant_id=identity.tenant_id,
            fund_product_id=product.id,
            template_key="builtin:weekly",
            report_date=date(2026, 8, 21),
            status="success",
            output_filename="onlyoffice-edit.pptx",
        )
        session.add(run)
        session.flush()
        relative_path = f"tenants/{identity.tenant_id}/reporting/runs/edit-source.pptx"
        atomic_write_bytes(get_settings().data_directory / relative_path, b"source")
        version = ReportFileVersion(
            tenant_id=identity.tenant_id,
            report_run_id=run.id,
            version=1,
            source="generated",
            filename="onlyoffice-edit.pptx",
            stored_path=relative_path,
            content_hash="b" * 64,
            file_size=6,
            created_by_user_id=user.id,
        )
        session.add(version)
        session.flush()
        run.current_version_id = version.id
        session.commit()
        scope = TenantContext(
            user=user,
            tenant_id=identity.tenant_id,
            tenant_code="default",
            tenant_name="默认业务账套",
            role=UserRole.OPERATOR,
            mailbox_ids=(identity.mailbox_account_id,),
            content_mailbox_ids=(identity.mailbox_account_id,),
            operable_mailbox_ids=(identity.mailbox_account_id,),
            manageable_mailbox_ids=(),
        )
        monkeypatch.setattr(OnlyOfficeService, "ensure_ready", lambda self: None)
        result = create_onlyoffice_view_session(
            run.id,
            _request(f"/api/v1/reports/runs/{run.id}/onlyoffice/session"),
            session,
            scope,
        )
        assert result.config["editorConfig"]["mode"] == "edit"
        assert result.config["document"]["permissions"]["edit"] is True
        callback_token = str(result.config["editorConfig"]["callbackUrl"]).rsplit("/", 1)[1]

    edited_content = b"edited-pptx-content"
    monkeypatch.setattr(
        onlyoffice_api,
        "_download_edited_pptx",
        lambda url: edited_content,
    )
    with manager.session_factory() as callback_session:
        response = await save_onlyoffice_callback(
            callback_token,
            {"status": 2, "url": "http://127.0.0.1:8080/cache/edited.pptx"},
            callback_session,
        )
        assert response == {"error": 0}
        saved_run = callback_session.get(ReportRun, run.id)
        saved = callback_session.get(ReportFileVersion, saved_run.current_version_id)
        assert saved.version == 2
        assert saved.source == "onlyoffice"
        assert (get_settings().data_directory / saved.stored_path).read_bytes() == edited_content
