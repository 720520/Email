"""人工执行一次邮箱同步：python -m app.cli.mail_sync。"""

from __future__ import annotations

import argparse
import json
import logging

from sqlalchemy import select

from app.core.config import get_settings
from app.core.credential_security import (
    dedicated_audit_key_configured,
    dedicated_credential_key_configured,
)
from app.core.logging import configure_logging
from app.db.models import MailboxAccount, TriggerType
from app.db.session import get_database_manager
from app.services.foundation_service import FoundationService
from app.services.mail_sync_runner import MailSyncRunner
from app.services.mailbox_account_service import MailboxAccountService


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="人工同步一个已配置的邮箱账户")
    parser.add_argument(
        "--mailbox-id",
        type=int,
        help="邮箱账户 ID；省略时同步当前租户默认邮箱",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    settings = get_settings()
    configure_logging(settings)
    if not (
        dedicated_credential_key_configured(settings.security)
        and dedicated_audit_key_configured(settings.security)
    ):
        print("请先配置独立邮箱凭据密钥和审计签名密钥")
        return 2
    manager = get_database_manager()
    with manager.session_factory() as session, session.begin():
        session.info["skip_tenant_scope"] = True
        foundation = FoundationService(settings).ensure(session)
        mailbox = session.scalar(
            select(MailboxAccount).where(
                MailboxAccount.id
                == (args.mailbox_id or foundation.mailbox_account_id),
                MailboxAccount.tenant_id == foundation.tenant_id,
                MailboxAccount.is_enabled.is_(True),
            )
        )
        if mailbox is None:
            raise RuntimeError("邮箱账户不存在、已停用或不属于当前租户")
        email_settings = MailboxAccountService(settings).runtime_settings(mailbox)
    execution = MailSyncRunner(
        settings,
        manager.session_factory,
        tenant_id=foundation.tenant_id,
        mailbox_account_id=foundation.mailbox_account_id,
        email_settings=email_settings,
    ).run(
        trigger_type=TriggerType.MANUAL
    )
    result = execution.result
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    if result.fatal_error or result.failed_uids:
        logging.getLogger(__name__).error("邮件同步未完全成功")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
