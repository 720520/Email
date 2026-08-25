"""邮件同步编排服务。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Protocol

from app.core.config import Settings
from app.email.imap_client import (
    ImapMailboxGateway,
    MailboxAuthenticationError,
    MailboxConfigurationError,
    MailboxConnectionError,
    MailboxProtocolError,
)
from app.email.mime_parser import MimeMessageParser
from app.email.models import (
    ArchivedEmail,
    EmailSyncError,
    EmailSyncResult,
    MailboxMessage,
    MailboxMessageMetadata,
    ParsedEmail,
)
from app.email.uid_registry import FileUidRegistry
from app.services.archive_service import (
    AttachmentTooLargeError,
    EmailArchiveService,
    EmailResourceLimitError,
)

logger = logging.getLogger(__name__)


class MailboxGateway(Protocol):
    mailbox_key: str
    uid_validity: str

    def __enter__(self) -> MailboxGateway: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def search_uids(self) -> list[int]: ...

    def fetch_message(self, uid: int) -> MailboxMessage: ...

    def fetch_metadata(self, uid: int) -> MailboxMessageMetadata: ...


class ArchiveRecorder(Protocol):
    def record(
        self,
        *,
        mailbox_key: str,
        uid_validity: str,
        source: MailboxMessage,
        parsed: ParsedEmail,
        archive: ArchivedEmail,
    ) -> object: ...


class EmailSyncService:
    """编排“搜索 → 幂等预留 → 初筛 → 归档 → 完成登记”。"""

    def __init__(
        self,
        settings: Settings,
        *,
        gateway_factory: Callable[[], MailboxGateway] | None = None,
        parser: MimeMessageParser | None = None,
        archive_service: EmailArchiveService | None = None,
        uid_registry: FileUidRegistry | None = None,
        archive_recorder: ArchiveRecorder | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self.gateway_factory = gateway_factory or (lambda: ImapMailboxGateway(settings.email))
        self.parser = parser or MimeMessageParser()
        self.archive_service = archive_service or EmailArchiveService(
            settings.data_directory,
            archive_timezone=settings.storage.archive_timezone,
            max_attachment_bytes=settings.email.max_attachment_bytes,
            max_attachments_per_email=settings.email.max_attachments_per_email,
            max_total_attachment_bytes=settings.email.max_total_attachment_bytes,
            max_raw_message_bytes=settings.email.max_raw_message_bytes,
        )
        self.uid_registry = uid_registry or FileUidRegistry(
            settings.data_directory / ".email_uid_state",
            stale_seconds=settings.email.uid_reservation_stale_seconds,
        )
        self.archive_recorder = archive_recorder
        self.sleep = sleep

    def sync(self) -> EmailSyncResult:
        """同步新邮件；连接故障按指数退避重试，认证和配置错误不重试。"""

        result = EmailSyncResult()
        for attempt in range(1, self.settings.email.retry_attempts + 1):
            result.attempts = attempt
            try:
                self._sync_once(result)
                break
            except (
                MailboxConfigurationError,
                MailboxAuthenticationError,
                MailboxProtocolError,
            ) as exc:
                result.fatal_error = str(exc)
                result.errors.append(
                    EmailSyncError(uid=None, error_type=type(exc).__name__, message=str(exc))
                )
                logger.error("邮箱配置或认证失败", extra={"error_type": type(exc).__name__})
                break
            except MailboxConnectionError as exc:
                if attempt >= self.settings.email.retry_attempts:
                    result.fatal_error = str(exc)
                    result.errors.append(
                        EmailSyncError(uid=None, error_type=type(exc).__name__, message=str(exc))
                    )
                    logger.error(
                        "IMAP 网络重试耗尽",
                        extra={"attempts": attempt},
                        exc_info=True,
                    )
                    break

                delay = self.settings.email.retry_base_delay_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "IMAP 连接失败，准备重试",
                    extra={"attempt": attempt, "retry_delay_seconds": delay},
                )
                self.sleep(delay)
        return result

    def _sync_once(self, result: EmailSyncResult) -> None:
        gateway = self.gateway_factory()
        result.mailbox_key = gateway.mailbox_key
        with gateway as mailbox:
            operation_key = f"{mailbox.mailbox_key}_{mailbox.uid_validity}"
            uids = mailbox.search_uids()
            result.discovered_uids.update(uids)
            logger.info("完成 IMAP 邮件搜索", extra={"message_count": len(uids)})

            for uid in uids:
                if uid in result.archived_uids or uid in result.ignored_uids:
                    continue
                if not self.uid_registry.reserve(operation_key, uid):
                    result.duplicate_uids.add(uid)
                    continue
                self._process_reserved_message(mailbox, operation_key, uid, result)

    def _process_reserved_message(
        self,
        mailbox: MailboxGateway,
        operation_key: str,
        uid: int,
        result: EmailSyncResult,
    ) -> None:
        try:
            metadata_fetch = getattr(mailbox, "fetch_metadata", None)
            if callable(metadata_fetch):
                try:
                    metadata = metadata_fetch(uid)
                except MailboxProtocolError:
                    # 元数据预筛选只是性能优化；部分 IMAP 服务返回的 BODYSTRUCTURE
                    # 不标准时回退到完整邮件，不能让兼容性问题阻断同步。
                    logger.warning(
                        "IMAP 邮件元数据格式不兼容，回退到完整邮件下载",
                        extra={"uid": uid},
                        exc_info=True,
                    )
                else:
                    if (
                        metadata.raw_size is not None
                        and metadata.raw_size > self.settings.email.max_raw_message_bytes
                    ):
                        raise EmailResourceLimitError(
                            "原始邮件超过大小限制 "
                            f"({metadata.raw_size} > "
                            f"{self.settings.email.max_raw_message_bytes})"
                        )
                    if not self._is_candidate(metadata.subject, list(metadata.attachment_names)):
                        self.uid_registry.complete(
                            operation_key,
                            uid,
                            {"status": "ignored", "subject": metadata.subject},
                        )
                        result.ignored_uids.add(uid)
                        return
            source = mailbox.fetch_message(uid)
            if len(source.raw_message) > self.settings.email.max_raw_message_bytes:
                raise EmailResourceLimitError(
                    "原始邮件超过大小限制 "
                    f"({len(source.raw_message)} > {self.settings.email.max_raw_message_bytes})"
                )
            parsed = self.parser.parse(source)
            attachment_names = [attachment.original_name for attachment in parsed.attachments]
            if not self._is_candidate(parsed.subject, attachment_names):
                self.uid_registry.complete(
                    operation_key,
                    uid,
                    {"status": "ignored", "subject": parsed.subject},
                )
                result.ignored_uids.add(uid)
                return

            archive = self.archive_service.archive(operation_key, source, parsed)
            if self.archive_recorder is not None:
                self.archive_recorder.record(
                    mailbox_key=mailbox.mailbox_key,
                    uid_validity=mailbox.uid_validity,
                    source=source,
                    parsed=parsed,
                    archive=archive,
                )
            self.uid_registry.complete(
                operation_key,
                uid,
                {
                    "status": "archived",
                    "subject": parsed.subject,
                    "manifest_path": str(archive.manifest_path),
                },
            )
            result.archived_uids.add(uid)
            result.archives.append(archive)
            logger.info(
                "基金净值候选邮件归档成功",
                extra={"uid": uid, "attachment_count": len(archive.attachments)},
            )
        except MailboxConnectionError:
            self.uid_registry.release(operation_key, uid)
            raise
        except (AttachmentTooLargeError, EmailResourceLimitError) as exc:
            # 资源超限是确定性失败，释放预留会导致同一封“毒邮件”在每次同步中
            # 被重复下载和解析。登记为已拒绝，保留失败统计但不再自动重试。
            self.uid_registry.complete(
                operation_key,
                uid,
                {
                    "status": "rejected",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
            )
            result.failed_uids.add(uid)
            result.errors.append(
                EmailSyncError(uid=uid, error_type=type(exc).__name__, message=str(exc))
            )
            logger.warning(
                "邮件因资源限制被拒绝，后续同步不再重复处理",
                extra={"uid": uid, "error_type": type(exc).__name__},
            )
        except Exception as exc:
            self.uid_registry.release(operation_key, uid)
            result.failed_uids.add(uid)
            result.errors.append(
                EmailSyncError(uid=uid, error_type=type(exc).__name__, message=str(exc))
            )
            logger.exception("单封邮件处理失败", extra={"uid": uid})

    def _is_candidate(self, subject: str, attachment_names: list[str]) -> bool:
        """标题或附件名命中关键词，或带 Excel 附件时进入后续字段识别。"""

        searchable_text = " ".join([subject, *attachment_names]).casefold()
        normalized_text = "".join(searchable_text.split())
        has_keyword = any(
            "".join(keyword.casefold().split()) in normalized_text
            for keyword in self.settings.email.candidate_keywords
            if keyword.strip()
        )
        extensions = {extension.casefold() for extension in self.settings.email.excel_extensions}
        has_excel_attachment = any(
            Path(name).suffix.casefold() in extensions for name in attachment_names
        )
        return has_keyword or has_excel_attachment
