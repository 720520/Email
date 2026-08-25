"""邮件同步过程中使用的轻量数据结构。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MailboxMessage:
    """从 IMAP 获取的单封原始邮件。"""

    uid: int
    internal_date: datetime
    raw_message: bytes


@dataclass(frozen=True, slots=True)
class MailboxMessageMetadata:
    """候选预筛所需的轻量 IMAP 元数据。"""

    uid: int
    subject: str
    attachment_names: tuple[str, ...]
    raw_size: int | None = None


@dataclass(frozen=True, slots=True)
class EmailAttachment:
    """从 MIME 邮件中解码出的附件。"""

    part_index: int
    original_name: str
    content_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class ParsedEmail:
    """用于归档和初筛的邮件元数据。"""

    subject: str
    sender: str
    receive_time: datetime
    message_id: str
    attachments: tuple[EmailAttachment, ...]


@dataclass(frozen=True, slots=True)
class ArchivedAttachment:
    original_name: str
    stored_path: Path
    content_type: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ArchivedEmail:
    uid: int
    eml_path: Path
    manifest_path: Path
    attachments: tuple[ArchivedAttachment, ...]


@dataclass(frozen=True, slots=True)
class EmailSyncError:
    uid: int | None
    error_type: str
    message: str


@dataclass(slots=True)
class EmailSyncResult:
    """单次邮箱同步结果，集合可避免网络重试导致重复统计。"""

    mailbox_key: str = ""
    attempts: int = 0
    discovered_uids: set[int] = field(default_factory=set)
    archived_uids: set[int] = field(default_factory=set)
    ignored_uids: set[int] = field(default_factory=set)
    duplicate_uids: set[int] = field(default_factory=set)
    failed_uids: set[int] = field(default_factory=set)
    archives: list[ArchivedEmail] = field(default_factory=list)
    errors: list[EmailSyncError] = field(default_factory=list)
    fatal_error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "mailbox_key": self.mailbox_key,
            "attempts": self.attempts,
            "discovered_count": len(self.discovered_uids),
            "archived_count": len(self.archived_uids),
            "ignored_count": len(self.ignored_uids),
            "duplicate_count": len(self.duplicate_uids),
            "failed_count": len(self.failed_uids),
            "archives": [
                {
                    "uid": archive.uid,
                    "eml_path": str(archive.eml_path),
                    "manifest_path": str(archive.manifest_path),
                    "attachment_count": len(archive.attachments),
                }
                for archive in self.archives
            ],
            "errors": [asdict(error) for error in self.errors],
            "fatal_error": self.fatal_error,
        }
