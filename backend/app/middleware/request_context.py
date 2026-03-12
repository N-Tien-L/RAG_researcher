"""Request context middleware for per-request ID generation and structlog binding.

Generates a UUID4 ``request_id`` for every incoming request, stores it on
``request.state``, binds it to structlog context vars so it appears in
every log entry for the duration of the request, and returns it to the
caller in the ``X-Request-ID`` response header.
"""
import uuid

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class RequestContextMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that generates a per-request UUID and binds it to structlog.

    The ``request_id`` is stored on ``request.state.request_id`` so it can
    be read by downstream middleware (e.g. ``ObservabilityMiddleware``) and
    service-layer helpers like :func:`~app.services.exceptions.get_request_context_data`.

    The ID is returned to callers via the ``X-Request-ID`` response header
    and cleared from structlog context vars in a ``finally`` block to
    prevent leaking between requests on the same event-loop worker.
    """

    async def dispatch(self, request: Request, call_next):
        """Assign ``request_id``, bind to structlog, forward request, inject header.

        Args:
            request: Incoming Starlette/FastAPI request.
            call_next: ASGI callable that forwards the request downstream.

        Returns:
            Response: Downstream response with ``X-Request-ID`` header set
            to the generated UUID.
        """
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        structlog.contextvars.bind_contextvars(request_id=request_id)

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()
