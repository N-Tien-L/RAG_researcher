"""Service-layer exception hierarchy for the RAG Researcher backend.

All domain errors ultimately derive from :class:`BaseApplicationError`, which
captures request context (``request_id``, ``user_id``) from structlog
context vars at construction time so that errors logged at any layer carry
full traceability information.

Hierarchy::

    Exception
    ├── ServiceError              # CRUD-level errors (not-found, conflict)
    │   ├── ResourceNotFound
    │   └── ResourceConflict
    ├── AuthenticationError        # Invalid credentials / expired token
    ├── RateLimitExceeded          # In-memory sliding-window limit breached
    └── BaseApplicationError       # Pipeline errors with error_code + context
        ├── IngestionError           # INGESTION_{STAGE}
        ├── EmbeddingError           # EMBEDDING_GENERATION_FAILED
        ├── VectorStoreError         # VECTORSTORE_{OPERATION}
        └── LLMError                 # LLM_GENERATION_FAILED
"""
from datetime import datetime
from typing import Any

import structlog


class ServiceError(Exception):
    """Base exception for service-layer CRUD failures.

    Raised by service methods (``UserService``, ``ChatService``, etc.) to
    signal domain-level errors that are unrelated to the RAG/ingestion
    pipeline.
    """


class ResourceNotFound(ServiceError):
    """Raised when a requested resource does not exist in the database.

    Maps to HTTP 404 in route handlers.
    """


class ResourceConflict(ServiceError):
    """Raised when a unique-constraint violation or logical conflict occurs.

    Maps to HTTP 409 in route handlers (e.g. duplicate email on registration).
    """


class AuthenticationError(Exception):
    """Raised by ``AuthService`` when credentials are invalid or the token
    cannot be decoded / has expired.

    Maps to HTTP 401 in route handlers via ``deps.current_user``.
    """


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded."""
    
    def __init__(self, message: str, retry_after: int = 60, limit: int = 60, remaining: int = 0):
        """Initialize rate limit exception.
        
        Args:
            message: Error message.
            retry_after: Seconds to wait before retrying.
            limit: Maximum requests allowed in window.
            remaining: Requests remaining in current window.
        """
        super().__init__(message)
        self.retry_after = retry_after
        self.limit = limit
        self.remaining = remaining


class BaseApplicationError(Exception):
    """Base exception for pipeline errors that require error codes and context.

    Automatically pulls ``request_id`` and ``user_id`` from structlog
    context vars (populated by ``RequestContextMiddleware``) so that every
    raised error is traceable back to the originating HTTP request.
    """

    def __init__(
        self,
        message: str,
        error_code: str,
        details: dict | None = None,
        request_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        if request_id is None or user_id is None:
            context = get_request_context_data()
            request_id = request_id or context.get("request_id")
            user_id = user_id or context.get("user_id")
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.request_id = request_id
        self.user_id = user_id
        self.timestamp = datetime.utcnow()


def get_request_context_data(request: Any | None = None) -> dict[str, str | None]:
    """Fetch request/user context from structlog contextvars or request state."""
    context = structlog.contextvars.get_contextvars()
    request_id = context.get("request_id")
    user_id = context.get("user_id")

    if request is not None:
        request_id = getattr(request.state, "request_id", request_id)
        user_id = getattr(request.state, "user_id", user_id)

    return {"request_id": request_id, "user_id": user_id}


class IngestionError(BaseApplicationError):
    """Raised when any stage of the ingestion pipeline fails.

    The ``error_code`` is set to ``INGESTION_{stage.upper()}`` so callers
    can distinguish extraction failures from chunking failures.
    """

    def __init__(
        self,
        message: str,
        stage: str,
        source_id: str | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(
            message=message,
            error_code=f"INGESTION_{stage.upper()}",
            details={"stage": stage, "source_id": source_id},
            **kwargs,
        )


class EmbeddingError(BaseApplicationError):
    """Raised when the TEI embedding service fails or returns unexpected data.

    ``error_code`` is always ``EMBEDDING_GENERATION_FAILED``.
    """

    def __init__(self, message: str, provider: str = "tei", **kwargs: object) -> None:
        super().__init__(
            message=message,
            error_code="EMBEDDING_GENERATION_FAILED",
            details={"provider": provider},
            **kwargs,
        )


class VectorStoreError(BaseApplicationError):
    """Raised when a pgvector database operation fails.

    The ``error_code`` is set to ``VECTORSTORE_{operation.upper()}`` to
    differentiate INSERT, QUERY, and DELETE failures.
    """

    def __init__(self, message: str, operation: str, **kwargs: object) -> None:
        super().__init__(
            message=message,
            error_code=f"VECTORSTORE_{operation.upper()}",
            details={"operation": operation},
            **kwargs,
        )


class LLMError(BaseApplicationError):
    """Raised when the LLM fails to generate a response or times out.

    ``error_code`` is always ``LLM_GENERATION_FAILED``.
    """

    def __init__(self, message: str, model: str | None = None, **kwargs: object) -> None:
        super().__init__(
            message=message,
            error_code="LLM_GENERATION_FAILED",
            details={"model": model},
            **kwargs,
        )