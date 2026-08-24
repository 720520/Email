"""受控字段 Provider 与统一解析器。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import FundProduct, ReportFieldDefinition, ReportFieldValue
from app.services.reporting_service import ReportDataService

SYSTEM_FIELD_CATALOG: dict[str, dict[str, Any]] = {
    "product.name": {
        "label": "产品名称",
        "data_type": "string",
        "source_type": "model",
        "requires_product": True,
    },
    "product.code": {
        "label": "产品代码/备案代码",
        "data_type": "string",
        "source_type": "model",
        "requires_product": True,
    },
    "product.investment_manager": {
        "label": "投资经理",
        "data_type": "rich_text",
        "source_type": "model",
        "requires_product": True,
    },
    "product.investment_strategy": {
        "label": "投资策略",
        "data_type": "rich_text",
        "source_type": "model",
        "requires_product": True,
    },
    "product.inception_date": {
        "label": "成立日期",
        "data_type": "date",
        "source_type": "contract",
        "requires_product": True,
    },
    "product.manager_name": {
        "label": "管理机构",
        "data_type": "string",
        "source_type": "contract",
        "requires_product": True,
    },
    "product.custodian_name": {
        "label": "托管/外包机构",
        "data_type": "string",
        "source_type": "contract",
        "requires_product": True,
    },
    "report.date": {
        "label": "报告日期",
        "data_type": "date",
        "source_type": "system",
        "requires_product": False,
    },
    "tenant.name": {
        "label": "当前租户名称",
        "data_type": "string",
        "source_type": "system",
        "requires_product": False,
    },
    "metric.annualized_return": {
        "label": "年化收益率",
        "data_type": "percentage",
        "source_type": "metric",
        "requires_product": True,
    },
    "metric.sharpe_ratio": {
        "label": "夏普比率",
        "data_type": "number",
        "source_type": "metric",
        "requires_product": True,
    },
    "metric.return_ytd": {
        "label": "今年以来收益",
        "data_type": "percentage",
        "source_type": "metric",
        "requires_product": True,
    },
    "metric.max_drawdown_since": {
        "label": "成立以来最大回撤",
        "data_type": "percentage",
        "source_type": "metric",
        "requires_product": True,
    },
    "chart.nav_history": {
        "label": "净值曲线",
        "data_type": "chart",
        "value_kind": "chart",
        "source_type": "metric",
        "requires_product": True,
    },
    "email.subject": {
        "label": "来源邮件主题",
        "data_type": "string",
        "source_type": "email",
        "requires_product": False,
    },
    "email.sender": {
        "label": "来源邮件发件人",
        "data_type": "string",
        "source_type": "email",
        "requires_product": False,
    },
    "email.received_at": {
        "label": "来源邮件接收时间",
        "data_type": "date",
        "source_type": "email",
        "requires_product": False,
    },
}

_PROFILE_KEYS = {
    "product.inception_date": "inception_date",
    "product.manager_name": "manager_name",
    "product.custodian_name": "custodian_name",
}


@dataclass(frozen=True, slots=True)
class FieldContext:
    tenant_id: int
    tenant_name: str
    product_id: int | None = None
    report_date: date | None = None
    email_fields: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ResolvedValue:
    value: Any
    source_type: str | None
    source_reference: str | None = None
    used_default: bool = False


class ModelFieldProvider:
    @staticmethod
    def resolve(key: str, product: FundProduct) -> ResolvedValue:
        if key == "product.name":
            return ResolvedValue(product.product_name, "model")
        if key == "product.code":
            return ResolvedValue(product.product_code, "model")
        if key == "product.investment_manager":
            return ResolvedValue(product.investment_manager_info, "model")
        return ResolvedValue(product.investment_strategy_info, "model")


class ContractFieldProvider:
    @staticmethod
    def resolve(key: str, product: FundProduct) -> ResolvedValue:
        profile_key = _PROFILE_KEYS[key]
        meta = (product.source_profile_meta or {}).get(profile_key, {})
        return ResolvedValue(
            product.effective_profile().get(profile_key),
            meta.get("source_type", "contract") if isinstance(meta, dict) else "contract",
            meta.get("source_reference") if isinstance(meta, dict) else None,
        )


class EmailFieldProvider:
    @staticmethod
    def resolve(key: str, context: FieldContext) -> ResolvedValue:
        return ResolvedValue((context.email_fields or {}).get(key), "email")


class MetricFieldProvider:
    @staticmethod
    def resolve(key: str, snapshot: dict[str, Any]) -> ResolvedValue:
        if key == "chart.nav_history":
            return ResolvedValue(snapshot.get("nav_series", []), "metric")
        return ResolvedValue(
            snapshot.get("performance", {}).get(key.removeprefix("metric.")), "metric"
        )


class SystemFieldProvider:
    @staticmethod
    def resolve(key: str, context: FieldContext) -> ResolvedValue:
        if key == "report.date":
            return ResolvedValue(context.report_date or date.today(), "system")
        return ResolvedValue(context.tenant_name, "system")


class CustomFieldProvider:
    @staticmethod
    def resolve(
        resolver: ReportFieldResolver,
        session: Session,
        definition: dict[str, Any],
        product: FundProduct | None,
        report_date: date | None,
    ) -> ResolvedValue:
        return resolver._custom(session, definition, product, report_date)


class ReportFieldResolver:
    """仅通过白名单 Provider 取值，不允许动态属性访问或 eval。"""

    def resolve_many(
        self,
        session: Session,
        field_keys: list[str],
        context: FieldContext,
        *,
        allow_inactive: bool = False,
    ) -> dict[str, tuple[dict[str, Any], ResolvedValue]]:
        product = self._product(session, context.product_id) if context.product_id else None
        metric_snapshot: dict[str, Any] | None = None
        result: dict[str, tuple[dict[str, Any], ResolvedValue]] = {}
        for key in dict.fromkeys(field_keys):
            definition = self.definition(session, key, allow_inactive=allow_inactive)
            if definition.get("requires_product") and product is None:
                raise AppError("REPORT_FIELD_PRODUCT_REQUIRED", f"字段 {key} 需要选择基金产品")
            source_type = definition["source_type"]
            if source_type == "custom":
                resolved = CustomFieldProvider.resolve(
                    self, session, definition, product, context.report_date
                )
            elif source_type == "model":
                assert product is not None
                resolved = ModelFieldProvider.resolve(key, product)
            elif source_type == "contract":
                assert product is not None
                resolved = ContractFieldProvider.resolve(key, product)
            elif source_type == "email":
                resolved = EmailFieldProvider.resolve(key, context)
            elif source_type == "system":
                resolved = SystemFieldProvider.resolve(key, context)
            elif source_type == "metric":
                assert product is not None
                if metric_snapshot is None:
                    metric_snapshot = ReportDataService().build_snapshot(
                        session, product, report_date=context.report_date, share_product_code=None
                    )
                resolved = MetricFieldProvider.resolve(key, metric_snapshot)
            else:
                raise AppError("REPORT_FIELD_SOURCE_UNSUPPORTED", f"字段 {key} 来源不受支持")
            if resolved.value is None and definition.get("default_value") is not None:
                resolved = ResolvedValue(
                    self.coerce(definition["data_type"], definition["default_value"]),
                    "default",
                    used_default=True,
                )
            result[key] = (definition, resolved)
        return result

    def definition(
        self, session: Session, field_key: str, *, allow_inactive: bool = False
    ) -> dict[str, Any]:
        system = SYSTEM_FIELD_CATALOG.get(field_key)
        if system:
            return {
                "id": None,
                "field_key": field_key,
                "description": None,
                "value_kind": system.get("value_kind", "scalar"),
                "format_config": {},
                "default_value": None,
                "is_required": False,
                "is_sensitive": False,
                "is_active": True,
                "is_system": True,
                "version": 1,
                **system,
            }
        row = session.scalar(
            select(ReportFieldDefinition).where(ReportFieldDefinition.field_key == field_key)
        )
        if row is None or (not row.is_active and not allow_inactive):
            raise AppError(
                "REPORT_FIELD_NOT_FOUND", f"报表字段不存在或已停用：{field_key}", status_code=404
            )
        return self.custom_definition(row)

    @staticmethod
    def custom_definition(row: ReportFieldDefinition) -> dict[str, Any]:
        return {
            "id": row.id,
            "field_key": row.field_key,
            "label": row.label,
            "description": row.description,
            "data_type": row.data_type,
            "value_kind": row.value_kind,
            "source_type": row.source_type,
            "format_config": row.format_config or {},
            "default_value": row.default_value,
            "is_required": row.is_required,
            "is_sensitive": row.is_sensitive,
            "is_active": row.is_active,
            "is_system": False,
            "version": row.version,
            "create_time": row.create_time,
            "update_time": row.update_time,
            "requires_product": True,
        }

    @staticmethod
    def _product(session: Session, product_id: int) -> FundProduct:
        product = session.get(FundProduct, product_id)
        if product is None:
            raise AppError("FUND_PRODUCT_NOT_FOUND", "未找到该基金产品", status_code=404)
        return product

    def _custom(
        self,
        session: Session,
        definition: dict[str, Any],
        product: FundProduct | None,
        report_date: date | None,
    ) -> ResolvedValue:
        assert product is not None
        conditions = [
            ReportFieldValue.field_definition_id == definition["id"],
            ReportFieldValue.entity_type == "fund_product",
            ReportFieldValue.entity_id == product.id,
        ]
        if report_date:
            conditions.append(
                or_(
                    ReportFieldValue.effective_date.is_(None),
                    ReportFieldValue.effective_date <= report_date,
                )
            )
        row = session.scalar(
            select(ReportFieldValue)
            .where(*conditions)
            .order_by(
                ReportFieldValue.effective_date.desc().nullslast(), ReportFieldValue.id.desc()
            )
        )
        if row is None:
            return ResolvedValue(None, None)
        value = row.value_json if row.value_json is not None else row.value_text
        return ResolvedValue(
            self.coerce(definition["data_type"], value),
            row.source_type,
            row.source_reference,
        )

    @staticmethod
    def coerce(data_type: str, value: Any) -> Any:
        if value is None:
            return None
        if data_type in {"string", "rich_text", "image", "date"}:
            return str(value).strip()
        if data_type in {"number", "percentage"}:
            try:
                return str(Decimal(str(value).strip().rstrip("%")))
            except InvalidOperation as exc:
                raise AppError("REPORT_FIELD_VALUE_INVALID", "字段值不是有效数字") from exc
        if data_type == "boolean":
            if isinstance(value, bool):
                return value
            normalized = str(value).strip().lower()
            if normalized in {"true", "1", "yes", "是"}:
                return True
            if normalized in {"false", "0", "no", "否"}:
                return False
            raise AppError("REPORT_FIELD_VALUE_INVALID", "布尔字段必须是 true/false")
        if data_type in {"list", "table", "chart"} and not isinstance(value, list):
            raise AppError("REPORT_FIELD_VALUE_INVALID", "结构化字段必须是数组")
        if data_type == "json" and not isinstance(value, (dict, list, str, int, float, bool)):
            raise AppError("REPORT_FIELD_VALUE_INVALID", "JSON 字段值无效")
        return value
