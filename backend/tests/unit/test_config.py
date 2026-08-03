from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import PROJECT_ROOT, Settings


def test_environment_overrides_yaml_values(monkeypatch) -> None:
    monkeypatch.setenv("FUND_NAV_DATABASE__ECHO", "true")

    settings = Settings(database={"echo": False})

    assert settings.database.echo is True


def test_relative_paths_resolve_from_project_root() -> None:
    settings = Settings(
        database={"url": "sqlite:///./data/example.db"},
        storage={"data_directory": "data"},
    )

    assert settings.data_directory == (PROJECT_ROOT / "data").resolve()
    assert settings.database_url.startswith("sqlite:///")
    assert Path(settings.database_url.removeprefix("sqlite:///")) == (
        PROJECT_ROOT / "data/example.db"
    ).resolve()


def test_secret_is_masked(monkeypatch) -> None:
    monkeypatch.setenv("FUND_NAV_EMAIL__PASSWORD", "mail-secret")
    settings = Settings()

    assert "mail-secret" not in repr(settings.email.password)
    assert settings.email.password.get_secret_value() == "mail-secret"


@pytest.mark.parametrize("filename", ["../report.xlsx", "report.xls", ""])
def test_daily_export_filename_rejects_path_escape_and_non_xlsx(filename: str) -> None:
    with pytest.raises(ValidationError):
        Settings(storage={"daily_export_filename": filename})
