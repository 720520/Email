"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.db.session import get_database_manager

logger = logging.getLogger(__name__)


def _lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        del app
        settings.data_directory.mkdir(parents=True, exist_ok=True)
        settings.log_directory.mkdir(parents=True, exist_ok=True)
        database = get_database_manager()
        database.check_connection()
        logger.info(
            "后端服务启动完成",
            extra={"environment": settings.app.environment, "version": __version__},
        )
        try:
            yield
        finally:
            database.dispose()
            logger.info("后端服务已停止")

    return lifespan


def create_app() -> FastAPI:
    """应用工厂，便于测试与未来多部署环境复用。"""

    settings = get_settings()
    configure_logging(settings)

    application = FastAPI(
        title=settings.app.name,
        version=__version__,
        debug=settings.app.debug,
        lifespan=_lifespan(settings),
    )
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    register_exception_handlers(application)
    application.include_router(api_router, prefix=settings.app.api_prefix)
    return application


app = create_app()

