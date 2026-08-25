"""独立附件解析 Worker：python -m app.cli.attachment_parse_worker。"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_database_manager
from app.services.attachment_parse_worker import AttachmentParseWorker


def _consume(slot: int, once: bool) -> None:
    settings = get_settings()
    worker = AttachmentParseWorker(
        settings,
        get_database_manager().session_factory,
        worker_id=f"attachment-worker-{slot}-{uuid4().hex}",
    )
    while True:
        worked = worker.run_once()
        if not worked and once:
            return
        if not worked:
            time.sleep(settings.excel.worker_poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 Excel 附件解析 Worker")
    parser.add_argument("--once", action="store_true", help="队列为空后退出")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings)
    AttachmentParseWorker(settings, get_database_manager().session_factory).recover_stale()
    with ThreadPoolExecutor(max_workers=settings.excel.worker_concurrency) as executor:
        futures = [
            executor.submit(_consume, slot, args.once)
            for slot in range(settings.excel.worker_concurrency)
        ]
        for future in futures:
            future.result()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
