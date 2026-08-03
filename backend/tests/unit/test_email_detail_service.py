from email.message import EmailMessage
from pathlib import Path

import pytest

from app.services.email_detail_service import (
    EmailDetailService,
    InvalidEmailArchivePathError,
)


def _write_message(path: Path, message: EmailMessage) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(message.as_bytes())


def test_prefers_plain_text_and_skips_attachments(tmp_path: Path) -> None:
    message = EmailMessage()
    message["Subject"] = "基金净值"
    message.set_content("您好，净值报告见附件。")
    message.add_alternative("<p>HTML 备用正文</p>", subtype="html")
    message.add_attachment(
        b"not body",
        maintype="application",
        subtype="octet-stream",
        filename="nav.xlsx",
    )
    path = tmp_path / "2026/07/29/emails/mail.eml"
    _write_message(path, message)

    service = EmailDetailService(tmp_path)
    resolved = service.resolve_archive_path("2026/07/29/emails/mail.eml")
    preview = service.body_preview(resolved)

    assert preview.text == "您好，净值报告见附件。"
    assert "HTML 备用正文" not in preview.text
    assert "not body" not in preview.text
    assert preview.truncated is False


def test_converts_html_only_message_to_safe_plain_text(tmp_path: Path) -> None:
    message = EmailMessage()
    message.set_content(
        "<html><head><style>body{display:none}</style></head>"
        "<body><script>alert('x')</script><p>单位净值：1.0256</p></body></html>",
        subtype="html",
    )
    path = tmp_path / "mail.eml"
    _write_message(path, message)

    preview = EmailDetailService(tmp_path).body_preview(path)

    assert preview.text == "单位净值：1.0256"
    assert "<script" not in preview.text
    assert "alert" not in preview.text
    assert "display:none" not in preview.text


def test_rejects_archive_path_outside_data_directory(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.eml"
    outside.write_bytes(b"Subject: test\r\n\r\nbody")

    with pytest.raises(InvalidEmailArchivePathError):
        EmailDetailService(tmp_path).resolve_archive_path(str(outside))
