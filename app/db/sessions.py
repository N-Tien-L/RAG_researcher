"""Database session management with async support."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Global async engine and session factory
engine: AsyncEngine | None = None
async_session_maker: async_sessionmaker[AsyncSession] | None = None


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