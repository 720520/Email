from __future__ import annotations

from decimal import Decimal
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


def test_parse_browser_uses_filing_code_instead_of_ta_code(tmp_path: Path) -> None:
    """TA 代码不是产品唯一标识；缺少产品代码时应使用备案编码。"""

    frame = pd.DataFrame(
        [
            [
                "产品名称",
                "TA代码",
                "净值日期",
                "单位净值",
                "累计单位净值",
                "资产净值",
                "资产份额",
                "备案编码",
                "资产总值",
            ],
            [
                "吉余商指陆号私募证券投资基金",
                "SA2889",
                "20260731",
                "1.3029",
                "1.3029",
                "53092427.62",
                "40748888.77",
                "SARD55",
                "53465590.67",
            ],
        ]
    )
    service = ExcelParserService(
        _settings(tmp_path),
        reader=FakeWorkbookReader({"Sheet1": frame}),
    )

    result = service.parse_file(tmp_path / "商指陆号净值表.xlsx")

    assert result.detected_types == {WorkbookType.ASSET_NAV_BROWSER}
    assert len(result.records) == 1
    record = result.records[0]
    assert record.product_code == "SARD55"
    assert record.product_code != "SA2889"
    assert record.nav_date.isoformat() == "2026-07-31"
    assert str(record.unit_nav) == "1.3029"
    assert str(record.asset_value) == "53092427.62"
    assert not result.issues


def test_parse_citics_product_elements_and_supplemental_profile(tmp_path: Path) -> None:
    """中信资产代码用于份额快照，备案代码用于产品主体，说明区单独提取。"""

    frame = pd.DataFrame(
        [
            [
                "日期",
                "资产代码",
                "资产名称",
                "资产份额净值(元)",
                "资产份额累计净值(元)",
                "资产净值(元)",
                "实收资本(元)",
                "总资产(元)",
                "总资产/资产净值",
                "协会备案代码",
                "母基金产品代码",
                "母基金产品名称",
            ],
            [
                "2026-08-04",
                "T08604(B级)",
                "吉余牡丹私募证券投资基金B类",
                "1.0234",
                "1.1234",
                "10000000",
                "9000000",
                "10010000",
                "100.10%",
                "SAVH33",
                "SAVH33",
                "吉余牡丹私募证券投资基金",
            ],
            ["投资经理信息：张某，具有多年投资管理经验。", None, None, None],
            ["投资策略信息：采用多策略组合并严格控制回撤。", None, None, None],
            ["声明：本附件由系统发送。", None, None, None],
        ]
    )
    service = ExcelParserService(
        _settings(tmp_path),
        reader=FakeWorkbookReader({"净值": frame}),
    )

    result = service.parse_file(tmp_path / "中信产品要素.xlsx")

    assert len(result.records) == 1
    record = result.records[0]
    assert record.product_code == "T08604(B级)"
    assert record.asset_code == "T08604(B级)"
    assert record.registration_code == "SAVH33"
    assert record.share_class == "B类"
    assert record.paid_in_capital == 9_000_000
    assert record.total_assets_nav_ratio == Decimal("1.001")
    assert record.parent_product_code == "SAVH33"
    assert record.investment_manager_info.startswith("张某")
    assert record.investment_strategy_info.startswith("采用多策略")
    assert not result.issues
