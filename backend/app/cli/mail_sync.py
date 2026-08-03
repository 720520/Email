"""人工执行一次邮箱同步：python -m app.cli.mail_sync。"""

from __future__ import annotations

import json
import logging

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.models import TriggerType
from app.db.session import get_database_manager
from app.services.mail_sync_runner import MailSyncRunner


def main() -> int:
    settings = get_settings()
    configure_logging(settings)
    manager = get_database_manager()
    execution = MailSyncRunner(settings, manager.session_factory).run(
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
