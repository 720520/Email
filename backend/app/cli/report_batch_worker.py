"""独立批量报表 Worker：python -m app.cli.report_batch_worker。"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_database_manager
from app.services.report_batch_worker import ReportBatchWorker


def _consume(slot: int, once: bool) -> None:
    settings = get_settings()
    worker = ReportBatchWorker(
        get_database_manager().session_factory,
        worker_id=f"batch-worker-{slot}",
    )
    while True:
        worked = worker.run_once()
        if not worked and once:
            return
        if not worked:
            time.sleep(settings.reports.worker_poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="运行批量报表 Worker")
    parser.add_argument("--once", action="store_true", help="队列为空后退出")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings)
    ReportBatchWorker(get_database_manager().session_factory).recover_stale(
        settings.reports.worker_stale_minutes
    )
    with ThreadPoolExecutor(max_workers=settings.reports.worker_concurrency) as executor:
        futures = [
            executor.submit(_consume, slot, args.once)
            for slot in range(settings.reports.worker_concurrency)
        ]
        for future in futures:
            future.result()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
