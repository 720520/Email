"""邮箱配置展示和只读连接检测。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter

from app.core.config import EmailSettings
from app.email.imap_client import ImapMailboxGateway, MailboxError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EmailConnectionCheck:
    success: bool
    message: str
    checked_at: datetime
    latency_ms: int
    uid_validity: str | None = None
    message_count: int | None = None


class EmailConnectionService:
    """复用生产 IMAP 网关验证连接，不读取邮件正文。"""

    def __init__(
        self,
        settings: EmailSettings,
        *,
        gateway_factory: Callable[[], ImapMailboxGateway] | None = None,
    ) -> None:
        self.settings = settings
        self.gateway_factory = gateway_factory or (lambda: ImapMailboxGateway(settings))

    @property
    def credential_configured(self) -> bool:
        if self.settings.auth_mode == "oauth2":
            return bool(self.settings.oauth2_access_token.get_secret_value())
        return bool(self.settings.password.get_secret_value())

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.host.strip()
            and self.settings.username.strip()
            and self.credential_configured
        )

    @property
    def transport(self) -> str:
        if self.settings.use_ssl:
            return "SSL/TLS"
        if self.settings.start_tls:
            return "STARTTLS"
        return "未加密"

    def test_connection(self) -> EmailConnectionCheck:
        started_at = perf_counter()
        checked_at = datetime.now(UTC)
        try:
            with self.gateway_factory() as gateway:
                return EmailConnectionCheck(
                    success=True,
                    message="邮箱连接、身份认证和收件箱选择均成功",
                    checked_at=checked_at,
                    latency_ms=_elapsed_ms(started_at),
                    uid_validity=gateway.uid_validity,
                    message_count=gateway.message_count,
                )
        except MailboxError as exc:
            logger.warning(
                "邮箱连接检测失败",
                extra={"error_type": type(exc).__name__, "host": self.settings.host},
            )
            return EmailConnectionCheck(
                success=False,
                message=str(exc),
                checked_at=checked_at,
                latency_ms=_elapsed_ms(started_at),
            )


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))
