"""密码哈希和无状态签名会话。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


class InvalidSessionTokenError(ValueError):
    pass


class PasswordHasher:
    """使用标准库 scrypt，避免明文或可逆密码存储。"""

    algorithm = "scrypt"
    n = 2**14
    r = 8
    p = 1
    dklen = 64

    def hash(self, password: str) -> str:
        if len(password) < 6:
            raise ValueError("密码至少需要 6 个字符")
        salt = secrets.token_bytes(16)
        digest = self._derive(password, salt)
        return "$".join(
            [
                self.algorithm,
                str(self.n),
                str(self.r),
                str(self.p),
                _encode(salt),
                _encode(digest),
            ]
        )

    def verify(self, password: str, encoded_hash: str) -> bool:
        try:
            algorithm, n, r, p, salt, expected = encoded_hash.split("$", 5)
            if algorithm != self.algorithm:
                return False
            expected_digest = _decode(expected)
            derived = hashlib.scrypt(
                password.encode("utf-8"),
                salt=_decode(salt),
                n=int(n),
                r=int(r),
                p=int(p),
                dklen=len(expected_digest),
                maxmem=64 * 1024 * 1024,
            )
            return hmac.compare_digest(derived, expected_digest)
        except (ValueError, TypeError):
            return False

    def _derive(self, password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=self.n,
            r=self.r,
            p=self.p,
            dklen=self.dklen,
            maxmem=64 * 1024 * 1024,
        )


@dataclass(frozen=True, slots=True)
class SessionClaims:
    user_id: int
    username: str
    tenant_id: int
    token_version: int
    expires_at: datetime


class SessionTokenService:
    def __init__(self, secret_key: str, *, ttl_minutes: int) -> None:
        if len(secret_key) < 24:
            raise ValueError("会话密钥至少需要 24 个字符")
        self.secret_key = secret_key.encode("utf-8")
        self.ttl = timedelta(minutes=ttl_minutes)

    def create(
        self,
        *,
        user_id: int,
        username: str,
        token_version: int,
        tenant_id: int = 1,
        now: datetime | None = None,
    ) -> str:
        issued_at = (now or datetime.now(UTC)).astimezone(UTC)
        payload = {
            "sub": user_id,
            "username": username,
            "tenant_id": tenant_id,
            "ver": token_version,
            "iat": int(issued_at.timestamp()),
            "exp": int((issued_at + self.ttl).timestamp()),
            "nonce": secrets.token_urlsafe(12),
        }
        encoded_payload = _encode(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        signature = _encode(
            hmac.new(self.secret_key, encoded_payload.encode("ascii"), hashlib.sha256).digest()
        )
        return f"{encoded_payload}.{signature}"

    def verify(self, token: str, *, now: datetime | None = None) -> SessionClaims:
        try:
            encoded_payload, encoded_signature = token.split(".", 1)
            expected_signature = hmac.new(
                self.secret_key,
                encoded_payload.encode("ascii"),
                hashlib.sha256,
            ).digest()
            if not hmac.compare_digest(expected_signature, _decode(encoded_signature)):
                raise InvalidSessionTokenError("会话签名无效")
            payload: dict[str, Any] = json.loads(_decode(encoded_payload))
            expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=UTC)
            current_time = (now or datetime.now(UTC)).astimezone(UTC)
            if expires_at <= current_time:
                raise InvalidSessionTokenError("会话已过期")
            return SessionClaims(
                user_id=int(payload["sub"]),
                username=str(payload["username"]),
                tenant_id=int(payload["tenant_id"]),
                token_version=int(payload["ver"]),
                expires_at=expires_at,
            )
        except InvalidSessionTokenError:
            raise
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise InvalidSessionTokenError("会话格式无效") from exc


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")
