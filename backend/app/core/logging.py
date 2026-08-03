"""应用日志配置。"""

from __future__ import annotations

import json
import logging
import logging.config
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.context import request_id_context


class JsonFormatter(logging.Formatter):
    """输出便于检索的单行 JSON 日志。"""

    _standard_attributes = set(logging.makeLogRecord({}).__dict__)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_context.get(),
        }
        for key, value in record.__dict__.items():
            if key not in self._standard_attributes and key not in {"message", "asctime"}:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(settings: Settings) -> None:
    """配置控制台日志和按大小滚动的文件日志。"""

    log_directory: Path = settings.log_directory
    log_directory.mkdir(parents=True, exist_ok=True)
    log_file = log_directory / settings.logging.filename

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {"()": "app.core.logging.JsonFormatter"},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "json",
                "filename": str(log_file),
                "maxBytes": settings.logging.max_bytes,
                "backupCount": settings.logging.backup_count,
                "encoding": "utf-8",
            },
        },
        "root": {
            "level": settings.logging.level,
            "handlers": ["console", "file"],
        },
        "loggers": {
            "uvicorn.access": {"handlers": [], "propagate": True},
        },
    }
    logging.config.dictConfig(config)

