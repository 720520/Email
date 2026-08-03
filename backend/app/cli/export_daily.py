"""人工生成每日基金净值汇总：python -m app.cli.export_daily --date 2026-07-24。"""

from __future__ import annotations

import argparse
import json
from datetime import date

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_database_manager
from app.services.export_service import DailyExcelExportService


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成指定日期的基金净值与异常汇总 Excel")
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        help="业务日期，格式 YYYY-MM-DD；省略时使用归档时区的当天日期",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    settings = get_settings()
    configure_logging(settings)
    service = DailyExcelExportService(settings, get_database_manager().session_factory)
    result = service.export(args.date)
    print(
        json.dumps(
            {
                "report_date": result.report_date.isoformat(),
                "output_path": str(result.output_path),
                "nav_count": result.nav_count,
                "exception_count": result.exception_count,
                "job_run_id": result.job_run_id,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
