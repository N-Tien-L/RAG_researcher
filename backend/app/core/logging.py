"""Structured logging configuration using structlog."""

import logging
import sys
from typing import Any

import structlog
from opentelemetry import trace
from structlog.typing import EventDict

from app.core.config import settings


def add_app_context(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Structlog processor that injects the application name into every log entry.

    Args:
        logger: The underlying logger instance (unused).
        method_name: Log method name such as ``info`` or ``error`` (unused).
        event_dict: Mutable structlog event dictionary.

    Returns:
        EventDict: The event dictionary with ``app`` set to ``'rag_researcher'``.
    """
    event_dict["app"] = "rag_researcher"
    return event_dict


def add_trace_context(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Structlog processor that injects the active OpenTelemetry trace context.

    Reads the current span from the OpenTelemetry context.  If a recording
    span is active, its ``trace_id`` and ``span_id`` are added to the event
    dictionary as 32- and 16-character hex strings respectively.

    Args:
        logger: The underlying logger instance (unused).
        method_name: Log method name (unused).
        event_dict: Mutable structlog event dictionary.

    Returns:
        EventDict: Event dictionary optionally enriched with ``trace_id`` and
            ``span_id`` keys.
    """
    span = trace.get_current_span()
    if span.is_recording():
        ctx = span.get_span_context()
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


def configure_logging(level: int = logging.INFO, json_logs: bool = True) -> None:
    """Configure structured logging with structlog.
    
    Args:
        level: Logging level.
        json_logs: If True, output JSON format. If False, use colored console output.
    """
    # Configure standard logging handlers
    handlers: list[logging.Handler] = []
    
    # Console handler (always enabled)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    handlers.append(console_handler)
    
    # Loki handler (optional)
    if settings.LOKI_ENABLED:
        try:
            from logging_loki import LokiHandler
            
            loki_handler = LokiHandler(
                url=f"{settings.LOKI_ENDPOINT}/loki/api/v1/push",
                tags={"service": "rag-researcher"},
                version="1",
            )
            loki_handler.setLevel(level)
            handlers.append(loki_handler)
        except ImportError:
            # Log warning if logging_loki is not installed
            logging.warning(
                "Loki logging enabled but python-logging-loki not installed. "
                "Install with: pip install python-logging-loki"
            )
    
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        handlers=handlers,
        level=level,
    )

    # Structlog processors
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        add_app_context,
        add_trace_context,
    ]

    if json_logs:
        # Production: JSON output
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Development: Colored console output
        processors.extend([
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=True),
        ])

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance.
    
    Args:
        name: Logger name (usually __name__).
        
    Returns:
        Structured logger with bound context.
    """
    return structlog.get_logger(name)


def bind_trace_context() -> None:
    """Bind the active OpenTelemetry trace context into structlog contextvars.

    Reads ``trace_id`` and ``span_id`` from the current span and binds them
    so that all subsequent log calls in the same async context automatically
    include them.  No-op when no recording span is active.
    """
    span = trace.get_current_span()
    if not span.is_recording():
        return
    ctx = span.get_span_context()
    structlog.contextvars.bind_contextvars(
        trace_id=format(ctx.trace_id, "032x"),
        span_id=format(ctx.span_id, "016x"),
    )


# RAG-specific logging helpers
def log_retrieval(
    logger: structlog.stdlib.BoundLogger,
    query: str,
    num_chunks: int,
    top_score: float | None,
    retrieval_time_ms: float,
) -> None:
    """Log vector retrieval operation metrics at INFO level.

    Args:
        logger: Bound structlog logger from the calling module.
        query: User query string (truncated to 100 chars for log size).
        num_chunks: Number of chunks returned by the retrieval.
        top_score: Similarity score of the best chunk, or ``None`` if empty.
        retrieval_time_ms: Total retrieval duration in milliseconds.
    """
    logger.info(
        "retrieval_completed",
        query=query[:100],  # Truncate for log size
        num_chunks=num_chunks,
        top_score=top_score,
        retrieval_time_ms=retrieval_time_ms,
    )


def log_generation(
    logger: structlog.stdlib.BoundLogger,
    query: str,
    response_length: int,
    tokens_used: int | None,
    generation_time_ms: float,
) -> None:
    """Log LLM generation operation metrics at INFO level.

    Args:
        logger: Bound structlog logger from the calling module.
        query: User query string (truncated to 100 chars for log size).
        response_length: Character length of the generated answer.
        tokens_used: Token count reported by the LLM, or ``None`` if unavailable.
        generation_time_ms: LLM generation duration in milliseconds.
    """
    logger.info(
        "generation_completed",
        query=query[:100],
        response_length=response_length,
        tokens_used=tokens_used,
        generation_time_ms=generation_time_ms,
    )


def log_cache_operation(
    logger: structlog.stdlib.BoundLogger,
    operation: str,
    cache_type: str,
    key_hash: str,
    execution_time_ms: float,
) -> None:
    """Log cache operation metrics.

    Args:
        logger: Structured logger instance.
        operation: Cache operation type (hit/miss/set).
        cache_type: Type of cached data (embedding/llm).
        key_hash: Hash of the cache key.
        execution_time_ms: Time taken for the operation in milliseconds.
    """
    logger.info(
        "cache_operation",
        operation=operation,
        cache_type=cache_type,
        key_hash=key_hash[:16],
        execution_time_ms=round(execution_time_ms, 2),
    )
