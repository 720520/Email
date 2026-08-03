from datetime import date
from decimal import Decimal

import pytest

from app.parsers.normalizers import (
    normalize_identifier,
    parse_date,
    parse_decimal,
)


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("20260724", date(2026, 7, 24)),
        ("2026年7月24日", date(2026, 7, 24)),
        ("2026/7/24 00:00:00", date(2026, 7, 24)),
        (46227, date(2026, 7, 24)),
    ],
)
def test_parse_multiple_date_formats(raw_value, expected) -> None:
    assert parse_date(raw_value) == expected


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("1,234,567.8900元", Decimal("1234567.8900")),
        ("（1,000.25）", Decimal("-1000.25")),
        (1.23456789, Decimal("1.23456789")),
        ("--", None),
    ],
)
def test_parse_financial_numbers_without_float_rounding(raw_value, expected) -> None:
    assert parse_decimal(raw_value) == expected


def test_reject_formula_and_percentage_values() -> None:
    with pytest.raises(ValueError, match="不执行 Excel 公式"):
        parse_decimal("=A1/B1")
    with pytest.raises(ValueError, match="不能使用百分比"):
        parse_decimal("1.5%")


def test_normalize_numeric_product_code() -> None:
    assert normalize_identifier(600001.0) == "600001"


def test_empty_and_whitespace_strings_are_blank() -> None:
    assert parse_decimal("") is None
    assert parse_date("   ") is None
