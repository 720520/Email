from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[FastAPI, None, None]:
    """每个测试使用独立 SQLite 和日志目录，避免污染业务数据。"""

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        yaml.safe_dump(
            {
                "app": {"environment": "test", "debug": False},
                "database": {"url": f"sqlite:///{(tmp_path / 'test.db').as_posix()}"},
                "logging": {"directory": str(tmp_path / "logs")},
                "storage": {"data_directory": str(tmp_path / "data")},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("FUND_NAV_CONFIG_FILE", str(config_file))
    # 测试必须与开发机 .env 完全隔离，避免本机密钥或邮箱配置污染断言。
    monkeypatch.setenv(
        "FUND_NAV_SECURITY__SECRET_KEY",
        "test-only-session-secret-with-at-least-32-characters",
    )
    monkeypatch.setenv("FUND_NAV_EMAIL__HOST", "")
    monkeypatch.setenv("FUND_NAV_EMAIL__USERNAME", "")
    monkeypatch.setenv("FUND_NAV_EMAIL__PASSWORD", "")
    monkeypatch.setenv("FUND_NAV_EMAIL__OAUTH2_ACCESS_TOKEN", "")

    from app.core.config import get_settings
    from app.db.session import get_database_manager

    get_database_manager.cache_clear()
    get_settings.cache_clear()

    from app.main import create_app

    application = create_app()
    yield application

    manager = get_database_manager()
    manager.dispose()
    get_database_manager.cache_clear()
    get_settings.cache_clear()
