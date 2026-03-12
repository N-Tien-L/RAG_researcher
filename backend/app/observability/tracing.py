"""OpenTelemetry tracing configuration and helpers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from functools import wraps
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

_tracing_configured = False


def configure_tracing(
    service_name: str,
    otlp_endpoint: str,
    enable_console_export: bool,
    *,
    exporter_type: str = "otlp",
    sample_rate: float = 1.0,
) -> None:
    """Configure OpenTelemetry tracing.

    Args:
        service_name: Service name for tracing.
        otlp_endpoint: OTLP collector endpoint (gRPC).
        enable_console_export: Enable console span export.
        exporter_type: Exporter type (otlp/console).
        sample_rate: Trace sample rate (0.0-1.0).
        
    Raises:
        ValueError: If exporter_type is not supported.
    """
    global _tracing_configured
    if _tracing_configured:
        return

    resource = Resource.create({"service.name": service_name})
    tracer_provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(sample_rate)),
    )

    if exporter_type == "otlp":
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
    elif exporter_type == "console":
        tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        raise ValueError(
            f"Unsupported exporter_type: {exporter_type}. "
            f"Supported types: 'otlp', 'console'"
        )

    if enable_console_export and exporter_type != "console":
        tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(tracer_provider)
    _tracing_configured = True


def instrument_fastapi(app: Any) -> None:
    """Enable FastAPI auto-instrumentation.

    Args:
        app: FastAPI application instance.
    """
    FastAPIInstrumentor.instrument_app(app)


def instrument_sqlalchemy(engine: Any) -> None:
    """Enable SQLAlchemy auto-instrumentation.

    Args:
        engine: SQLAlchemy engine instance.
    """
    SQLAlchemyInstrumentor().instrument(engine=engine)


def shutdown_tracing() -> None:
    """Flush and shutdown tracing provider."""
    provider = trace.get_tracer_provider()
    if hasattr(provider, "shutdown"):
        provider.shutdown()


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer instance for a module.

    Args:
        name: Module name.

    Returns:
        Tracer instance.
    """
    return trace.get_tracer(name)


def trace_async_function(
    span_name: str,
    attributes: dict[str, Any] | None = None,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Decorator to trace async functions.

    Args:
        span_name: Span name.
        attributes: Span attributes.

    Returns:
        Decorated async function.
    """
    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer(func.__module__)
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)
                return await func(*args, **kwargs)

        return wrapper

    return decorator


@contextmanager
def trace_context_manager(
    span_name: str,
    attributes: dict[str, Any] | None = None,
) -> Any:
    """Context manager for manual spans.

    Args:
        span_name: Span name.
        attributes: Span attributes.

    Yields:
        Current span.
    """
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span(span_name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        yield span


def add_span_attributes(**kwargs: Any) -> None:
    """Add attributes to the current span."""
    span = trace.get_current_span()
    if not span.is_recording():
        return
    for key, value in kwargs.items():
        span.set_attribute(key, value)


def add_span_event(name: str, attributes: dict[str, Any] | None = None) -> None:
    """Add an event to the current span.

    Args:
        name: Event name.
        attributes: Event attributes.
    """
    span = trace.get_current_span()
    if not span.is_recording():
        return
    span.add_event(name, attributes=attributes or {})


def get_current_trace_id() -> str | None:
    """Get the current trace ID for log correlation.

    Returns:
        Trace ID hex string if present.
    """
    span = trace.get_current_span()
    if not span.is_recording():
        return None
    ctx = span.get_span_context()
    if not ctx or not ctx.trace_id:
        return None
    return format(ctx.trace_id, "032x")
