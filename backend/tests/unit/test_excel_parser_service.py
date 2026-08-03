from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.config import Settings
from app.parsers.models import IssueCode, WorkbookType
from app.parsers.service import ExcelParserService

ALIAS_FILE = Path(__file__).resolve().parents[3] / "config/excel_fields.yaml"


class FakeWorkbookReader:
    def __init__(self, sheets: dict[str, pd.DataFrame]) -> None:
        self.sheets = sheets

    def read(self, path: Path) -> dict[str, pd.DataFrame]:
        del path
        return self.sheets


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database={"url": f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}"},
        logging={"directory": str(tmp_path / "logs")},
        storage={"data_directory": str(tmp_path / "data")},
        excel={"field_alias_file": str(ALIAS_FILE)},
    )


def test_parse_single_fund_uses_metadata_date_and_decimal(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        [
            ["日期", "2026-07-24", None, None],
            ["资产代码", "资产名称", "资产份额净值(元)", "资产份额累计净值(元)"],
            ["SAWK26", "吉余测试基金", "1.02560000", "1.12340000"],
        ]
    )
    service = ExcelParserService(
        _settings(tmp_path),
        reader=FakeWorkbookReader({"净值": frame}),
    )

    result = service.parse_file(tmp_path / "托管附件.xls")

    assert result.detected_types == {WorkbookType.SINGLE_FUND_DAILY}
    assert len(result.records) == 1
    record = result.records[0]
    assert record.product_code == "SAWK26"
    assert record.nav_date.isoformat() == "2026-07-24"
    assert str(record.unit_nav) == "1.02560000"
    assert not result.issues


def test_parse_summary_marks_invalid_numbers_missing_nav_and_duplicates(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        [
            ["产品代码", "产品名称", "估值基准日", "单位净值", "累计净值", "资产净值"],
            ["F001", "吉余一号", "20260724", "1.10000000", "1.20", "10,000,000.00"],
            ["F001", "吉余一号", "20260724", "1.10000000", "1.20", "10,000,000.00"],
            ["F002", "吉余二号", "日期错误", "--", "abc", "20,000,000"],
        ]
    )
    service = ExcelParserService(
        _settings(tmp_path),
        reader=FakeWorkbookReader({"汇总": frame}),
    )

    result = service.parse_file(tmp_path / "随意文件名.xlsx")

    assert len(result.rows) == 3
    assert len(result.records) == 1
    codes = {issue.code for issue in result.issues}
    assert IssueCode.DUPLICATE_ROW in codes
    assert IssueCode.INVALID_DATE in codes
    assert IssueCode.EMPTY_NAV in codes
    assert IssueCode.INVALID_NUMBER in codes


def test_parse_multiple_sheets_and_warn_about_mixed_types(tmp_path: Path) -> None:
    summary = pd.DataFrame(
        [
            ["产品代码", "产品名称", "估值基准日", "单位净值"],
            ["F001", "吉余一号", "2026-07-24", 1.1],
        ]
    )
    browser = pd.DataFrame(
        [
            ["产品名称", "产品代码", "日期", "资产净值", "资产份额", "单位净值"],
            ["吉余二号", "F002", "2026-07-24", 20_000_000, 10_000_000, 2],
        ]
    )
    service = ExcelParserService(
        _settings(tmp_path),
        reader=FakeWorkbookReader({"汇总": summary, "浏览": browser}),
    )

    result = service.parse_file(tmp_path / "mixed.xlsx")

    assert len(result.records) == 2
    assert result.detected_types == {
        WorkbookType.FUND_NAV_SUMMARY,
        WorkbookType.ASSET_NAV_BROWSER,
    }
    assert any(issue.code == IssueCode.MIXED_WORKBOOK_TYPES for issue in result.issues)


def test_missing_column_creates_structured_issue(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        [
            ["产品代码", "产品名称", "估值基准日"],
            ["F001", "吉余一号", "2026-07-24"],
        ]
    )
    service = ExcelParserService(
        _settings(tmp_path),
        reader=FakeWorkbookReader({"缺字段": frame}),
    )

    result = service.parse_file(tmp_path / "missing.xlsx")

    assert not result.records
    issue = next(issue for issue in result.issues if issue.code == IssueCode.MISSING_FIELD)
    assert issue.sheet_name == "缺字段"
    assert issue.raw_data == {"missing_fields": ["unit_nav"]}


def test_stop_before_custodian_disclaimer_without_creating_false_issue(
    tmp_path: Path,
) -> None:
    """中信等托管附件会在数据后紧接长篇声明，声明不能被当成基金记录。"""

    frame = pd.DataFrame(
        [
            ["日期", "资产代码", "资产名称", "资产份额净值(元)", "资产份额累计净值(元)"],
            ["2026-07-31", "F001", "吉余测试基金", "0.9383", "0.9383"],
            [" ", "", "", "", ""],
            ["声明：基金托管人已按合同约定完成净值复核。", "", "", "", ""],
            ["2026-08-01", "SHOULD_NOT_PARSE", "页脚后的内容", "9.9", "9.9"],
        ]
    )
    service = ExcelParserService(
        _settings(tmp_path),
        reader=FakeWorkbookReader({"日间净值列表": frame}),
    )

    result = service.parse_file(tmp_path / "托管净值.xlsx")

    assert [record.product_code for record in result.records] == ["F001"]
    assert not result.invalid_rows
    assert not result.issues
