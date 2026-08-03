"""Excel 智能识别与标准化统一入口。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Settings, get_settings
from app.parsers.asset_browser import AssetNavBrowserParser
from app.parsers.detector import TableDetector
from app.parsers.field_registry import FieldAliasRegistry
from app.parsers.fund_summary import FundNavSummaryParser
from app.parsers.models import (
    IssueCode,
    IssueSeverity,
    ParsedNavRow,
    ParseIssue,
    WorkbookParseResult,
    WorkbookType,
)
from app.parsers.single_fund import SingleFundDailyParser
from app.parsers.workbook_reader import (
    UnsupportedWorkbookFormatError,
    WorkbookReader,
    WorkbookReadError,
)

logger = logging.getLogger(__name__)


class ExcelParserService:
    """遍历全部工作表，拒绝歧义格式，并汇总有效记录和行级异常。"""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        reader: WorkbookReader | None = None,
        registry: FieldAliasRegistry | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.reader = reader or WorkbookReader()
        self.registry = registry or FieldAliasRegistry.from_yaml(
            self.settings.excel_field_alias_file
        )
        self.detector = TableDetector(self.registry, self.settings.excel)
        self.parsers = {
            WorkbookType.SINGLE_FUND_DAILY: SingleFundDailyParser(
                self.registry, self.settings.excel
            ),
            WorkbookType.FUND_NAV_SUMMARY: FundNavSummaryParser(
                self.registry, self.settings.excel
            ),
            WorkbookType.ASSET_NAV_BROWSER: AssetNavBrowserParser(
                self.registry, self.settings.excel
            ),
        }

    def parse_file(self, source_path: str | Path) -> WorkbookParseResult:
        path = Path(source_path).resolve()
        result = WorkbookParseResult(source_path=path)
        try:
            sheets = self.reader.read(path)
        except UnsupportedWorkbookFormatError as exc:
            result.issues.append(
                self._file_issue(result, IssueCode.UNSUPPORTED_WORKBOOK_FORMAT, str(exc))
            )
            return result
        except WorkbookReadError as exc:
            result.issues.append(self._file_issue(result, IssueCode.WORKBOOK_READ_ERROR, str(exc)))
            return result

        if not sheets:
            result.issues.append(
                self._file_issue(result, IssueCode.EMPTY_WORKBOOK, "工作簿不包含工作表")
            )
            return result

        parsed_types: set[WorkbookType] = set()
        recognized_sheet_count = 0
        parsed_at = datetime.now(UTC)
        for sheet_name, frame in sheets.items():
            detection = self.detector.detect(sheet_name, frame)
            if detection is None:
                continue
            recognized_sheet_count += 1
            result.detections.append(detection)
            if detection.ambiguous_with is not None:
                result.issues.append(
                    ParseIssue(
                        code=IssueCode.AMBIGUOUS_FORMAT,
                        severity=IssueSeverity.ERROR,
                        message=(
                            f"工作表格式同时匹配 {detection.workbook_type.value} 和 "
                            f"{detection.ambiguous_with.value}，已停止猜测"
                        ),
                        source_file=result.source_file,
                        sheet_name=sheet_name,
                        row_number=detection.header_start_row + 1,
                    )
                )
                continue
            if detection.missing_fields:
                result.issues.append(
                    ParseIssue(
                        code=IssueCode.MISSING_FIELD,
                        severity=IssueSeverity.ERROR,
                        message=f"缺少必需字段: {', '.join(detection.missing_fields)}",
                        source_file=result.source_file,
                        sheet_name=sheet_name,
                        row_number=detection.header_start_row + 1,
                        raw_data={"missing_fields": list(detection.missing_fields)},
                    )
                )
                continue

            parser = self.parsers[detection.workbook_type]
            parsed_rows = parser.parse(
                frame,
                detection,
                path,
                create_time=parsed_at,
            )
            result.rows.extend(parsed_rows)
            for parsed_row in parsed_rows:
                result.issues.extend(parsed_row.issues)
            parsed_types.add(detection.workbook_type)

        if recognized_sheet_count == 0:
            result.issues.append(
                self._file_issue(
                    result,
                    IssueCode.HEADER_NOT_FOUND,
                    "未在任何工作表前部找到可识别的基金净值表头",
                )
            )
        elif not result.rows and not result.issues:
            result.issues.append(
                self._file_issue(result, IssueCode.EMPTY_WORKBOOK, "已识别表头但没有数据行")
            )

        if len(parsed_types) > 1:
            result.issues.append(
                ParseIssue(
                    code=IssueCode.MIXED_WORKBOOK_TYPES,
                    severity=IssueSeverity.WARNING,
                    message="同一工作簿包含多种净值表类型，已按工作表分别解析",
                    source_file=result.source_file,
                    raw_data={"types": sorted(item.value for item in parsed_types)},
                )
            )
        self._mark_duplicates(result)
        logger.info(
            "Excel 解析完成",
            extra={
                "source_file": result.source_file,
                "sheet_count": len(sheets),
                "record_count": len(result.records),
                "issue_count": len(result.issues),
            },
        )
        return result

    @staticmethod
    def _file_issue(
        result: WorkbookParseResult,
        code: IssueCode,
        message: str,
    ) -> ParseIssue:
        return ParseIssue(
            code=code,
            severity=IssueSeverity.ERROR,
            message=message,
            source_file=result.source_file,
        )

    @staticmethod
    def _mark_duplicates(result: WorkbookParseResult) -> None:
        seen: dict[tuple[str, object], tuple[str, int]] = {}
        for row_index, parsed_row in enumerate(result.rows):
            record = parsed_row.record
            if record.product_code is None or record.nav_date is None:
                continue
            key = (record.product_code.casefold(), record.nav_date)
            first_occurrence = seen.get(key)
            if first_occurrence is None:
                seen[key] = (record.source_sheet, record.source_row)
                continue
            first_sheet, first_row = first_occurrence
            issue = ParseIssue(
                code=IssueCode.DUPLICATE_ROW,
                severity=IssueSeverity.ERROR,
                message=f"产品代码和日期重复，首次出现于 {first_sheet} 第 {first_row} 行",
                source_file=result.source_file,
                sheet_name=record.source_sheet,
                row_number=record.source_row,
                field_name="product_code+nav_date",
                raw_data={
                    "product_code": record.product_code,
                    "nav_date": record.nav_date.isoformat(),
                },
            )
            result.rows[row_index] = ParsedNavRow(
                record=record,
                issues=(*parsed_row.issues, issue),
            )
            result.issues.append(issue)
