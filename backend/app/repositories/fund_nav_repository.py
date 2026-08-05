"""基金净值仓储。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import FundNav


@dataclass(frozen=True, slots=True)
class NavInsertResult:
    record: FundNav
    inserted: bool


class FundNavRepository:
    """只允许插入，不提供覆盖更新接口。"""

    @staticmethod
    def find_by_business_key(
        session: Session,
        *,
        tenant_id: int,
        product_code: str,
        nav_date: date,
    ) -> FundNav | None:
        statement = select(FundNav).where(
            FundNav.tenant_id == tenant_id,
            FundNav.product_code == product_code,
            FundNav.nav_date == nav_date,
        ).execution_options(skip_mailbox_scope=True)
        return session.scalar(statement)

    def insert_if_absent(self, session: Session, candidate: FundNav) -> NavInsertResult:
        """通过预查和保存点处理普通重复与并发重复，且不污染外层事务。"""

        existing = self.find_by_business_key(
            session,
            tenant_id=candidate.tenant_id,
            product_code=candidate.product_code,
            nav_date=candidate.nav_date,
        )
        if existing is not None:
            return NavInsertResult(record=existing, inserted=False)

        try:
            with session.begin_nested():
                session.add(candidate)
                session.flush()
        except IntegrityError:
            # 唯一约束可能被另一事务抢先写入；保存点回滚后外层事务仍可记录异常。
            existing = self.find_by_business_key(
                session,
                tenant_id=candidate.tenant_id,
                product_code=candidate.product_code,
                nav_date=candidate.nav_date,
            )
            if existing is None:
                raise
            return NavInsertResult(record=existing, inserted=False)
        return NavInsertResult(record=candidate, inserted=True)
