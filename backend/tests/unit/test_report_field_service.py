from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.db.models import FundProduct
from app.services.report_field_service import (
    SYSTEM_FIELD_CATALOG,
    ContractFieldProvider,
    EmailFieldProvider,
    FieldContext,
    MetricFieldProvider,
    ModelFieldProvider,
    ReportFieldResolver,
    SystemFieldProvider,
)


def test_system_field_catalog_uses_stable_namespaced_keys() -> None:
    assert "product.name" in SYSTEM_FIELD_CATALOG
    assert "report.date" in SYSTEM_FIELD_CATALOG
    assert "metric.annualized_return" in SYSTEM_FIELD_CATALOG
    assert "chart.nav_history" in SYSTEM_FIELD_CATALOG
    assert all("." in key for key in SYSTEM_FIELD_CATALOG)


@pytest.mark.parametrize(
    ("data_type", "raw", "expected"),
    [
        ("string", "  测试  ", "测试"),
        ("number", "1.230", "1.230"),
        ("percentage", "12.5%", "12.5"),
        ("boolean", "是", True),
        ("boolean", "false", False),
        ("list", [{"name": "A"}], [{"name": "A"}]),
    ],
)
def test_coerce_supported_field_values(data_type: str, raw: object, expected: object) -> None:
    assert ReportFieldResolver.coerce(data_type, raw) == expected


def test_coerce_rejects_invalid_structured_value() -> None:
    with pytest.raises(AppError) as error:
        ReportFieldResolver.coerce("table", {"not": "a list"})
    assert error.value.code == "REPORT_FIELD_VALUE_INVALID"


def test_coerce_rejects_invalid_boolean() -> None:
    with pytest.raises(AppError) as error:
        ReportFieldResolver.coerce("boolean", "maybe")
    assert error.value.code == "REPORT_FIELD_VALUE_INVALID"


def test_whitelisted_providers_resolve_their_owned_sources() -> None:
    product = FundProduct(
        tenant_id=1,
        product_code="PROVIDER001",
        product_name="Provider 测试基金",
        source_profile={"manager_name": "测试管理机构"},
        source_profile_meta={
            "manager_name": {
                "source_type": "contract",
                "source_reference": "contract.pdf",
            }
        },
    )
    context = FieldContext(
        tenant_id=1,
        tenant_name="测试租户",
        email_fields={"email.subject": "净值日报"},
    )

    assert ModelFieldProvider.resolve("product.name", product).value == "Provider 测试基金"
    assert ContractFieldProvider.resolve("product.manager_name", product).source_reference == (
        "contract.pdf"
    )
    assert EmailFieldProvider.resolve("email.subject", context).value == "净值日报"
    assert SystemFieldProvider.resolve("tenant.name", context).value == "测试租户"
    assert (
        MetricFieldProvider.resolve(
            "metric.annualized_return", {"performance": {"annualized_return": "8.00%"}}
        ).value
        == "8.00%"
    )
