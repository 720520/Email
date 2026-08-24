from __future__ import annotations

from pathlib import Path

from app.cli.init_security_keys import initialize_security_keys
from app.core.config import SecuritySettings


def test_initializer_adds_keys_without_printing_or_overwriting(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FUND_NAV_CONFIG_FILE=config/config.yaml\n", encoding="utf-8")

    created = initialize_security_keys(env_file)
    first_content = env_file.read_text(encoding="utf-8")
    created_again = initialize_security_keys(env_file)

    values = dict(
        line.split("=", 1)
        for line in first_content.splitlines()
        if line and not line.startswith("#")
    )
    assert len(created) == 3
    assert created_again == ()
    assert env_file.read_text(encoding="utf-8") == first_content
    assert len({values[name] for name in created}) == 3
    SecuritySettings(
        secret_key="test-session-secret-with-at-least-32-characters",
        credential_encryption_key=values[created[0]],
        audit_signing_key=values[created[1]],
    )
