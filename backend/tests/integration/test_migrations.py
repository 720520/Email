from __future__ import annotations

from pathlib import Path

import yaml
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command


def test_initial_migration_upgrade_check_and_downgrade(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump({"database": {"url": database_url}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("FUND_NAV_CONFIG_FILE", str(config_path))

    from app.core.config import get_settings

    get_settings.cache_clear()
    alembic_config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))

    command.upgrade(alembic_config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    expected_tables = {
        "alembic_version",
        "app_user",
        "attachment_record",
        "email_record",
        "exception_record",
        "fund_nav",
        "job_run",
    }
    assert set(inspector.get_table_names()) == expected_tables
    fund_nav_uniques = {item["name"] for item in inspector.get_unique_constraints("fund_nav")}
    assert "uq_fund_nav_product_code_nav_date" in fund_nav_uniques
    email_uniques = {item["name"] for item in inspector.get_unique_constraints("email_record")}
    assert "uq_email_record_mailbox_uidvalidity_uid" in email_uniques
    app_user_columns = {item["name"] for item in inspector.get_columns("app_user")}
    assert {"role", "token_version"}.issubset(app_user_columns)

    # 模型与已执行迁移必须保持一致，否则 command.check 会抛出异常。
    command.check(alembic_config)
    command.downgrade(alembic_config, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]

    engine.dispose()
    get_settings.cache_clear()
