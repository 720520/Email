"""可配置字段别名和表格类型规则。"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.parsers.models import WorkbookType


@dataclass(frozen=True, slots=True)
class HeaderMatch:
    field_name: str
    matched_alias: str
    strength: int


@dataclass(frozen=True, slots=True)
class WorkbookTypeRule:
    workbook_type: WorkbookType
    required_fields: frozenset[str]
    required_any: tuple[frozenset[str], ...]
    optional_fields: frozenset[str]
    signature_aliases: frozenset[str]


class FieldAliasRegistry:
    """从 YAML 加载托管字段别名，允许运营人员低风险扩展格式。"""

    def __init__(
        self,
        aliases: dict[str, frozenset[str]],
        type_rules: dict[WorkbookType, WorkbookTypeRule],
    ) -> None:
        self.aliases = aliases
        self.type_rules = type_rules
        self._alias_to_field: dict[str, str] = {}
        for field_name, field_aliases in aliases.items():
            for alias in field_aliases:
                existing = self._alias_to_field.get(alias)
                if existing is not None and existing != field_name:
                    raise ValueError(f"字段别名冲突: {alias} 同时属于 {existing} 和 {field_name}")
                self._alias_to_field[alias] = field_name

    @classmethod
    def from_yaml(cls, path: Path) -> FieldAliasRegistry:
        if not path.exists():
            raise FileNotFoundError(f"Excel 字段词典不存在: {path}")
        content = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(content, dict):
            raise ValueError("Excel 字段词典顶层必须为映射")

        raw_fields = content.get("fields")
        raw_types = content.get("types")
        if not isinstance(raw_fields, dict) or not isinstance(raw_types, dict):
            raise ValueError("Excel 字段词典必须包含 fields 和 types")

        aliases: dict[str, frozenset[str]] = {}
        for field_name, definition in raw_fields.items():
            if not isinstance(definition, dict) or not isinstance(definition.get("aliases"), list):
                raise ValueError(f"字段 {field_name} 缺少 aliases 列表")
            normalized_aliases = {
                normalize_header(alias)
                for alias in definition["aliases"]
                if normalize_header(alias)
            }
            if not normalized_aliases:
                raise ValueError(f"字段 {field_name} 没有有效别名")
            aliases[str(field_name)] = frozenset(normalized_aliases)

        type_rules: dict[WorkbookType, WorkbookTypeRule] = {}
        for type_name, definition in raw_types.items():
            if not isinstance(definition, dict):
                raise ValueError(f"类型 {type_name} 配置无效")
            workbook_type = WorkbookType(type_name)
            required = cls._field_set(definition, "required_fields")
            required_any = cls._required_any(definition)
            optional = cls._field_set(definition, "optional_fields")
            grouped_fields = set().union(*required_any) if required_any else set()
            unknown_fields = (required | optional | grouped_fields) - aliases.keys()
            if unknown_fields:
                raise ValueError(f"类型 {type_name} 引用了未知字段: {sorted(unknown_fields)}")
            signatures = frozenset(
                normalize_header(alias)
                for alias in definition.get("signature_aliases", [])
                if normalize_header(alias)
            )
            type_rules[workbook_type] = WorkbookTypeRule(
                workbook_type=workbook_type,
                required_fields=frozenset(required),
                required_any=required_any,
                optional_fields=frozenset(optional),
                signature_aliases=signatures,
            )
        return cls(aliases, type_rules)

    @staticmethod
    def _field_set(definition: dict[str, Any], key: str) -> set[str]:
        value = definition.get(key, [])
        if not isinstance(value, list):
            raise ValueError(f"{key} 必须为列表")
        return {str(item) for item in value}

    @staticmethod
    def _required_any(definition: dict[str, Any]) -> tuple[frozenset[str], ...]:
        """读取“每组至少命中一个字段”，用于兼容产品/资产/备案代码差异。"""

        value = definition.get("required_any", [])
        if not isinstance(value, list):
            raise ValueError("required_any 必须为列表")
        groups: list[frozenset[str]] = []
        for group in value:
            if not isinstance(group, list) or not group:
                raise ValueError("required_any 的每一项必须是非空字段列表")
            groups.append(frozenset(str(item) for item in group))
        return tuple(groups)

    def match(self, variants: list[str]) -> HeaderMatch | None:
        best: HeaderMatch | None = None
        for raw_variant in variants:
            variant = normalize_header(raw_variant)
            if not variant:
                continue
            exact_field = self._alias_to_field.get(variant)
            if exact_field is not None:
                candidate = HeaderMatch(exact_field, variant, 100 + len(variant))
                if best is None or candidate.strength > best.strength:
                    best = candidate
                continue

            for alias, field_name in self._alias_to_field.items():
                length_delta = len(variant) - len(alias)
                if len(alias) >= 4 and 0 <= length_delta <= 12 and variant.endswith(alias):
                    candidate = HeaderMatch(field_name, alias, 60 + len(alias))
                    if best is None or candidate.strength > best.strength:
                        best = candidate
        return best

    def match_exact(self, value: Any) -> str | None:
        return self._alias_to_field.get(normalize_header(value))


def normalize_header(value: Any) -> str:
    """统一全半角、空白、换行、标点和常见金额单位。"""

    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).casefold().strip()
    normalized = "".join(character for character in text if character.isalnum())
    for suffix in ("人民币元", "人民币", "元"):
        if normalized.endswith(suffix) and len(normalized) > len(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized
