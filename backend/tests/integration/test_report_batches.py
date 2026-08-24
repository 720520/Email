from __future__ import annotations

import io
import zipfile
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from starlette.requests import Request

from app.api.deps import TenantContext
from app.api.schemas.reporting import ReportBatchCreate
from app.api.v1.reports import (
    cancel_report_batch,
    create_report_batch,
    download_report_batch,
    retry_report_batch,
)
from app.db.models import (
    FundNav,
    FundProduct,
    ReportBatch,
    ReportBatchItem,
    ReportRun,
    UserRole,
)
from app.db.types import utc_now
from app.services.report_batch_worker import ReportBatchWorker


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/reports/batches",
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
    )


def _seed(session, count: int):
    from app.core.config import get_settings
    from app.db.session import configure_tenant_scope
    from app.services.auth_service import AuthService
    from app.services.foundation_service import FoundationService

    identity = FoundationService(get_settings()).ensure(session)
    user = AuthService().create_user(
        session,
        username="batch-admin",
        password="AdminPass!2026",
        role=UserRole.ADMIN,
        tenant_id=identity.tenant_id,
    )
    configure_tenant_scope(
        session,
        tenant_id=identity.tenant_id,
        mailbox_ids=(identity.mailbox_account_id,),
    )
    products = [
        FundProduct(
            tenant_id=identity.tenant_id,
            product_code=f"BATCH-{index:03d}",
            product_name=f"批量基金 {index:03d}",
        )
        for index in range(count)
    ]
    session.add_all(products)
    session.flush()
    session.add_all(
        FundNav(
            tenant_id=identity.tenant_id,
            mailbox_account_id=identity.mailbox_account_id,
            product_name=product.product_name,
            product_code=product.product_code,
            master_product_code=product.product_code,
            nav_date=date(2026, 8, 21),
            unit_nav=Decimal("1.0000"),
            total_nav=Decimal("1.0000"),
            source_file="batch-test.xlsx",
        )
        for product in products
    )
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
    session.commit()
    return identity, scope, products


@pytest.mark.parametrize("count", [1, 10, 100])
def test_batch_sizes_idempotency_and_worker_isolation(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, count: int
) -> None:
    del app
    import app.services.report_batch_worker as worker_module
    from app.db.session import configure_tenant_scope, get_database_manager

    manager = get_database_manager()
    with manager.session_factory() as session:
        identity, scope, products = _seed(session, count)
        configure_tenant_scope(
            session,
            tenant_id=identity.tenant_id,
            mailbox_ids=(identity.mailbox_account_id,),
        )
        payload = ReportBatchCreate(
            product_ids=[product.id for product in products],
            template_key="builtin:weekly",
            report_date=date(2026, 8, 21),
            idempotency_key=f"batch-size-{count}",
        )
        created = create_report_batch(payload, _request(), session, scope)
        duplicate = create_report_batch(payload, _request(), session, scope)
        assert created.id == duplicate.id
        assert created.total_count == count

    failed_product_id = products[count // 2].id if count > 1 else None

    def fake_create(_session, run, *_args, **_kwargs):
        if run.fund_product_id == failed_product_id:
            raise RuntimeError("模拟单项渲染失败")

    monkeypatch.setattr(worker_module, "_create_file_version", fake_create)
    worker = ReportBatchWorker(manager.session_factory, "test-worker")
    processed = 0
    while worker.run_once():
        processed += 1
    assert processed == count

    with manager.session_factory() as session:
        session.info["skip_tenant_scope"] = True
        batch = session.get(ReportBatch, created.id)
        assert batch is not None
        assert batch.success_count == count - (1 if failed_product_id else 0)
        assert batch.failed_count == (1 if failed_product_id else 0)
        assert session.scalar(select(func.count(ReportRun.id))) == count
        assert worker.run_once() is False
        if failed_product_id:
            retry_report_batch(created.id, _request(), session, scope)

    if failed_product_id:
        monkeypatch.setattr(worker_module, "_create_file_version", lambda *_args, **_kwargs: None)
        assert worker.run_once() is True
        with manager.session_factory() as session:
            session.info["skip_tenant_scope"] = True
            retried = session.get(ReportBatch, created.id)
            assert retried is not None and retried.success_count == count
            assert retried.failed_count == 0
            assert session.scalar(select(func.count(ReportRun.id))) == count


def test_claim_recovery_and_no_duplicate_claim(app: FastAPI) -> None:
    del app
    from app.db.session import configure_tenant_scope, get_database_manager

    manager = get_database_manager()
    with manager.session_factory() as session:
        identity, scope, products = _seed(session, 2)
        configure_tenant_scope(
            session,
            tenant_id=identity.tenant_id,
            mailbox_ids=(identity.mailbox_account_id,),
        )
        batch = create_report_batch(
            ReportBatchCreate(
                product_ids=[product.id for product in products],
                template_key="builtin:weekly",
                report_date=date(2026, 8, 21),
                idempotency_key="claim-recovery",
            ),
            _request(),
            session,
            scope,
        )

    first = ReportBatchWorker(manager.session_factory, "worker-a")._claim()
    second_worker = ReportBatchWorker(manager.session_factory, "worker-b")
    second = second_worker._claim()
    assert first and second and first[0] != second[0]
    with manager.session_factory() as session, session.begin():
        session.info["skip_tenant_scope"] = True
        item = session.get(ReportBatchItem, first[0])
        assert item is not None
        item.locked_at = utc_now() - timedelta(minutes=60)
    assert second_worker.recover_stale(stale_minutes=15) == 1
    with manager.session_factory() as session:
        session.info["skip_tenant_scope"] = True
        statuses = list(
            session.scalars(
                select(ReportBatchItem.status)
                .where(ReportBatchItem.batch_id == batch.id)
                .order_by(ReportBatchItem.id)
            )
        )
        assert statuses == ["pending", "processing"]

    with manager.session_factory() as session:
        configure_tenant_scope(session, tenant_id=identity.tenant_id + 999, mailbox_ids=())
        assert session.get(ReportBatch, batch.id) is None
        assert (
            session.scalar(select(ReportBatchItem).where(ReportBatchItem.batch_id == batch.id))
            is None
        )


@pytest.mark.anyio
async def test_real_batch_render_cancel_and_zip_download(app: FastAPI) -> None:
    del app
    from app.db.session import configure_tenant_scope, get_database_manager

    manager = get_database_manager()
    with manager.session_factory() as session:
        identity, scope, products = _seed(session, 2)
        configure_tenant_scope(
            session,
            tenant_id=identity.tenant_id,
            mailbox_ids=(identity.mailbox_account_id,),
        )
        batch = create_report_batch(
            ReportBatchCreate(
                product_ids=[product.id for product in products],
                template_key="builtin:weekly",
                report_date=date(2026, 8, 21),
                idempotency_key="real-render-zip",
            ),
            _request(),
            session,
            scope,
        )
    assert ReportBatchWorker(manager.session_factory, "real-worker").run_once()
    with manager.session_factory() as session:
        configure_tenant_scope(
            session,
            tenant_id=identity.tenant_id,
            mailbox_ids=(identity.mailbox_account_id,),
        )
        cancelled = cancel_report_batch(batch.id, _request(), session, scope)
        assert cancelled.success_count == 1
        assert cancelled.cancelled_count == 1
        response = download_report_batch(batch.id, _request(), session, scope)
        body = b"".join([chunk async for chunk in response.body_iterator])
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist()
        assert any(name.endswith(".pptx") for name in names)
        assert "失败清单.csv" in names
