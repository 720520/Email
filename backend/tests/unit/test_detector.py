from pathlib import Path

import pandas as pd

from app.core.config import ExcelSettings
from app.parsers.detector import TableDetector
from app.parsers.field_registry import FieldAliasRegistry
from app.parsers.models import WorkbookType

ALIAS_FILE = Path(__file__).resolve().parents[3] / "config/excel_fields.yaml"


def _detector(**overrides) -> TableDetector:
    settings = ExcelSettings(**overrides)
    return TableDetector(FieldAliasRegistry.from_yaml(ALIAS_FILE), settings)


def test_detect_single_fund_with_title_metadata_and_two_line_header() -> None:
    frame = pd.DataFrame(
        [
            ["基金每日净值表", None, None, None],
            ["日期：2026-07-24", None, None, None],
            ["资产", "资产", "资产份额", "资产份额累计"],
            ["代码", "名称", "净值(元)", "净值(元)"],
            ["SAWK26", "吉余测试基金", "1.02560000", "1.12340000"],
        ]
    )

    detection = _detector().detect("净值表", frame)

    assert detection is not None
    assert detection.workbook_type == WorkbookType.SINGLE_FUND_DAILY
    assert detection.header_start_row == 2
    assert detection.header_row_count == 2
    assert set(detection.field_columns) == {
        "product_code",
        "product_name",
        "unit_nav",
        "total_nav",
    }
    assert detection.ambiguous_with is None


def test_detect_summary_using_another_custodian_aliases() -> None:
    frame = pd.DataFrame(
        [
            ["基金编号", "基金全称", "净值日期", "份额净值", "累计单位净值", "净资产"],
            ["F001", "吉余一号", "2026/07/24", 1.1, 1.2, 10_000_000],
        ]
    )

    detection = _detector().detect("Sheet1", frame)

    assert detection is not None
    assert detection.workbook_type == WorkbookType.FUND_NAV_SUMMARY
    assert detection.missing_fields == ()
    assert detection.ambiguous_with is None


def test_detect_asset_browser_by_asset_value_and_share() -> None:
    frame = pd.DataFrame(
        [
            ["产品名称", "产品代码", "日期", "资产净值", "资产份额", "单位净值", "累计净值"],
            ["吉余全球易一号", "F002", "2026-07-24", 20_000_000, 10_000_000, 2, 2.1],
        ]
    )

    detection = _detector().detect("资产净值", frame)

    assert detection is not None
    assert detection.workbook_type == WorkbookType.ASSET_NAV_BROWSER
    assert detection.ambiguous_with is None


def test_report_missing_required_field_instead_of_guessing() -> None:
    frame = pd.DataFrame(
        [
            ["产品代码", "产品名称", "估值基准日"],
            ["F001", "吉余一号", "2026-07-24"],
        ]
    )

    detection = _detector().detect("Sheet1", frame)

    assert detection is not None
    assert detection.workbook_type == WorkbookType.FUND_NAV_SUMMARY
    assert detection.missing_fields == ("unit_nav",)


def test_mark_format_ambiguous_when_scores_are_too_close() -> None:
    frame = pd.DataFrame(
        [
            ["基金代码", "基金名称", "净值日期", "份额净值"],
            ["F001", "吉余一号", "2026-07-24", 1.1],
        ]
    )

    detection = _detector(ambiguity_score_delta=50).detect("Sheet1", frame)

    assert detection is not None
    assert detection.ambiguous_with is not None
