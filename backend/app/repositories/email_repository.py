"""邮件与附件仓储。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EmailRecord


class EmailRepository:
    """封装邮件幂等键查询，避免业务层重复拼接条件。"""

    @staticmethod
    def find_by_uid(
        session: Session,
        *,
        tenant_id: int,
        mailbox_account_id: int,
        uid_validity: str,
        message_uid: str,
    ) -> EmailRecord | None:
        statement = select(EmailRecord).where(
            EmailRecord.tenant_id == tenant_id,
            EmailRecord.mailbox_account_id == mailbox_account_id,
            EmailRecord.uid_validity == uid_validity,
            EmailRecord.message_uid == message_uid,
        )
        return session.scalar(statement)

    @staticmethod
    def get(
        session: Session,
        email_id: int,
        *,
        tenant_id: int,
        mailbox_ids: tuple[int, ...],
    ) -> EmailRecord | None:
        return session.scalar(
            select(EmailRecord).where(
                EmailRecord.id == email_id,
                EmailRecord.tenant_id == tenant_id,
                EmailRecord.mailbox_account_id.in_(mailbox_ids),
            )
        )
