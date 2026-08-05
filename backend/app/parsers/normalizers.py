"""Excel 单元格值标准化。"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from numbers import Integral, Real
from typing import Any

import pandas as pd

_BLANK_MARKERS = {"", "-", "--", "/", "n/a", "na", "none", "null", "无", "不适用"}
_EXCEL_EPOCH = datetime(1899, 12, 30)


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        normalized = normalize_text(value)
        return normalized is None or normalized.casefold() in _BLANK_MARKERS
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def normalize_text(value: Any) -> str | None:
    if is_null_like(value):
        return None
    text = unicodedata.normalize("NFKC", str(value)).replace("\u00a0", " ")
    normalized = " ".join(text.split()).strip()
    return normalized or None


def normalize_identifier(value: Any) -> str | None:
    if is_blank(value):
        return None
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, Integral):
        return str(int(value))
    if isinstance(value, Real) and math.isfinite(float(value)):
        numeric = float(value)
        if numeric.is_integer():
            return str(int(numeric))
    text = normalize_text(value)
    if text and re.fullmatch(r"\d+\.0+", text):
        return text.split(".", 1)[0]
    return text


def parse_date(value: Any) -> date | None:
    if is_blank(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, bool):
        raise ValueError("布尔值不是有效日期")
    if isinstance(value, Real):
        numeric_value = float(value)
        if 20_000 <= numeric_value <= 80_000:
            return (_EXCEL_EPOCH + timedelta(days=numeric_value)).date()
        raise ValueError(f"无效 Excel 日期序号: {value}")

    text = normalize_text(value)
    if text is None:
        return None
    if re.fullmatch(r"\d{8}(?:\.0+)?", text):
        return datetime.strptime(text[:8], "%Y%m%d").date()
    if re.fullmatch(r"\d{5}(?:\.\d+)?", text):
        return parse_date(float(text))

    match = re.match(
        r"^(?P<year>\d{4})\s*[-/.年]\s*(?P<month>\d{1,2})\s*[-/.月]\s*"
        r"(?P<day>\d{1,2})(?:日)?(?:\s+.*)?$",
        text,
    )
    if match:
        return date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
    raise ValueError(f"无法识别日期: {text}")


def parse_decimal(value: Any) -> Decimal | None:
    if is_blank(value):
        return None
    if isinstance(value, bool):
        raise ValueError("布尔值不是有效数值")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, Real):
        if not math.isfinite(float(value)):
            raise ValueError("数值不是有限数")
        result = Decimal(str(value))
    else:
        text = normalize_text(value)
        if text is None:
            return None
        if text.startswith("="):
            raise ValueError("不执行 Excel 公式，请提供已计算的数值")
        if text.endswith("%"):
            raise ValueError("净值和资产值不能使用百分比")
        negative = text.startswith("(") and text.endswith(")")
        if negative:
            text = text[1:-1]
        cleaned = (
            text.replace(",", "")
            .replace("，", "")
            .replace("￥", "")
            .replace("¥", "")
            .replace("$", "")
            .replace(" ", "")
        )
        if cleaned.endswith("元"):
            cleaned = cleaned[:-1]
        try:
            result = Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError(f"无法识别数值: {text}") from exc
        if negative:
            result = -result

    if not result.is_finite():
        raise ValueError("数值不是有限数")
    return result


def parse_ratio(value: Any) -> Decimal | None:
    """把百分比文本转换为比例值，例如 100.10% -> 1.001。"""

    if is_blank(value):
        return None
    if isinstance(value, str):
        text = normalize_text(value)
        if text and text.endswith("%"):
            numeric = parse_decimal(text[:-1])
            return None if numeric is None else numeric / Decimal("100")
    return parse_decimal(value)


def serialize_value(value: Any, *, max_length: int = 500) -> Any:
    """转换成后续可写入 JSON 异常记录的安全值。"""

    if is_blank(value):
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        return float(value)
    item_method = getattr(value, "item", None)
    if callable(item_method):
        return serialize_value(item_method(), max_length=max_length)
    text = normalize_text(value) or ""
    return text[:max_length]


def is_null_like(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return False
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
