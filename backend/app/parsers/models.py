"""Excel 解析领域模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any


class WorkbookType(StrEnum):
    SINGLE_FUND_DAILY = "single_fund_daily"
    FUND_NAV_SUMMARY = "fund_nav_summary"
    ASSET_NAV_BROWSER = "asset_nav_browser"


class IssueSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class IssueCode(StrEnum):
    UNSUPPORTED_WORKBOOK_FORMAT = "unsupported_workbook_format"
    WORKBOOK_READ_ERROR = "workbook_read_error"
    EMPTY_WORKBOOK = "empty_workbook"
    HEADER_NOT_FOUND = "header_not_found"
    AMBIGUOUS_FORMAT = "ambiguous_format"
    MISSING_FIELD = "missing_field"
    MISSING_DATE = "missing_date"
    MISSING_PRODUCT_CODE = "missing_product_code"
    MISSING_PRODUCT_NAME = "missing_product_name"
    EMPTY_NAV = "empty_nav"
    INVALID_DATE = "invalid_date"
    INVALID_NUMBER = "invalid_number"
    DUPLICATE_ROW = "duplicate_row"
    MIXED_WORKBOOK_TYPES = "mixed_workbook_types"


@dataclass(frozen=True, slots=True)
class ParseIssue:
    code: IssueCode
    severity: IssueSeverity
    message: str
    source_file: str
    sheet_name: str | None = None
    row_number: int | None = None
    field_name: str | None = None
    raw_value: Any = None
    raw_data: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class StandardNavRecord:
    """三类来源统一后的基金净值记录。"""

    product_name: str | None
    product_code: str | None
    nav_date: date | None
    unit_nav: Decimal | None
    total_nav: Decimal | None
    asset_value: Decimal | None
    source_file: str
    source_sheet: str
    source_row: int
    source_type: WorkbookType
    create_time: datetime


@dataclass(frozen=True, slots=True)
class ParsedNavRow:
    record: StandardNavRecord
    issues: tuple[ParseIssue, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not any(issue.severity == IssueSeverity.ERROR for issue in self.issues)


@dataclass(frozen=True, slots=True)
class FieldColumn:
    column_index: int
    header_label: str
    matched_alias: str
    match_strength: int


@dataclass(frozen=True, slots=True)
class TableDetection:
    workbook_type: WorkbookType
    sheet_name: str
    header_start_row: int
    header_row_count: int
    field_columns: dict[str, FieldColumn]
    score: float
    confidence: float
    missing_fields: tuple[str, ...] = ()
    ambiguous_with: WorkbookType | None = None


@dataclass(slots=True)
class WorkbookParseResult:
    source_path: Path
    rows: list[ParsedNavRow] = field(default_factory=list)
    issues: list[ParseIssue] = field(default_factory=list)
    detections: list[TableDetection] = field(default_factory=list)

    @property
    def source_file(self) -> str:
        return self.source_path.name

    @property
    def detected_types(self) -> set[WorkbookType]:
        return {detection.workbook_type for detection in self.detections}

    @property
    def records(self) -> list[StandardNavRecord]:
        """仅返回没有 ERROR 的记录，供后续入库阶段使用。"""

        return [row.record for row in self.rows if row.is_valid]

    @property
    def invalid_rows(self) -> list[ParsedNavRow]:
        return [row for row in self.rows if not row.is_valid]

