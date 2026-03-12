"""Observability middleware for HTTP metrics and distributed tracing.

Attaches an OpenTelemetry span to every request (``http.request``) and
records Prometheus metrics via :func:`~app.observability.metrics.record_http_request`.
The span trace/span IDs are propagated to response headers as
``X-Trace-ID`` and ``X-Span-ID`` so callers can correlate logs in Loki
and traces in Tempo.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import structlog
from opentelemetry.trace.status import Status, StatusCode

from app.core.config import settings
from app.core.logging import bind_trace_context
from app.observability.metrics import active_requests, record_http_request
from app.observability.tracing import get_tracer


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that adds distributed tracing and Prometheus metrics.

    For every HTTP request this middleware:

    1. Opens an OpenTelemetry span (``http.request``) with method, path, and
       request/user IDs as attributes.
    2. Increments the ``active_requests`` Prometheus gauge while processing.
    3. Calls :func:`~app.observability.metrics.record_http_request` in the
       ``finally`` block to record latency, method, path, and status code.
    4. Injects ``X-Trace-ID`` and ``X-Span-ID`` response headers for
       log-trace correlation (e.g. Grafana Loki + Tempo).
    5. Records the span status as ERROR and attaches the exception if an
       unhandled exception propagates.

    Metrics collection is gated by ``settings.ENABLE_METRICS`` so it can
    be disabled in test environments.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process one request: open span, record metrics, inject trace headers.

        Args:
            request: Incoming Starlette/FastAPI request.
            call_next: ASGI callable that forwards the request to the next
                middleware or route handler.

        Returns:
            Response: The downstream response with ``X-Trace-ID`` and
            ``X-Span-ID`` headers appended.

        Raises:
            Exception: Any unhandled exception from downstream is re-raised
                after being recorded on the active span.
        """
        tracer = get_tracer(__name__)
        method = request.method
        path = request.url.path
        start_time = time.perf_counter()
        status_code = 500

        if settings.ENABLE_METRICS:
            active_requests.inc()

        with tracer.start_as_current_span("http.request") as span:
            span.set_attribute("http.method", method)
            span.set_attribute("http.path", path)
            request_id = getattr(request.state, "request_id", None)
            if request_id:
                span.set_attribute("request_id", request_id)

            contextvars = structlog.contextvars.get_contextvars()
            user_id = contextvars.get("user_id")
            if user_id is not None:
                span.set_attribute("user_id", user_id)

            bind_trace_context()

            try:
                response = await call_next(request)
                status_code = response.status_code
                span.set_attribute("http.status_code", status_code)
                return response
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.set_attribute("http.status_code", status_code)
                raise
            finally:
                duration_seconds = time.perf_counter() - start_time
                if settings.ENABLE_METRICS:
                    record_http_request(method, path, status_code, duration_seconds)
                    active_requests.dec()

                span_ctx = span.get_span_context()
                if span_ctx and span_ctx.trace_id:
                    request.state.trace_id = format(span_ctx.trace_id, "032x")
                    request.state.span_id = format(span_ctx.span_id, "016x")

                if "response" in locals():
                    if span_ctx and span_ctx.trace_id:
                        response.headers["X-Trace-ID"] = format(
                            span_ctx.trace_id, "032x"
                        )
                        response.headers["X-Span-ID"] = format(
                            span_ctx.span_id, "016x"
                        )
