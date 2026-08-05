"""邮箱凭据加密和审计签名密钥派生。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import SecuritySettings

logger = logging.getLogger(__name__)
_CREDENTIAL_PREFIX = "aesgcm-v1:"


class CredentialDecryptionError(ValueError):
    """密文损坏、密钥不匹配或邮箱作用域被替换。"""


class MailboxCredentialCipher:
    """使用 AES-256-GCM 加密邮箱授权码或 OAuth 令牌。"""

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("邮箱凭据加密密钥必须为 32 字节")
        self._cipher = AESGCM(key)

    @classmethod
    def from_security_settings(cls, settings: SecuritySettings) -> MailboxCredentialCipher:
        key = _purpose_key(
            configured=settings.credential_encryption_key.get_secret_value(),
            fallback=settings.secret_key.get_secret_value(),
            purpose=b"fund-nav/mailbox-credential/v1",
        )
        return cls(key)

    def encrypt(self, plaintext: str, *, tenant_id: int, mailbox_account_id: int) -> str:
        if not plaintext:
            raise ValueError("不能加密空邮箱凭据")
        nonce = secrets.token_bytes(12)
        ciphertext = self._cipher.encrypt(
            nonce,
            plaintext.encode("utf-8"),
            _associated_data(tenant_id, mailbox_account_id),
        )
        encoded = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
        return f"{_CREDENTIAL_PREFIX}{encoded}"

    def decrypt(self, value: str, *, tenant_id: int, mailbox_account_id: int) -> str:
        if not value.startswith(_CREDENTIAL_PREFIX):
            raise CredentialDecryptionError("邮箱凭据密文版本不受支持")
        try:
            payload = base64.urlsafe_b64decode(value.removeprefix(_CREDENTIAL_PREFIX))
            plaintext = self._cipher.decrypt(
                payload[:12],
                payload[12:],
                _associated_data(tenant_id, mailbox_account_id),
            )
            return plaintext.decode("utf-8")
        except Exception as exc:
            raise CredentialDecryptionError("邮箱凭据解密失败") from exc


def audit_signing_key(settings: SecuritySettings) -> bytes:
    return _purpose_key(
        configured=settings.audit_signing_key.get_secret_value(),
        fallback=settings.secret_key.get_secret_value(),
        purpose=b"fund-nav/audit-signing/v1",
    )


def dedicated_credential_key_configured(settings: SecuritySettings) -> bool:
    return bool(settings.credential_encryption_key.get_secret_value())


def dedicated_audit_key_configured(settings: SecuritySettings) -> bool:
    return bool(settings.audit_signing_key.get_secret_value())


def _purpose_key(*, configured: str, fallback: str, purpose: bytes) -> bytes:
    if configured:
        decoded = _decode_key(configured)
        if len(decoded) != 32:
            raise ValueError("安全密钥必须是 URL-safe Base64 编码的 32 字节随机值")
        return decoded
    logger.warning("未配置独立业务密钥，开发环境暂时从会话密钥派生")
    return hmac.new(fallback.encode("utf-8"), purpose, hashlib.sha256).digest()


def _decode_key(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(f"{value}{padding}")
    except (ValueError, TypeError) as exc:
        raise ValueError("安全密钥不是有效的 URL-safe Base64") from exc


def _associated_data(tenant_id: int, mailbox_account_id: int) -> bytes:
    return f"tenant:{tenant_id}:mailbox:{mailbox_account_id}:credential:v1".encode("ascii")
