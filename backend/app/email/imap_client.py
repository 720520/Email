"""IMAPClient 协议适配器。"""

from __future__ import annotations

import hashlib
import logging
import ssl
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any

from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError, LoginError

from app import __version__
from app.core.config import EmailSettings
from app.email.models import MailboxMessage

logger = logging.getLogger(__name__)


class MailboxError(RuntimeError):
    """邮箱访问错误基类。"""


class MailboxConfigurationError(MailboxError):
    pass


class MailboxAuthenticationError(MailboxError):
    pass


class MailboxConnectionError(MailboxError):
    pass


class MailboxProtocolError(MailboxError):
    pass


class ImapMailboxGateway:
    """只读访问 IMAP 邮箱，使用 UID 搜索且不改变邮件已读状态。"""

    def __init__(self, settings: EmailSettings) -> None:
        self.settings = settings
        self._client: IMAPClient | None = None
        self.uid_validity = "0"
        self.message_count: int | None = None
        identity = f"{settings.host}\0{settings.username.casefold()}\0{settings.folder}"
        self.mailbox_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

    def __enter__(self) -> ImapMailboxGateway:
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.close()

    def connect(self) -> None:
        self._validate_configuration()
        client: IMAPClient | None = None
        try:
            client = IMAPClient(
                self.settings.host,
                port=self.settings.port,
                use_uid=True,
                ssl=self.settings.use_ssl,
                ssl_context=self.ssl_context if self.settings.use_ssl else None,
                timeout=self.settings.timeout_seconds,
            )
            if self.settings.start_tls:
                client.starttls(self.ssl_context)
            if self.settings.auth_mode == "oauth2":
                client.oauth2_login(
                    self.settings.username,
                    self.settings.oauth2_access_token.get_secret_value(),
                )
            else:
                client.login(
                    self.settings.username,
                    self.settings.password.get_secret_value(),
                )
            self._identify_client_if_supported(client)
            folder_info = client.select_folder(self.settings.folder, readonly=True)
            uid_validity = self._get_response_value(
                folder_info,
                (b"UIDVALIDITY", "UIDVALIDITY"),
            )
            self.uid_validity = self._normalize_uid_validity(uid_validity)
            exists = self._get_response_value(folder_info, (b"EXISTS", "EXISTS"))
            self.message_count = self._normalize_optional_count(exists)
            self._client = client
            logger.info(
                "IMAP 邮箱连接成功",
                extra={"host": self.settings.host, "folder": self.settings.folder},
            )
        except LoginError as exc:
            self._shutdown_quietly(client)
            raise MailboxAuthenticationError("IMAP 账号或授权码验证失败") from exc
        except (IMAPClientError, OSError, TimeoutError, ssl.SSLError) as exc:
            self._shutdown_quietly(client)
            raise MailboxConnectionError("IMAP 连接或文件夹选择失败") from exc

    def close(self) -> None:
        client, self._client = self._client, None
        if client is None:
            return
        try:
            client.logout()
        except (IMAPClientError, OSError):
            logger.debug("IMAP 连接关闭时服务器未正常响应", exc_info=True)

    def search_uids(self) -> list[int]:
        client = self._require_client()
        since_date = datetime.now(UTC).date() - timedelta(days=self.settings.lookback_days)
        try:
            uids = [int(uid) for uid in client.search(["SINCE", since_date])]
        except (IMAPClientError, OSError, TimeoutError) as exc:
            raise MailboxConnectionError("搜索 IMAP 邮件失败") from exc
        return sorted(uids, reverse=True)[: self.settings.max_messages_per_run]

    def fetch_message(self, uid: int) -> MailboxMessage:
        client = self._require_client()
        try:
            response = client.fetch([uid], [b"BODY.PEEK[]", b"INTERNALDATE"])
        except (IMAPClientError, OSError, TimeoutError) as exc:
            raise MailboxConnectionError(f"获取 IMAP 邮件失败，UID={uid}") from exc

        message_data = response.get(uid)
        if not isinstance(message_data, dict):
            raise MailboxProtocolError(f"IMAP 返回中缺少邮件，UID={uid}")

        raw_message = self._get_response_value(
            message_data,
            (b"BODY[]", b"BODY.PEEK[]", b"RFC822", "BODY[]", "RFC822"),
        )
        internal_date = self._get_response_value(
            message_data,
            (b"INTERNALDATE", "INTERNALDATE"),
        )
        if not isinstance(raw_message, bytes):
            raise MailboxProtocolError(f"IMAP 邮件正文格式无效，UID={uid}")
        if not isinstance(internal_date, datetime):
            raise MailboxProtocolError(f"IMAP 邮件接收时间缺失，UID={uid}")
        if internal_date.tzinfo is None:
            internal_date = internal_date.replace(tzinfo=UTC)
        return MailboxMessage(uid=uid, internal_date=internal_date, raw_message=raw_message)

    def _validate_configuration(self) -> None:
        if not self.settings.host.strip():
            raise MailboxConfigurationError("未配置 email.host")
        if not self.settings.username.strip():
            raise MailboxConfigurationError("未配置 email.username")
        if self.settings.auth_mode == "password" and not self.settings.password.get_secret_value():
            raise MailboxConfigurationError("未配置邮箱授权码")
        if (
            self.settings.auth_mode == "oauth2"
            and not self.settings.oauth2_access_token.get_secret_value()
        ):
            raise MailboxConfigurationError("未配置 Outlook OAuth2 访问令牌")

    def _require_client(self) -> IMAPClient:
        if self._client is None:
            raise MailboxConnectionError("IMAP 客户端尚未连接")
        return self._client

    @staticmethod
    def _identify_client_if_supported(client: IMAPClient) -> None:
        """向支持 RFC 2971 ID 的服务器声明客户端身份。

        网易163会在登录成功后校验客户端 ID；未发送 ID 时，选择 INBOX
        可能返回 ``Unsafe Login``。不支持 ID 的 QQ、Outlook 或普通企业
        邮箱保持原流程；服务器声明支持但拒绝 ID 时也继续尝试只读选箱。
        """

        if not client.has_capability("ID"):
            return
        try:
            client.id_(
                {
                    "name": "FundNavMailReader",
                    "version": __version__,
                    "vendor": "LocalFundOperations",
                }
            )
        except IMAPClientError:
            logger.warning("IMAP 服务器拒绝客户端 ID，继续尝试选择邮箱目录")

    @staticmethod
    def _get_response_value(message_data: dict[Any, Any], keys: tuple[Any, ...]) -> Any:
        for key in keys:
            if key in message_data:
                return message_data[key]
        return None

    @staticmethod
    def _normalize_uid_validity(value: Any) -> str:
        if isinstance(value, bytes):
            value = value.decode("ascii", errors="strict")
        try:
            normalized = str(int(value))
        except (TypeError, ValueError) as exc:
            raise MailboxProtocolError("IMAP 文件夹缺少有效 UIDVALIDITY") from exc
        if normalized.startswith("-"):
            raise MailboxProtocolError("IMAP UIDVALIDITY 不能为负数")
        return normalized

    @staticmethod
    def _normalize_optional_count(value: Any) -> int | None:
        if value is None:
            return None
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            return None
        return normalized if normalized >= 0 else None

    @staticmethod
    def _shutdown_quietly(client: IMAPClient | None) -> None:
        if client is None:
            return
        try:
            client.shutdown()
        except (IMAPClientError, OSError):
            pass
