"""Database session management with async support."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import re
import time

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import get_logger
from app.observability.metrics import record_database_query, set_database_pool_metrics

logger = get_logger(__name__)

# Global async engine and session factory
engine: AsyncEngine | None = None
async_session_maker: async_sessionmaker[AsyncSession] | None = None


def _extract_operation(statement: str) -> str:
    match = re.match(r"^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)", statement, re.I)
    if match:
        return match.group(1).upper()
    return "UNKNOWN"


def _extract_table(statement: str, operation: str) -> str:
    if operation == "SELECT" or operation == "DELETE":
        pattern = r"\bFROM\s+([\w\"\.]+)"
    elif operation == "INSERT":
        pattern = r"\bINTO\s+([\w\"\.]+)"
    elif operation == "UPDATE":
        pattern = r"\bUPDATE\s+([\w\"\.]+)"
    else:
        return "unknown"

    match = re.search(pattern, statement, re.I)
    if not match:
        return "unknown"
    return match.group(1).strip('"')


def _register_query_metrics(sync_engine: Engine) -> None:
    @event.listens_for(sync_engine, "before_cursor_execute")
    def before_cursor_execute(
        conn: Engine,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        setattr(context, "_query_start_time", time.perf_counter())

    @event.listens_for(sync_engine, "after_cursor_execute")
    def after_cursor_execute(
        conn: Engine,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        start_time = getattr(context, "_query_start_time", None)
        if start_time is None:
            return
        duration_seconds = time.perf_counter() - start_time
        operation = _extract_operation(statement)
        table = _extract_table(statement, operation)
        record_database_query(operation, table, duration_seconds)

        duration_ms = duration_seconds * 1000
        if duration_ms >= settings.METRICS_SLOW_QUERY_THRESHOLD_MS:
            logger.warning(
                "Slow query detected",
                operation=operation,
                table=table,
                duration_ms=round(duration_ms, 2),
            )

        try:
            pool = sync_engine.pool
            set_database_pool_metrics(pool.size(), pool.checkedout())
        except Exception:
            return


def init_engine(database_url: str, pool_size: int = 20, max_overflow: int = 10) -> None:
    """Initialize async database engine and session factory.
    
    Args:
        database_url: Database connection URL (must use asyncpg driver).
        pool_size: Connection pool size.
        max_overflow: Maximum overflow connections.
    """
    global engine, async_session_maker

    engine = create_async_engine(
        database_url,
        echo=False,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        pool_recycle=3600,  # Recycle connections after 1 hour
    )
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    _register_query_metrics(engine.sync_engine)
    try:
        set_database_pool_metrics(engine.sync_engine.pool.size(), 0)
    except Exception:
        return


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide async database session per request.
    
    Yields:
        AsyncSession instance.
    """
    if async_session_maker is None:
        raise RuntimeError("Database engine is not initialized. Call init_engine() first.")
    
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()