"""存活与就绪检查。"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.core.errors import AppError
from app.db.session import get_database_manager

router = APIRouter()


class LiveResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str


class ReadyResponse(BaseModel):
    status: Literal["ready"] = "ready"
    database: Literal["ok"] = "ok"


@router.get("/live", response_model=LiveResponse, summary="存活检查")
def live() -> LiveResponse:
    """仅确认 Web 进程能够响应。"""

    return LiveResponse(version=__version__)


@router.get("/ready", response_model=ReadyResponse, summary="就绪检查")
def ready() -> ReadyResponse:
    """确认数据库等关键依赖可用。"""

    try:
        get_database_manager().check_connection()
    except SQLAlchemyError as exc:
        raise AppError(
            "DATABASE_UNAVAILABLE",
            "数据库连接不可用",
            status_code=503,
        ) from exc
    return ReadyResponse()

