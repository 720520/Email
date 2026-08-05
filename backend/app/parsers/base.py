"""三类净值表共享的行解析与标准化逻辑。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd

from app.core.config import ExcelSettings
from app.domain.fund_identity import fund_display_identity
from app.parsers.field_registry import FieldAliasRegistry
from app.parsers.models import (
    IssueCode,
    IssueSeverity,
    ParsedNavRow,
    ParseIssue,
    StandardNavRecord,
    TableDetection,
    WorkbookType,
)
from app.parsers.normalizers import (
    is_blank,
    normalize_identifier,
    normalize_text,
    parse_date,
    parse_decimal,
    parse_ratio,
    serialize_value,
)


class BaseTableParser:
    workbook_type: ClassVar[WorkbookType]

    def __init__(self, registry: FieldAliasRegistry, settings: ExcelSettings) -> None:
        self.registry = registry
        self.settings = settings

    def parse(
        self,
        frame: pd.DataFrame,
        detection: TableDetection,
        source_path: Path,
        *,
        create_time: datetime | None = None,
    ) -> list[ParsedNavRow]:
        if detection.workbook_type != self.workbook_type:
            raise ValueError("解析器类型与检测结果不一致")
        parsed_at = create_time or datetime.now(UTC)
        metadata = self._extract_metadata(frame, detection.header_start_row)
        supplemental = self._extract_supplemental_info(frame)
        data_start = detection.header_start_row + detection.header_row_count
        rows: list[ParsedNavRow] = []
        blank_streak = 0

        for row_index in range(data_start, len(frame.index)):
            raw_data = self._mapped_row(frame, row_index, detection)
            if all(is_blank(value) for value in raw_data.values()):
                blank_streak += 1
                if blank_streak >= self.settings.max_consecutive_blank_rows:
                    break
                continue
            blank_streak = 0
            if self._is_repeated_header(raw_data) or self._is_summary_row(raw_data):
                continue
            if self._is_supplemental_row(raw_data):
                continue
            # 托管附件常在净值数据后直接拼接合并单元格声明，没有足够空行可供终止。
            # 一旦命中可配置的声明标记，后续内容都属于页脚，不再生成伪异常记录。
            if self._is_terminal_footer(raw_data):
                break
            rows.append(
                self._parse_row(
                    raw_data,
                    metadata,
                    source_path=source_path,
                    sheet_name=detection.sheet_name,
                    row_number=row_index + 1,
                    create_time=parsed_at,
                    supplemental=supplemental,
                )
            )
        return rows

    def _parse_row(
        self,
        raw_data: dict[str, Any],
        metadata: dict[str, Any],
        *,
        source_path: Path,
        sheet_name: str,
        row_number: int,
        create_time: datetime,
        supplemental: dict[str, str],
    ) -> ParsedNavRow:
        serialized_row = {key: serialize_value(value) for key, value in raw_data.items()}
        issues: list[ParseIssue] = []
        explicit_code = self._prefer_value(
            raw_data.get("product_code"), metadata.get("product_code")
        )
        asset_code = normalize_identifier(
            self._prefer_value(raw_data.get("asset_code"), metadata.get("asset_code"))
        )
        registration_code = normalize_identifier(
            self._prefer_value(
                raw_data.get("registration_code"), metadata.get("registration_code")
            )
        )
        product_code = normalize_identifier(
            self._prefer_value(explicit_code, asset_code or registration_code)
        )
        product_name = normalize_text(
            self._prefer_value(raw_data.get("product_name"), metadata.get("product_name"))
        )
        date_value = self._prefer_value(raw_data.get("nav_date"), metadata.get("nav_date"))
        nav_date = self._convert_date(
            date_value,
            issues,
            source_path,
            sheet_name,
            row_number,
            serialized_row,
        )
        unit_nav = self._convert_number(
            "unit_nav",
            raw_data.get("unit_nav"),
            issues,
            source_path,
            sheet_name,
            row_number,
            serialized_row,
        )
        total_nav = self._convert_number(
            "total_nav",
            raw_data.get("total_nav"),
            issues,
            source_path,
            sheet_name,
            row_number,
            serialized_row,
        )
        asset_value = self._convert_number(
            "asset_value",
            raw_data.get("asset_value"),
            issues,
            source_path,
            sheet_name,
            row_number,
            serialized_row,
        )
        optional_numbers = {
            field_name: self._convert_number(
                field_name,
                raw_data.get(field_name),
                issues,
                source_path,
                sheet_name,
                row_number,
                serialized_row,
                severity=IssueSeverity.WARNING,
            )
            for field_name in (
                "asset_share",
                "paid_in_capital",
                "holding_shares",
                "reference_market_value",
                "total_assets",
                "parent_unit_nav",
                "parent_total_nav",
                "parent_asset_value",
                "parent_paid_in_capital",
            )
        }
        total_assets_nav_ratio = self._convert_ratio(
            raw_data.get("total_assets_nav_ratio"),
            issues,
            source_path,
            sheet_name,
            row_number,
            serialized_row,
        )

        if product_code is None:
            issues.append(
                self._issue(
                    IssueCode.MISSING_PRODUCT_CODE,
                    "产品代码缺失",
                    source_path,
                    sheet_name,
                    row_number,
                    "product_code",
                    raw_data.get("product_code"),
                    serialized_row,
                )
            )
        if product_name is None:
            issues.append(
                self._issue(
                    IssueCode.MISSING_PRODUCT_NAME,
                    "产品名称缺失",
                    source_path,
                    sheet_name,
                    row_number,
                    "product_name",
                    raw_data.get("product_name"),
                    serialized_row,
                )
            )
        if nav_date is None and not any(issue.code == IssueCode.INVALID_DATE for issue in issues):
            issues.append(
                self._issue(
                    IssueCode.MISSING_DATE,
                    "净值日期缺失",
                    source_path,
                    sheet_name,
                    row_number,
                    "nav_date",
                    date_value,
                    serialized_row,
                )
            )
        if unit_nav is None and not any(
            issue.code == IssueCode.INVALID_NUMBER and issue.field_name == "unit_nav"
            for issue in issues
        ):
            issues.append(
                self._issue(
                    IssueCode.EMPTY_NAV,
                    "单位净值为空",
                    source_path,
                    sheet_name,
                    row_number,
                    "unit_nav",
                    raw_data.get("unit_nav"),
                    serialized_row,
                )
            )

        record = StandardNavRecord(
            product_name=product_name,
            product_code=product_code,
            nav_date=nav_date,
            unit_nav=unit_nav,
            total_nav=total_nav,
            asset_value=asset_value,
            source_file=source_path.name,
            source_sheet=sheet_name,
            source_row=row_number,
            source_type=self.workbook_type,
            create_time=create_time,
            asset_code=asset_code,
            registration_code=registration_code,
            share_class=(
                fund_display_identity(product_name, product_code).share_class
                if product_name and product_code
                else None
            ),
            asset_share=optional_numbers["asset_share"],
            paid_in_capital=optional_numbers["paid_in_capital"],
            holding_shares=optional_numbers["holding_shares"],
            reference_market_value=optional_numbers["reference_market_value"],
            total_assets=optional_numbers["total_assets"],
            total_assets_nav_ratio=total_assets_nav_ratio,
            investor_name=normalize_text(raw_data.get("investor_name")),
            investor_account=normalize_identifier(raw_data.get("investor_account")),
            parent_unit_nav=optional_numbers["parent_unit_nav"],
            parent_total_nav=optional_numbers["parent_total_nav"],
            parent_asset_value=optional_numbers["parent_asset_value"],
            parent_product_code=normalize_identifier(raw_data.get("parent_product_code")),
            parent_product_name=normalize_text(raw_data.get("parent_product_name")),
            notes=normalize_text(raw_data.get("notes")),
            parent_paid_in_capital=optional_numbers["parent_paid_in_capital"],
            investment_manager_info=supplemental.get("investment_manager_info"),
            investment_strategy_info=supplemental.get("investment_strategy_info"),
        )
        return ParsedNavRow(record=record, issues=tuple(issues))

    def _extract_metadata(
        self,
        frame: pd.DataFrame,
        header_start_row: int,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        allowed_fields = {
            "product_code",
            "asset_code",
            "registration_code",
            "product_name",
            "nav_date",
        }
        column_limit = min(len(frame.columns), self.settings.max_columns)
        for row_index in range(header_start_row):
            for column_index in range(column_limit):
                value = frame.iat[row_index, column_index]
                if is_blank(value):
                    continue
                text = normalize_text(value) or ""
                inline_label, inline_value = self._split_label_value(text)
                field_name = self.registry.match_exact(inline_label)
                if field_name not in allowed_fields or field_name in metadata:
                    continue
                candidate_value: Any = inline_value
                if is_blank(candidate_value) and column_index + 1 < column_limit:
                    candidate_value = frame.iat[row_index, column_index + 1]
                if not is_blank(candidate_value):
                    metadata[field_name] = candidate_value
        return metadata

    def _extract_supplemental_info(self, frame: pd.DataFrame) -> dict[str, str]:
        """提取中信说明区；其他托管缺失时返回空，不影响净值解析。"""

        markers = {
            "投资经理信息": "investment_manager_info",
            "投资策略信息": "investment_strategy_info",
        }
        result: dict[str, str] = {}
        column_limit = min(len(frame.columns), self.settings.max_columns)
        for row_index in range(len(frame.index)):
            for column_index in range(column_limit):
                text = normalize_text(frame.iat[row_index, column_index])
                if text is None:
                    continue
                for marker, field_name in markers.items():
                    if not text.startswith(marker):
                        continue
                    _, _, content = text.partition("：")
                    if not content:
                        _, _, content = text.partition(":")
                    cleaned = content.strip()[:20_000]
                    if cleaned:
                        result[field_name] = cleaned
        return result

    @staticmethod
    def _split_label_value(text: str) -> tuple[str, str | None]:
        for separator in ("：", ":"):
            if separator in text:
                label, value = text.split(separator, 1)
                return label, value
        return text, None

    @staticmethod
    def _mapped_row(
        frame: pd.DataFrame,
        row_index: int,
        detection: TableDetection,
    ) -> dict[str, Any]:
        return {
            field_name: frame.iat[row_index, field_column.column_index]
            for field_name, field_column in detection.field_columns.items()
        }

    def _is_repeated_header(self, raw_data: dict[str, Any]) -> bool:
        matches = sum(
            self.registry.match_exact(value) == field_name
            for field_name, value in raw_data.items()
            if not is_blank(value)
        )
        return matches >= min(2, len(raw_data))

    @staticmethod
    def _is_supplemental_row(raw_data: dict[str, Any]) -> bool:
        return any(
            (text := normalize_text(value)) is not None
            and text.startswith(("投资经理信息", "投资策略信息"))
            for value in raw_data.values()
        )

    @staticmethod
    def _is_summary_row(raw_data: dict[str, Any]) -> bool:
        """跳过合计、制表人等非基金数据行，但允许后续继续出现数据。"""

        name = normalize_text(raw_data.get("product_name"))
        code = normalize_text(raw_data.get("product_code"))
        return code is None and name in {"合计", "总计", "说明", "备注", "制表人", "复核人"}

    def _is_terminal_footer(self, raw_data: dict[str, Any]) -> bool:
        """识别托管机构附在数据区末尾的声明、风险提示和保密条款。"""

        markers = {
            normalized.casefold()
            for marker in self.settings.footer_markers
            if (normalized := normalize_text(marker)) is not None
        }
        if not markers:
            return False

        for value in raw_data.values():
            text = normalize_text(value)
            if text is None:
                continue
            candidate = text.casefold()
            for marker in markers:
                if candidate == marker:
                    return True
                if candidate.startswith(marker) and len(candidate) > len(marker):
                    boundary = candidate[len(marker)]
                    if boundary in {":", "：", " ", "\t", "\r", "\n"}:
                        return True
        return False

    @staticmethod
    def _prefer_value(primary: Any, fallback: Any) -> Any:
        return fallback if is_blank(primary) else primary

    def _convert_date(
        self,
        value: Any,
        issues: list[ParseIssue],
        source_path: Path,
        sheet_name: str,
        row_number: int,
        raw_data: dict[str, Any],
    ):
        try:
            return parse_date(value)
        except ValueError as exc:
            issues.append(
                self._issue(
                    IssueCode.INVALID_DATE,
                    str(exc),
                    source_path,
                    sheet_name,
                    row_number,
                    "nav_date",
                    value,
                    raw_data,
                )
            )
            return None

    def _convert_number(
        self,
        field_name: str,
        value: Any,
        issues: list[ParseIssue],
        source_path: Path,
        sheet_name: str,
        row_number: int,
        raw_data: dict[str, Any],
        *,
        severity: IssueSeverity = IssueSeverity.ERROR,
    ):
        try:
            return parse_decimal(value)
        except ValueError as exc:
            issues.append(
                self._issue(
                    IssueCode.INVALID_NUMBER,
                    str(exc),
                    source_path,
                    sheet_name,
                    row_number,
                    field_name,
                    value,
                    raw_data,
                    severity=severity,
                )
            )
            return None

    def _convert_ratio(
        self,
        value: Any,
        issues: list[ParseIssue],
        source_path: Path,
        sheet_name: str,
        row_number: int,
        raw_data: dict[str, Any],
    ):
        try:
            return parse_ratio(value)
        except ValueError as exc:
            issues.append(
                self._issue(
                    IssueCode.INVALID_NUMBER,
                    str(exc),
                    source_path,
                    sheet_name,
                    row_number,
                    "total_assets_nav_ratio",
                    value,
                    raw_data,
                    severity=IssueSeverity.WARNING,
                )
            )
            return None

    @staticmethod
    def _issue(
        code: IssueCode,
        message: str,
        source_path: Path,
        sheet_name: str,
        row_number: int,
        field_name: str,
        raw_value: Any,
        raw_data: dict[str, Any],
        *,
        severity: IssueSeverity = IssueSeverity.ERROR,
    ) -> ParseIssue:
        return ParseIssue(
            code=code,
            severity=severity,
            message=message,
            source_file=source_path.name,
            sheet_name=sheet_name,
            row_number=row_number,
            field_name=field_name,
            raw_value=serialize_value(raw_value),
            raw_data=raw_data,
        )
