from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr

from app.core.config import OnlyOfficeSettings
from app.services.onlyoffice_service import OnlyOfficeService, OnlyOfficeTokenError


def _service() -> OnlyOfficeService:
    return OnlyOfficeService(
        OnlyOfficeSettings(
            enabled=True,
            jwt_secret=SecretStr("onlyoffice-test-secret-at-least-32-characters"),
            callback_base_url="http://host.docker.internal:8000",
        )
    )


def test_edit_session_has_full_editing_and_save_callback() -> None:
    service = _service()
    session = service.build_session(
        tenant_id=3,
        run_id=7,
        version_id=11,
        content_hash="a" * 64,
        filename="基金周报.pptx",
        user_id=5,
        username="viewer",
        editable=True,
    )
    config = session["config"]
    assert config["documentType"] == "slide"
    assert config["editorConfig"]["mode"] == "edit"
    assert config["editorConfig"]["customization"]["compactHeader"] is False
    assert config["editorConfig"]["customization"]["forcesave"] is True
    assert config["editorConfig"]["customization"]["zoom"] == -1
    assert config["document"]["permissions"]["edit"] is True
    assert "/api/v1/onlyoffice/callbacks/" in config["editorConfig"]["callbackUrl"]
    assert config["document"]["url"].startswith("http://host.docker.internal:8000/")
    assert len(config["token"].split(".")) == 3


def test_view_session_remains_read_only() -> None:
    service = _service()
    session = service.build_view_session(
        tenant_id=3,
        run_id=7,
        version_id=11,
        content_hash="a" * 64,
        filename="基金周报.pptx",
        user_id=5,
        username="viewer",
    )
    assert session["config"]["editorConfig"]["mode"] == "view"
    assert session["config"]["document"]["permissions"]["edit"] is False


def test_file_token_expiration_and_tampering() -> None:
    service = _service()
    token = service.create_file_token(tenant_id=1, run_id=2, version_id=3)
    claims = service.verify_file_token(token)
    assert claims["tenant_id"] == 1
    with pytest.raises(OnlyOfficeTokenError, match="过期"):
        service.verify_file_token(
            token,
            now=datetime.now(UTC) + timedelta(hours=2),
        )
    damaged = token[:-1] + ("a" if token[-1] != "a" else "b")
    with pytest.raises(OnlyOfficeTokenError, match="签名"):
        service.verify_file_token(damaged)
