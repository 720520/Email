from __future__ import annotations

from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from types import TracebackType

from app.core.config import Settings
from app.email.imap_client import MailboxConnectionError
from app.email.models import ArchivedEmail, MailboxMessage, ParsedEmail
from app.services.email_service import EmailSyncService


def _raw_email(subject: str, attachment_name: str | None = None, content: bytes = b"nav") -> bytes:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = "custodian@example.com"
    message.set_content("邮件正文")
    if attachment_name:
        message.add_attachment(
            content,
            maintype="application",
            subtype="octet-stream",
            filename=attachment_name,
        )
    return message.as_bytes()


class FakeGateway:
    mailbox_key = "fake-mailbox"
    uid_validity = "12345"

    def __init__(self, messages: dict[int, MailboxMessage], *, fail_on_enter: bool = False) -> None:
        self.messages = messages
        self.fail_on_enter = fail_on_enter

    def __enter__(self) -> FakeGateway:
        if self.fail_on_enter:
            raise MailboxConnectionError("temporary connection failure")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback

    def search_uids(self) -> list[int]:
        return sorted(self.messages, reverse=True)

    def fetch_message(self, uid: int) -> MailboxMessage:
        return self.messages[uid]


class FakeArchiveRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def record(
        self,
        *,
        mailbox_key: str,
        uid_validity: str,
        source: MailboxMessage,
        parsed: ParsedEmail,
        archive: ArchivedEmail,
    ) -> None:
        self.calls.append(
            {
                "mailbox_key": mailbox_key,
                "uid_validity": uid_validity,
                "uid": source.uid,
                "subject": parsed.subject,
                "eml_path": archive.eml_path,
            }
        )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app={"environment": "test"},
        database={"url": f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}"},
        logging={"directory": str(tmp_path / "logs")},
        storage={"data_directory": str(tmp_path / "data")},
        email={
            "max_attachment_bytes": 1024,
            "retry_attempts": 3,
            "retry_base_delay_seconds": 0.5,
        },
    )


def test_sync_archives_candidates_ignores_other_mail_and_isolates_failure(tmp_path: Path) -> None:
    timestamp = datetime(2026, 7, 24, 10, tzinfo=UTC)
    messages = {
        3: MailboxMessage(3, timestamp, _raw_email("普通主题", "净值数据.xlsx")),
        2: MailboxMessage(2, timestamp, _raw_email("普通通知")),
        1: MailboxMessage(
            1,
            timestamp,
            _raw_email("基金净值", "oversize.xlsx", content=b"x" * 2048),
        ),
    }
    settings = _settings(tmp_path)
    recorder = FakeArchiveRecorder()
    service = EmailSyncService(
        settings,
        gateway_factory=lambda: FakeGateway(messages),
        archive_recorder=recorder,
        sleep=lambda _: None,
    )

    first_result = service.sync()
    second_result = service.sync()

    assert first_result.archived_uids == {3}
    assert first_result.ignored_uids == {2}
    assert first_result.failed_uids == {1}
    assert first_result.fatal_error is None
    assert second_result.duplicate_uids == {2, 3}
    assert second_result.failed_uids == {1}
    assert len(list((tmp_path / "data").rglob("*.eml"))) == 1
    assert recorder.calls[0]["uid_validity"] == "12345"


def test_connection_failure_retries_with_exponential_backoff(tmp_path: Path) -> None:
    timestamp = datetime(2026, 7, 24, 10, tzinfo=UTC)
    messages = {9: MailboxMessage(9, timestamp, _raw_email("基金净值"))}
    gateways = iter([FakeGateway(messages, fail_on_enter=True), FakeGateway(messages)])
    delays: list[float] = []
    service = EmailSyncService(
        _settings(tmp_path),
        gateway_factory=lambda: next(gateways),
        sleep=delays.append,
    )

    result = service.sync()

    assert result.attempts == 2
    assert result.archived_uids == {9}
    assert delays == [0.5]
    assert result.fatal_error is None
