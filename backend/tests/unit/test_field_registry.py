from pathlib import Path

import yaml

from app.parsers.field_registry import FieldAliasRegistry

ALIAS_FILE = Path(__file__).resolve().parents[3] / "config/excel_fields.yaml"


def test_operator_can_add_custodian_alias_without_code_change(tmp_path: Path) -> None:
    content = yaml.safe_load(ALIAS_FILE.read_text(encoding="utf-8"))
    content["fields"]["product_code"]["aliases"].append("托管产品识别码")
    custom_file = tmp_path / "custom-fields.yaml"
    custom_file.write_text(yaml.safe_dump(content, allow_unicode=True), encoding="utf-8")

    registry = FieldAliasRegistry.from_yaml(custom_file)
    match = registry.match(["托管产品识别码"])

    assert match is not None
    assert match.field_name == "product_code"

