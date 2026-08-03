"""原始邮件和附件安全归档。"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.files import atomic_write_bytes
from app.email.models import ArchivedAttachment, ArchivedEmail, MailboxMessage, ParsedEmail

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class AttachmentTooLargeError(ValueError):
    """附件超过配置的安全上限。"""


class EmailArchiveService:
    """按邮件接收日期写入 EML、附件和审计清单。"""

    def __init__(
        self,
        data_directory: Path,
        *,
        archive_timezone: str,
        max_attachment_bytes: int,
    ) -> None:
        self.data_directory = data_directory
        self.timezone = ZoneInfo(archive_timezone)
        self.max_attachment_bytes = max_attachment_bytes

    def archive(
        self,
        mailbox_key: str,
        source: MailboxMessage,
        parsed: ParsedEmail,
    ) -> ArchivedEmail:
        self._validate_attachments(parsed)
        receive_time = parsed.receive_time
        if receive_time.tzinfo is None:
            receive_time = receive_time.replace(tzinfo=UTC)
        local_date = receive_time.astimezone(self.timezone).date()
        daily_directory = (
            self.data_directory
            / f"{local_date.year:04d}"
            / f"{local_date.month:02d}"
            / f"{local_date.day:02d}"
        )
        email_directory = daily_directory / "emails"
        attachment_directory = daily_directory / "attachments"
        email_directory.mkdir(parents=True, exist_ok=True)
        attachment_directory.mkdir(parents=True, exist_ok=True)

        archive_stem = f"{mailbox_key}_{source.uid}"
        eml_path = email_directory / f"{archive_stem}.eml"
        atomic_write_bytes(eml_path, source.raw_message)

        archived_attachments: list[ArchivedAttachment] = []
        for attachment in parsed.attachments:
            safe_name = sanitize_filename(attachment.original_name)
            stored_name = f"{archive_stem}_{attachment.part_index:03d}_{safe_name}"
            stored_path = attachment_directory / stored_name
            atomic_write_bytes(stored_path, attachment.content)
            archived_attachments.append(
                ArchivedAttachment(
                    original_name=attachment.original_name,
                    stored_path=stored_path,
                    content_type=attachment.content_type,
                    size=len(attachment.content),
                    sha256=hashlib.sha256(attachment.content).hexdigest(),
                )
            )

        manifest_path = email_directory / f"{archive_stem}.json"
        manifest = {
            "mailbox_key": mailbox_key,
            "uid": source.uid,
            "message_id": parsed.message_id,
            "subject": parsed.subject,
            "sender": parsed.sender,
            "receive_time": receive_time.isoformat(),
            "eml_path": self._relative_path(eml_path),
            "attachments": [
                {
                    "original_name": item.original_name,
                    "stored_path": self._relative_path(item.stored_path),
                    "content_type": item.content_type,
                    "size": item.size,
                    "sha256": item.sha256,
                }
                for item in archived_attachments
            ],
        }
        atomic_write_bytes(
            manifest_path,
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        return ArchivedEmail(
            uid=source.uid,
            eml_path=eml_path,
            manifest_path=manifest_path,
            attachments=tuple(archived_attachments),
        )

    def _validate_attachments(self, parsed: ParsedEmail) -> None:
        for attachment in parsed.attachments:
            if len(attachment.content) > self.max_attachment_bytes:
                raise AttachmentTooLargeError(
                    f"附件超过大小限制: {attachment.original_name} "
                    f"({len(attachment.content)} > {self.max_attachment_bytes})"
                )

    def _relative_path(self, path: Path) -> str:
        return path.relative_to(self.data_directory).as_posix()

def sanitize_filename(filename: str, *, max_length: int = 180) -> str:
    """移除路径与 Windows 非法字符，阻止路径穿越和保留名冲突。"""

    name = Path(filename.replace("\\", "/")).name.strip().rstrip(". ")
    name = _INVALID_FILENAME_CHARS.sub("_", name)
    if not name:
        name = "attachment.bin"

    stem = Path(name).stem
    suffix = Path(name).suffix
    if stem.upper() in _WINDOWS_RESERVED_NAMES:
        stem = f"_{stem}"
    available_stem_length = max(1, max_length - len(suffix))
    return f"{stem[:available_stem_length]}{suffix}"[:max_length]
