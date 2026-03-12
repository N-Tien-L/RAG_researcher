"""Prometheus metrics definitions and helpers."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from app.core.config import settings

_REGISTRY = CollectorRegistry()

# -------------------------
# Counters
# -------------------------
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",  # labels: method, path, status_code
    ["method", "path", "status_code"],
    registry=_REGISTRY,
)

rag_queries_total = Counter(
    "rag_queries_total",
    "Total RAG queries",  # labels: collection_name, status (success/failure)
    ["collection_name", "status"],
    registry=_REGISTRY,
)

ingestion_jobs_total = Counter(
    "ingestion_jobs_total",
    "Total ingestion jobs",  # labels: source_type (pdf/youtube), status (success/skipped/failure)
    ["source_type", "status"],
    registry=_REGISTRY,
)

cache_operations_total = Counter(
    "cache_operations_total",
    "Total cache operations",  # labels: operation (get/set), cache_type (embedding/llm), result (hit/miss)
    ["operation", "cache_type", "result"],
    registry=_REGISTRY,
)

database_queries_total = Counter(
    "database_queries_total",
    "Total database queries",  # labels: operation (SELECT/INSERT/UPDATE/DELETE), table
    ["operation", "table"],
    registry=_REGISTRY,
)

# -------------------------
# Histograms
# -------------------------
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    registry=_REGISTRY,
)

rag_query_duration_seconds = Histogram(
    "rag_query_duration_seconds",
    "End-to-end RAG query duration in seconds",
    ["collection_name"],
    registry=_REGISTRY,
)

rag_retrieval_duration_seconds = Histogram(
    "rag_retrieval_duration_seconds",
    "RAG retrieval duration in seconds",
    ["collection_name"],
    registry=_REGISTRY,
)

rag_generation_duration_seconds = Histogram(
    "rag_generation_duration_seconds",
    "RAG generation duration in seconds",
    ["model"],
    registry=_REGISTRY,
)

embedding_generation_duration_seconds = Histogram(
    "embedding_generation_duration_seconds",
    "Embedding generation duration in seconds",
    ["provider", "mode"],
    registry=_REGISTRY,
)

database_query_duration_seconds = Histogram(
    "database_query_duration_seconds",
    "Database query duration in seconds",
    ["operation", "table"],
    registry=_REGISTRY,
)

cache_operation_duration_seconds = Histogram(
    "cache_operation_duration_seconds",
    "Cache operation duration in seconds",
    ["operation", "cache_type"],
    registry=_REGISTRY,
)

# -------------------------
# Gauges
# -------------------------
active_requests = Gauge(
    "active_requests",
    "Current in-flight HTTP requests",
    registry=_REGISTRY,
)

database_pool_size = Gauge(
    "database_pool_size",
    "Configured database connection pool size",
    registry=_REGISTRY,
)

database_pool_checked_out = Gauge(
    "database_pool_checked_out",
    "Database connections currently checked out",
    registry=_REGISTRY,
)


def get_metrics_registry() -> CollectorRegistry:
    """Return the Prometheus registry used by the application.

    Returns:
        CollectorRegistry: Prometheus registry instance.
    """
    return _REGISTRY


def _metrics_enabled() -> bool:
    """Return ``True`` if Prometheus metrics collection is active.

    Gates all ``record_*`` helper functions so that metrics are silently
    skipped when ``settings.ENABLE_METRICS`` is ``False`` (e.g. in tests
    or lightweight deployments).

    Returns:
        bool: Value of ``settings.ENABLE_METRICS``.
    """
    return settings.ENABLE_METRICS


def record_http_request(
    method: str,
    path: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """Record HTTP request metrics.

    Args:
        method: HTTP method.
        path: Request path.
        status_code: HTTP response status code.
        duration_seconds: Duration in seconds.
    """
    if not _metrics_enabled():
        return
    http_requests_total.labels(
        method=method,
        path=path,
        status_code=str(status_code),
    ).inc()
    http_request_duration_seconds.labels(method=method, path=path).observe(
        duration_seconds
    )


def record_rag_query(
    collection: str,
    duration_seconds: float,
    retrieval_seconds: float,
    generation_seconds: float,
    status: str,
) -> None:
    """Record RAG query metrics.

    Args:
        collection: Collection name.
        duration_seconds: End-to-end duration in seconds.
        retrieval_seconds: Retrieval duration in seconds.
        generation_seconds: Generation duration in seconds.
        status: Status label (success/failure).
    """
    if not _metrics_enabled():
        return
    rag_queries_total.labels(collection_name=collection, status=status).inc()
    rag_query_duration_seconds.labels(collection_name=collection).observe(
        duration_seconds
    )
    rag_retrieval_duration_seconds.labels(collection_name=collection).observe(
        retrieval_seconds
    )
    rag_generation_duration_seconds.labels(model=settings.OLLAMA_MODEL).observe(
        generation_seconds
    )


def record_ingestion_job(
    source_type: str,
    status: str,
    duration_seconds: float,
    chunks_count: int,
) -> None:
    """Record ingestion job metrics.

    Args:
        source_type: Source type (pdf/youtube).
        status: Status label (success/failure/skipped).
        duration_seconds: End-to-end duration in seconds.
        chunks_count: Number of chunks processed.
    """
    if not _metrics_enabled():
        return
    _ = chunks_count
    ingestion_jobs_total.labels(source_type=source_type, status=status).inc()


def record_embedding(
    provider: str,
    mode: str,
    duration_seconds: float,
    batch_size: int,
) -> None:
    """Record embedding generation metrics.

    Args:
        provider: Embedding provider name.
        mode: Embedding mode (query/passage).
        duration_seconds: Duration in seconds.
        batch_size: Size of the embedding batch.
    """
    if not _metrics_enabled():
        return
    _ = batch_size
    embedding_generation_duration_seconds.labels(provider=provider, mode=mode).observe(
        duration_seconds
    )


def record_cache_operation(
    operation: str,
    cache_type: str,
    duration_seconds: float,
    hit: bool,
) -> None:
    """Record cache operation metrics.

    Args:
        operation: Cache operation type.
        cache_type: Cache type name.
        duration_seconds: Duration in seconds.
        hit: Whether the operation was a cache hit.
    """
    if not _metrics_enabled():
        return
    result = "hit" if hit else "miss"
    cache_operations_total.labels(
        operation=operation,
        cache_type=cache_type,
        result=result,
    ).inc()
    cache_operation_duration_seconds.labels(
        operation=operation,
        cache_type=cache_type,
    ).observe(duration_seconds)


def record_database_query(operation: str, table: str, duration_seconds: float) -> None:
    """Record database query metrics.

    Args:
        operation: SQL operation (SELECT/INSERT/UPDATE/DELETE).
        table: Table name.
        duration_seconds: Duration in seconds.
    """
    if not _metrics_enabled():
        return
    database_queries_total.labels(operation=operation, table=table).inc()
    database_query_duration_seconds.labels(operation=operation, table=table).observe(
        duration_seconds
    )


def set_database_pool_metrics(pool_size: int, checked_out: int) -> None:
    """Update database connection pool gauges.

    Args:
        pool_size: Total pool size.
        checked_out: Current checked out connections.
    """
    if not _metrics_enabled():
        return
    database_pool_size.set(pool_size)
    database_pool_checked_out.set(checked_out)
