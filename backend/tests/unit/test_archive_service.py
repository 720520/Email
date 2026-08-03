import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.email.models import EmailAttachment, MailboxMessage, ParsedEmail
from app.services.archive_service import (
    AttachmentTooLargeError,
    EmailArchiveService,
    sanitize_filename,
)


def _build_source_and_email(content: bytes = b"excel") -> tuple[MailboxMessage, ParsedEmail]:
    receive_time = datetime(2026, 7, 24, 10, 30, tzinfo=UTC)
    source = MailboxMessage(uid=26, internal_date=receive_time, raw_message=b"raw-eml")
    parsed = ParsedEmail(
        subject="基金净值",
        sender="custodian@example.com",
        receive_time=receive_time,
        message_id="<26@example.com>",
        attachments=(
            EmailAttachment(
                part_index=3,
                original_name="../吉余基金净值.xlsx",
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                content=content,
            ),
        ),
    )
    return source, parsed


def test_archive_email_and_attachment_by_local_date(tmp_path: Path) -> None:
    source, parsed = _build_source_and_email()
    service = EmailArchiveService(
        tmp_path,
        archive_timezone="Asia/Shanghai",
        max_attachment_bytes=1024,
    )

    archived = service.archive("mailbox01", source, parsed)

    expected_directory = tmp_path / "2026/07/24"
    assert archived.eml_path == expected_directory / "emails/mailbox01_26.eml"
    assert archived.eml_path.read_bytes() == b"raw-eml"
    assert archived.attachments[0].stored_path.parent == expected_directory / "attachments"
    assert ".." not in archived.attachments[0].stored_path.name
    manifest = json.loads(archived.manifest_path.read_text(encoding="utf-8"))
    assert manifest["uid"] == 26
    assert manifest["attachments"][0]["original_name"] == "../吉余基金净值.xlsx"
    assert manifest["attachments"][0]["sha256"] == archived.attachments[0].sha256


def test_reject_attachment_over_size_limit_before_writing(tmp_path: Path) -> None:
    source, parsed = _build_source_and_email(content=b"12345")
    service = EmailArchiveService(
        tmp_path,
        archive_timezone="Asia/Shanghai",
        max_attachment_bytes=4,
    )

    with pytest.raises(AttachmentTooLargeError):
        service.archive("mailbox01", source, parsed)

    assert not list(tmp_path.rglob("*.eml"))


@pytest.mark.parametrize(
    ("unsafe_name", "safe_name"),
    [
        ("../../secret.xlsx", "secret.xlsx"),
        ("CON.xls", "_CON.xls"),
        ('基金<净值>:表.xlsx', "基金_净值__表.xlsx"),
    ],
)
def test_sanitize_filename(unsafe_name: str, safe_name: str) -> None:
    assert sanitize_filename(unsafe_name) == safe_name

