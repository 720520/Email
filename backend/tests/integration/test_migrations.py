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
        "audit_event",
        "attachment_record",
        "attachment_parse_task",
        "email_record",
        "exception_record",
        "filing_profile",
        "filing_field",
        "filing_file_version",
        "fund_nav",
        "fund_nav_revision",
        "fund_product",
        "job_run",
        "mailbox_account",
        "mailbox_user_grant",
        "parse_result_row",
        "parse_session",
        "product_document",
        "report_definition",
        "report_batch",
        "report_batch_item",
        "report_field_definition",
        "report_field_definition_version",
        "report_field_value",
        "report_file_version",
        "report_run",
        "report_template",
        "report_template_version",
        "tenant",
        "tenant_membership",
    }
    assert set(inspector.get_table_names()) == expected_tables
    fund_nav_uniques = {item["name"] for item in inspector.get_unique_constraints("fund_nav")}
    assert "uq_fund_nav_tenant_product_code_nav_date" in fund_nav_uniques
    fund_nav_columns = {item["name"] for item in inspector.get_columns("fund_nav")}
    assert {
        "master_product_code",
        "asset_code",
        "registration_code",
        "paid_in_capital",
        "total_assets",
        "parent_product_code",
    }.issubset(fund_nav_columns)
    product_uniques = {item["name"] for item in inspector.get_unique_constraints("fund_product")}
    assert "uq_fund_product_tenant_product_code" in product_uniques
    product_columns = {item["name"] for item in inspector.get_columns("fund_product")}
    assert {"source_profile", "source_profile_meta", "manual_profile"}.issubset(product_columns)
    email_uniques = {item["name"] for item in inspector.get_unique_constraints("email_record")}
    assert "uq_email_record_scope_uidvalidity_uid" in email_uniques
    mailbox_columns = {item["name"] for item in inspector.get_columns("mailbox_account")}
    assert {
        "configuration_source",
        "last_connection_error",
        "last_sync_status",
        "last_sync_at",
    }.issubset(mailbox_columns)
    mailbox_indexes = {item["name"] for item in inspector.get_indexes("mailbox_account")}
    assert "uq_mailbox_account_one_default_per_tenant" in mailbox_indexes
    app_user_columns = {item["name"] for item in inspector.get_columns("app_user")}
    assert {"role", "token_version", "is_platform_admin"}.issubset(app_user_columns)
    for table_name in (
        "job_run",
        "email_record",
        "attachment_record",
        "exception_record",
        "filing_profile",
        "filing_field",
        "filing_file_version",
        "fund_nav",
        "fund_product",
        "product_document",
        "report_definition",
        "report_batch",
        "report_batch_item",
        "report_field_definition",
        "report_field_definition_version",
        "report_field_value",
        "report_file_version",
        "report_run",
        "report_template",
        "report_template_version",
        "audit_event",
    ):
        assert "tenant_id" in {item["name"] for item in inspector.get_columns(table_name)}

    # 模型与已执行迁移必须保持一致，否则 command.check 会抛出异常。
    command.check(alembic_config)
    command.downgrade(alembic_config, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]

    engine.dispose()
    get_settings.cache_clear()
