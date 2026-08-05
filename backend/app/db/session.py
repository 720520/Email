"""数据库引擎与会话生命周期。"""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker, with_loader_criteria
from sqlalchemy.sql import visitors

from app.core.config import get_settings
from app.db.models.mixins import MailboxOwnedMixin, TenantOwnedMixin


class TenantScopeViolationError(RuntimeError):
    pass


class TenantScopeRequiredError(RuntimeError):
    """业务数据访问没有显式租户上下文时，采用默认拒绝策略。"""


@event.listens_for(Session, "do_orm_execute")
def _apply_tenant_scope(execute_state) -> None:
    """对作用域会话的全部 ORM SELECT 自动注入租户和邮箱条件。"""

    if not execute_state.is_select:
        return
    session = execute_state.session
    if session.info.get("skip_tenant_scope") or execute_state.execution_options.get(
        "skip_tenant_scope"
    ):
        return
    tenant_id = session.info.get("tenant_id")
    if tenant_id is None:
        if _statement_uses_tenant_data(execute_state.statement):
            raise TenantScopeRequiredError("访问业务数据前必须配置租户作用域")
        return
    mailbox_ids = tuple(session.info.get("mailbox_ids", ()))
    criteria = [
        with_loader_criteria(
            TenantOwnedMixin,
            lambda model: model.tenant_id == tenant_id,
            include_aliases=True,
        )
    ]
    if not execute_state.execution_options.get("skip_mailbox_scope"):
        criteria.append(
            with_loader_criteria(
                MailboxOwnedMixin,
                lambda model: model.mailbox_account_id.in_(mailbox_ids),
                include_aliases=True,
            )
        )
    execute_state.statement = execute_state.statement.options(
        *criteria,
    )


@event.listens_for(Session, "before_flush")
def _validate_tenant_scope(session: Session, flush_context, instances) -> None:
    del flush_context, instances
    if session.info.get("skip_tenant_scope"):
        return
    tenant_id = session.info.get("tenant_id")
    scoped_items = [
        item
        for item in session.new.union(session.dirty).union(session.deleted)
        if isinstance(item, TenantOwnedMixin)
    ]
    if tenant_id is None:
        if scoped_items:
            raise TenantScopeRequiredError("写入业务数据前必须配置租户作用域")
        return
    mailbox_ids = set(session.info.get("mailbox_ids", ()))
    for item in scoped_items:
        if isinstance(item, TenantOwnedMixin):
            current_tenant_id = getattr(item, "tenant_id", None)
            if current_tenant_id is None:
                item.tenant_id = tenant_id
            elif current_tenant_id != tenant_id:
                raise TenantScopeViolationError("禁止写入其他租户的数据")
        if isinstance(item, MailboxOwnedMixin):
            mailbox_id = getattr(item, "mailbox_account_id", None)
            if mailbox_id is None and len(mailbox_ids) == 1:
                item.mailbox_account_id = next(iter(mailbox_ids))
            elif mailbox_id not in mailbox_ids:
                raise TenantScopeViolationError("禁止写入未授权邮箱的数据")


def _statement_uses_tenant_data(statement) -> bool:
    """识别 ORM 查询涉及的租户模型；阻断遗漏作用域的服务端代码路径。"""

    for description in getattr(statement, "column_descriptions", ()):
        entity = description.get("entity")
        try:
            entity_type = entity if isinstance(entity, type) else entity.mapper.class_
        except (AttributeError, TypeError):
            continue
        try:
            if issubclass(entity_type, TenantOwnedMixin):
                return True
        except TypeError:
            continue
    protected_tables = {
        model.__table__
        for model in _tenant_owned_types(TenantOwnedMixin)
        if hasattr(model, "__table__")
    }
    if any(item in protected_tables for item in visitors.iterate(statement)):
        return True
    return False


def _tenant_owned_types(base: type) -> set[type]:
    descendants: set[type] = set()
    for child in base.__subclasses__():
        descendants.add(child)
        descendants.update(_tenant_owned_types(child))
    return descendants


def configure_tenant_scope(
    session: Session,
    *,
    tenant_id: int,
    mailbox_ids: tuple[int, ...],
) -> Session:
    session.info["tenant_id"] = tenant_id
    session.info["mailbox_ids"] = tuple(sorted(set(mailbox_ids)))
    return session


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
