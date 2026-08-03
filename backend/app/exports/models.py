"""Excel 导出使用的稳定数据结构。"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class DailyNavExportRow:
    nav_date: date
    product_code: str
    product_name: str
    unit_nav: Decimal | None
    total_nav: Decimal | None
    asset_value: Decimal | None
    source_file: str


@dataclass(frozen=True, slots=True)
class ExceptionExportRow:
    occurred_date: date
    category: str
    severity: str
    product_code: str | None
    product_name: str | None
    source: str
    sheet_name: str | None
    row_number: int | None
    field_name: str | None
    raw_value: str | None
    message: str
    status: str
