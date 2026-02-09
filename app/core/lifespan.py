"""Application lifespan management."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.cache.redis_cache import get_redis_client
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.sessions import engine, init_engine
from app.observability.tracing import configure_tracing, instrument_sqlalchemy, shutdown_tracing
from app.utils.files import ensure_directory

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    # -------------------------
    # Startup
    # -------------------------
    
    # Configure logging
    configure_logging(json_logs=False)  # Use colored console for development
    logger.info("Starting RAG Researcher API", version=settings.VERSION)

    if settings.ENABLE_TRACING:
        configure_tracing(
            service_name=settings.OTEL_SERVICE_NAME,
            jaeger_endpoint=settings.JAEGER_ENDPOINT,
            enable_console_export=settings.OTEL_EXPORTER_TYPE == "console",
            exporter_type=settings.OTEL_EXPORTER_TYPE,
            sample_rate=settings.OTEL_TRACE_SAMPLE_RATE,
        )
        logger.info(
            "Tracing enabled",
            exporter=settings.OTEL_EXPORTER_TYPE,
            sample_rate=settings.OTEL_TRACE_SAMPLE_RATE,
        )
    
    # Initialize database
    init_engine(
        settings.DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
    )
    logger.info("Database engine initialized", driver="asyncpg", backend="pgvector")

    if settings.ENABLE_TRACING and engine is not None:
        instrument_sqlalchemy(engine.sync_engine)
    
    # Initialize Redis cache
    if settings.REDIS_ENABLED:
        try:
            redis_client = await get_redis_client()
            await redis_client.connect()
            logger.info("Redis cache connected", url=settings.REDIS_CONNECTION_URL)
        except Exception as exc:
            logger.warning(
                "Redis cache unavailable – continuing without cache",
                error=str(exc),
            )
    
    # Ensure upload directory exists
    ensure_directory(str(settings.UPLOAD_DIR))
    logger.info("Upload directory ready", path=str(settings.UPLOAD_DIR))
    
    logger.info("✅ RAG Researcher API ready", api_prefix=settings.API_PREFIX)

    yield

    # -------------------------
    # Shutdown
    # -------------------------
    logger.info("Shutting down API")
    
    # Close Redis cache
    if settings.REDIS_ENABLED:
        try:
            redis_client = await get_redis_client()
            await redis_client.disconnect()
            logger.info("Redis cache disconnected")
        except Exception as exc:
            logger.error("Redis disconnect error", error=str(exc))
    
    # Close database engine
    if engine:
        await engine.dispose()
        logger.info("Database connections closed")

    if settings.ENABLE_TRACING:
        shutdown_tracing()
        logger.info("Tracing shutdown complete")
    
    logger.info("🛑 Shutdown complete")
