from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from pptx import Presentation

from app.db.models import FundProduct
from app.services.report_presentation_service import ReportPresentationService
from app.services.reporting_service import (
    DEFAULT_REPORT_SECTIONS,
    ReportDataService,
    extract_contract_fields,
)


def test_extract_contract_fields_keeps_high_confidence_values() -> None:
    text = """
    基金名称：吉余测试一号私募证券投资基金
    基金备案编码：SABCDE
    成立日期：2024年1月8日
    基金管理人：上海吉余私募基金管理有限公司
    托管机构：中信证券股份有限公司
    风险等级：R4
    开放日：每周三
    管理费率：1.50%/年
    业绩报酬比例：20%
    投资范围：国内期货交易所期货及期权
    """

    fields = extract_contract_fields(text)

    assert fields["product_code"] == "SABCDE"
    assert fields["inception_date"] == "2024年1月8日"
    assert fields["risk_level"] == "R4"
    assert fields["management_fee"] == "1.50%/年"
    assert fields["performance_fee"] == "20%"


def test_manual_field_override_can_restore_source() -> None:
    product = FundProduct(
        tenant_id=1,
        product_code="SABCDE",
        product_name="测试基金",
        source_profile={"risk_level": "R4"},
        source_profile_meta={},
        manual_profile={},
    )
    service = ReportDataService()

    before, after = service.update_field(
        product,
        field_key="risk_level",
        value="R3",
        restore_source=False,
    )
    assert (before, after) == ("R4", "R3")
    assert product.manual_profile == {"risk_level": "R3"}

    before, after = service.update_field(
        product,
        field_key="risk_level",
        value=None,
        restore_source=True,
    )
    assert (before, after) == ("R3", "R4")
    assert product.manual_profile == {}


def test_standard_weekly_presentation_can_be_reopened(tmp_path: Path) -> None:
    start = date(2025, 1, 3)
    nav_series = [
        {
            "date": (start + timedelta(days=index * 7)).isoformat(),
            "unit_nav": str(Decimal("1.0") + Decimal(index) / Decimal("100")),
            "total_nav": str(Decimal("1.0") + Decimal(index) / Decimal("100")),
        }
        for index in range(20)
    ]
    snapshot = {
        "product_name": "吉余测试一号私募证券投资基金",
        "report_date": nav_series[-1]["date"],
        "fields": {
            "product_name": "吉余测试一号私募证券投资基金",
            "inception_date": "2025-01-03",
            "strategy_category": "复合CTA",
            "latest_unit_nav": "1.1900",
            "latest_total_nav": "1.1900",
            "investment_strategy": "采用跨期、跨品种和趋势策略组合，控制单品种风险暴露。",
            "manager_name": "测试管理人",
            "custodian_name": "测试托管人",
            "risk_level": "R4",
            "open_day": "每周三",
            "duration": "15年",
            "lockup_period": "开放式",
            "management_fee": "1.50%/年",
            "custody_fee": "0.04%/年",
            "subscription_fee": "1%",
            "redemption_fee": "1%",
            "performance_fee": "20%",
            "investment_scope": "国内期货交易所期货及期权",
        },
        "performance": {
            "annualized_return": "18.00%",
            "sharpe_ratio": "1.40",
            "return_1m": "2.10%",
            "return_3m": "5.20%",
            "return_6m": "8.00%",
            "return_ytd": "19.00%",
            "return_1y": "19.00%",
            "return_since": "19.00%",
            "max_drawdown_ytd": "-2.00%",
            "max_drawdown_since": "-2.00%",
        },
        "nav_series": nav_series,
    }
    output = tmp_path / "weekly.pptx"

    ReportPresentationService().generate(
        snapshot,
        output_path=output,
        sections=DEFAULT_REPORT_SECTIONS,
    )

    presentation = Presentation(output)
    assert len(presentation.slides) == 1
    assert output.stat().st_size > 20_000
