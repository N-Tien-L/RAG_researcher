"""Structured logging configuration using structlog."""

import logging
import sys
from typing import Any

import structlog
from opentelemetry import trace
from structlog.typing import EventDict


def add_app_context(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add application context to log entries."""
    event_dict["app"] = "rag_researcher"
    return event_dict


def add_trace_context(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add OpenTelemetry trace context to log entries."""
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
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
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
    """Bind trace context into structlog contextvars."""
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
    """Log retrieval operation metrics."""
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
    """Log generation operation metrics."""
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
