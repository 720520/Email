from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml
from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command


def test_legacy_filing_data_is_split_without_changing_file_identity(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = f"sqlite:///{(tmp_path / 'stage2.db').as_posix()}"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump({"database": {"url": database_url}}), encoding="utf-8")
    monkeypatch.setenv("FUND_NAV_CONFIG_FILE", str(config_path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    alembic_config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(alembic_config, "20260827_0017")
    now = datetime(2026, 8, 27, 8, tzinfo=UTC).replace(tzinfo=None)
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE tenant SET name = '合成迁移租户', update_time = :now WHERE id = 1"),
            {"now": now},
        )
        connection.execute(
            text(
                "INSERT INTO filing_profile "
                "(id, tenant_id, field_values, document_notes, create_time, update_time) "
                "VALUES (1, 1, :values, '{}', :now, :now)"
            ),
            {"values": '{"company_name":"合成迁移管理人"}', "now": now},
        )
        connection.execute(
            text(
                "INSERT INTO filing_field "
                "(id, tenant_id, field_key, label, category, field_type, sensitive, multiline, "
                "source_forms, sort_order, is_active, create_time, update_time) VALUES "
                "(1, 1, 'company_name', '管理人全称', '公司信息', 'text', "
                "0, 0, '[]', 10, 1, :now, :now),"
                "(2, 1, 'business_license_file', '营业执照', '公司证照', 'file', "
                "0, 0, '[]', 20, 1, :now, :now),"
                "(3, 1, 'fund_contract_file', '基金合同', '产品材料', 'file', "
                "0, 0, '[]', 30, 1, :now, :now)"
            ),
            {"now": now},
        )
        connection.execute(
            text(
                "INSERT INTO filing_file_version "
                "(id, tenant_id, field_id, version, original_name, stored_path, content_hash, "
                "file_size, content_type, create_time) VALUES "
                "(11, 1, 2, 1, 'synthetic-license.pdf', 'legacy/license.pdf', "
                ":company_hash, 12, 'application/pdf', :now),"
                "(12, 1, 3, 1, 'synthetic-contract.pdf', 'legacy/contract.pdf', "
                ":product_hash, 13, 'application/pdf', :now)"
            ),
            {"company_hash": "a" * 64, "product_hash": "b" * 64, "now": now},
        )
        connection.execute(
            text(
                "INSERT INTO fund_product "
                "(id, tenant_id, product_code, product_name, investment_manager_manual, "
                "investment_strategy_manual, source_profile, source_profile_meta, manual_profile, "
                "create_time, update_time) VALUES "
                "(21, 1, 'SYNTH-P001', '合成迁移产品', 0, 0, '{}', '{}', '{}', :now, :now)"
            ),
            {"now": now},
        )

    command.upgrade(alembic_config, "head")
    with engine.connect() as connection:
        entities = (
            connection.execute(text("SELECT id, entity_type, display_name FROM entity ORDER BY id"))
            .mappings()
            .all()
        )
        fact = (
            connection.execute(text("SELECT value_json, source_type FROM field_value"))
            .mappings()
            .one()
        )
        documents = (
            connection.execute(
                text(
                    "SELECT id, legacy_filing_file_version_id, content_hash, storage_path, "
                    "version, entity_id "
                    "FROM source_document ORDER BY legacy_filing_file_version_id"
                )
            )
            .mappings()
            .all()
        )
        attribution = (
            connection.execute(
                text(
                    "SELECT document_id, status, product_entity_id "
                    "FROM product_material_attribution"
                )
            )
            .mappings()
            .one()
        )
        product_entity_id = connection.scalar(
            text("SELECT entity_id FROM fund_product WHERE id = 21")
        )
        relation_count = connection.scalar(
            text(
                "SELECT COUNT(*) FROM document_relation "
                "WHERE relation_type = 'legacy_company_material'"
            )
        )

    assert {item["entity_type"] for item in entities} == {"organization", "product"}
    assert json.loads(fact["value_json"]) == "合成迁移管理人"
    assert fact["source_type"] == "legacy_migration"
    assert [item["legacy_filing_file_version_id"] for item in documents] == [11, 12]
    assert [item["content_hash"] for item in documents] == ["a" * 64, "b" * 64]
    assert [item["storage_path"] for item in documents] == [
        "legacy/license.pdf",
        "legacy/contract.pdf",
    ]
    assert attribution["document_id"] == documents[1]["id"]
    assert attribution["status"] == "pending"
    assert attribution["product_entity_id"] is None
    assert product_entity_id is not None
    assert relation_count == 1

    engine.dispose()
    get_settings.cache_clear()
