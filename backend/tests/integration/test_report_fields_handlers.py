from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import func, select
from starlette.requests import Request

from app.api.deps import TenantContext
from app.api.schemas.report_field import (
    ReportFieldDefinitionCreate,
    ReportFieldDefinitionUpdate,
    ReportFieldResolveRequest,
    ReportFieldValueUpdate,
)
from app.api.v1.report_fields import (
    create_field,
    disable_field,
    resolve_fields,
    set_product_value,
    update_field,
)
from app.db.models import (
    FundProduct,
    ReportFieldDefinitionVersion,
    UserRole,
)


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
    )


def test_field_handlers_complete_definition_value_and_resolve_loop(app: FastAPI) -> None:
    del app
    from app.core.config import get_settings
    from app.db.session import configure_tenant_scope, get_database_manager
    from app.services.auth_service import AuthService
    from app.services.foundation_service import FoundationService

    with get_database_manager().session_factory() as session:
        identity = FoundationService(get_settings()).ensure(session)
        user = AuthService().create_user(
            session,
            username="field-handler-admin",
            password="AdminPass!2026",
            role=UserRole.ADMIN,
            tenant_id=identity.tenant_id,
        )
        configure_tenant_scope(
            session,
            tenant_id=identity.tenant_id,
            mailbox_ids=(identity.mailbox_account_id,),
        )
        product = FundProduct(
            tenant_id=identity.tenant_id,
            product_code="HANDLER001",
            product_name="字段处理器测试基金",
            source_profile={"manager_name": "合同管理机构"},
            source_profile_meta={
                "manager_name": {
                    "source_type": "contract",
                    "source_reference": "contract.pdf",
                }
            },
        )
        session.add(product)
        session.commit()
        scope = TenantContext(
            user=user,
            tenant_id=identity.tenant_id,
            tenant_code="default",
            tenant_name="默认业务账套",
            role=UserRole.ADMIN,
            mailbox_ids=(identity.mailbox_account_id,),
            content_mailbox_ids=(identity.mailbox_account_id,),
            operable_mailbox_ids=(identity.mailbox_account_id,),
            manageable_mailbox_ids=(identity.mailbox_account_id,),
        )

        created = create_field(
            ReportFieldDefinitionCreate(
                field_key="custom.roadshow_contact",
                label="路演联系人",
                data_type="string",
                value_kind="scalar",
                default_value="未配置",
            ),
            _request("/api/v1/report-fields"),
            session,
            scope,
        )
        initial = resolve_fields(
            ReportFieldResolveRequest(
                field_keys=["product.name", "custom.roadshow_contact"],
                product_id=product.id,
            ),
            session,
            scope,
        )
        saved = set_product_value(
            product.id,
            "custom.roadshow_contact",
            ReportFieldValueUpdate(value="张经理", source_reference="2026 路演资料"),
            _request("/api/v1/report-fields/products/1/values/custom.roadshow_contact"),
            session,
            scope,
        )
        resolved = resolve_fields(
            ReportFieldResolveRequest(
                field_keys=["product.manager_name", "custom.roadshow_contact"],
                product_id=product.id,
            ),
            session,
            scope,
        )
        updated = update_field(
            created.id or 0,
            ReportFieldDefinitionUpdate(label="路演对接人", is_required=True),
            _request("/api/v1/report-fields/1"),
            session,
            scope,
        )
        disabled = disable_field(
            created.id or 0,
            _request("/api/v1/report-fields/1/disable"),
            session,
            scope,
        )
        version_count = session.scalar(
            select(func.count(ReportFieldDefinitionVersion.id)).where(
                ReportFieldDefinitionVersion.field_definition_id == created.id
            )
        )

        assert initial.fields["product.name"].value == "字段处理器测试基金"
        assert initial.fields["custom.roadshow_contact"].value == "未配置"
        assert initial.fields["custom.roadshow_contact"].used_default is True
        assert saved.value == "张经理"
        assert resolved.fields["product.manager_name"].source_reference == "contract.pdf"
        assert resolved.fields["custom.roadshow_contact"].value == "张经理"
        assert updated.version == 2
        assert disabled.version == 3
        assert disabled.is_active is False
        assert version_count == 3
