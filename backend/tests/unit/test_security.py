from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import (
    InvalidSessionTokenError,
    PasswordHasher,
    SessionTokenService,
)


def test_password_hasher_never_stores_plaintext_and_verifies() -> None:
    hasher = PasswordHasher()
    encoded = hasher.hash("StrongPass!2026")

    assert "StrongPass!2026" not in encoded
    assert encoded.startswith("scrypt$")
    assert hasher.verify("StrongPass!2026", encoded) is True
    assert hasher.verify("wrong-password", encoded) is False
    assert hasher.verify("anything", "broken-hash") is False


def test_session_token_detects_tampering_and_expiration() -> None:
    now = datetime(2026, 7, 29, 10, tzinfo=UTC)
    service = SessionTokenService("a-secure-test-secret-key-123456", ttl_minutes=60)
    token = service.create(
        user_id=7,
        username="operator",
        token_version=3,
        now=now,
    )

    claims = service.verify(token, now=now + timedelta(minutes=10))
    assert claims.user_id == 7
    assert claims.username == "operator"
    assert claims.token_version == 3

    with pytest.raises(InvalidSessionTokenError):
        service.verify(f"{token}changed", now=now)
    with pytest.raises(InvalidSessionTokenError, match="过期"):
        service.verify(token, now=now + timedelta(hours=2))
