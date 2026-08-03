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
        mailbox_key: str,
        uid_validity: str,
        message_uid: str,
    ) -> EmailRecord | None:
        statement = select(EmailRecord).where(
            EmailRecord.mailbox_key == mailbox_key,
            EmailRecord.uid_validity == uid_validity,
            EmailRecord.message_uid == message_uid,
        )
        return session.scalar(statement)

    @staticmethod
    def get(session: Session, email_id: int) -> EmailRecord | None:
        return session.get(EmailRecord, email_id)
