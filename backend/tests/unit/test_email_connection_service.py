from app.core.config import EmailSettings
from app.email.imap_client import MailboxAuthenticationError
from app.services.email_connection_service import EmailConnectionService


class SuccessfulGateway:
    uid_validity = "20260729"
    message_count = 36

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        del exc_type, exc_value, traceback


class FailedGateway:
    def __enter__(self):
        raise MailboxAuthenticationError("IMAP 账号或授权码验证失败")

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        del exc_type, exc_value, traceback


def test_email_connection_service_reports_configuration_without_secret() -> None:
    service = EmailConnectionService(
        EmailSettings(
            host="imap.example.com",
            username="operations@example.com",
            password="authorization-code",
            use_ssl=True,
        )
    )

    assert service.configured is True
    assert service.credential_configured is True
    assert service.transport == "SSL/TLS"


def test_email_connection_service_reports_success_and_mailbox_count() -> None:
    service = EmailConnectionService(
        EmailSettings(host="imap.example.com", username="ops@example.com", password="code"),
        gateway_factory=SuccessfulGateway,
    )

    result = service.test_connection()

    assert result.success is True
    assert result.uid_validity == "20260729"
    assert result.message_count == 36
    assert result.latency_ms >= 0


def test_email_connection_service_returns_safe_authentication_failure() -> None:
    service = EmailConnectionService(
        EmailSettings(host="imap.example.com", username="ops@example.com", password="code"),
        gateway_factory=FailedGateway,
    )

    result = service.test_connection()

    assert result.success is False
    assert result.message == "IMAP 账号或授权码验证失败"
    assert result.uid_validity is None
