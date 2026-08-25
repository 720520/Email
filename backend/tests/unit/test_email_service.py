from __future__ import annotations

from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from types import TracebackType

from app.core.config import Settings
from app.email.imap_client import MailboxConnectionError, MailboxProtocolError
from app.email.models import (
    ArchivedEmail,
    MailboxMessage,
    MailboxMessageMetadata,
    ParsedEmail,
)
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
    assert second_result.duplicate_uids == {1, 2, 3}
    assert not second_result.failed_uids
    assert len(list((tmp_path / "data").rglob("*.eml"))) == 1
    assert recorder.calls[0]["uid_validity"] == "12345"
    rejected_state = next((tmp_path / "data" / ".email_uid_state").rglob("1.done.json"))
    assert '"status": "rejected"' in rejected_state.read_text(encoding="utf-8")


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


def test_metadata_prefilter_skips_full_download_for_irrelevant_mail(tmp_path: Path) -> None:
    timestamp = datetime(2026, 7, 24, 10, tzinfo=UTC)
    messages = {
        2: MailboxMessage(2, timestamp, _raw_email("基金净值", "净值.xlsx")),
        1: MailboxMessage(1, timestamp, _raw_email("普通通知")),
    }

    class MetadataGateway(FakeGateway):
        def __init__(self):
            super().__init__(messages)
            self.full_fetches: list[int] = []

        def fetch_metadata(self, uid: int) -> MailboxMessageMetadata:
            return MailboxMessageMetadata(
                uid=uid,
                subject="基金净值" if uid == 2 else "普通通知",
                attachment_names=("净值.xlsx",) if uid == 2 else (),
                raw_size=1024,
            )

        def fetch_message(self, uid: int) -> MailboxMessage:
            self.full_fetches.append(uid)
            return super().fetch_message(uid)

    gateway = MetadataGateway()
    result = EmailSyncService(
        _settings(tmp_path),
        gateway_factory=lambda: gateway,
        archive_recorder=FakeArchiveRecorder(),
        sleep=lambda _: None,
    ).sync()

    assert result.archived_uids == {2}
    assert result.ignored_uids == {1}
    assert gateway.full_fetches == [2]


def test_metadata_protocol_error_falls_back_to_full_message(tmp_path: Path) -> None:
    timestamp = datetime(2026, 7, 24, 10, tzinfo=UTC)
    messages = {7: MailboxMessage(7, timestamp, _raw_email("基金净值", "净值.xlsx"))}

    class IncompatibleMetadataGateway(FakeGateway):
        def __init__(self):
            super().__init__(messages)
            self.full_fetches: list[int] = []

        def fetch_metadata(self, uid: int) -> MailboxMessageMetadata:
            raise MailboxProtocolError(f"invalid BODYSTRUCTURE for {uid}")

        def fetch_message(self, uid: int) -> MailboxMessage:
            self.full_fetches.append(uid)
            return super().fetch_message(uid)

    gateway = IncompatibleMetadataGateway()
    result = EmailSyncService(
        _settings(tmp_path),
        gateway_factory=lambda: gateway,
        archive_recorder=FakeArchiveRecorder(),
        sleep=lambda _: None,
    ).sync()

    assert result.archived_uids == {7}
    assert not result.failed_uids
    assert gateway.full_fetches == [7]
