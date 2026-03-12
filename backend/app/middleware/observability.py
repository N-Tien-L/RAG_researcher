"""Observability middleware for metrics and tracing."""

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
    """Attach metrics and tracing to incoming requests."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
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
