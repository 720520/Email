"""数据库引擎与会话生命周期。"""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


class DatabaseManager:
    """集中管理 SQLAlchemy 引擎和会话工厂。"""

    def __init__(self, url: str, *, echo: bool = False) -> None:
        connect_args = (
            {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
        )
        self.engine: Engine = create_engine(
            url,
            echo=echo,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            autoflush=False,
            expire_on_commit=False,
        )
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", self._configure_sqlite)

    @staticmethod
    def _configure_sqlite(dbapi_connection: object, connection_record: object) -> None:
        """启用外键约束、WAL 和忙等待，提升本地运行可靠性。"""

        del connection_record
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
        finally:
            cursor.close()

    def check_connection(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def dispose(self) -> None:
        self.engine.dispose()


@lru_cache(maxsize=1)
def get_database_manager() -> DatabaseManager:
    settings = get_settings()
    return DatabaseManager(settings.database_url, echo=settings.database.echo)


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI 数据库依赖：异常时回滚，始终关闭会话。"""

    session = get_database_manager().session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
