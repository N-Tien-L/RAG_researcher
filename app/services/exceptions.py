from datetime import datetime
from typing import Any

import structlog


class ResourceNotFound(Exception):
    pass

class ResourceConflict(Exception):
    pass


class AuthenticationError(Exception):
    pass


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
    """Base exception with request context tracking."""

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
    """Raised when ingestion pipeline fails."""

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
    """Raised when embedding generation fails."""

    def __init__(self, message: str, provider: str = "tei", **kwargs: object) -> None:
        super().__init__(
            message=message,
            error_code="EMBEDDING_GENERATION_FAILED",
            details={"provider": provider},
            **kwargs,
        )


class VectorStoreError(BaseApplicationError):
    """Raised when vector store operations fail."""

    def __init__(self, message: str, operation: str, **kwargs: object) -> None:
        super().__init__(
            message=message,
            error_code=f"VECTORSTORE_{operation.upper()}",
            details={"operation": operation},
            **kwargs,
        )


class LLMError(BaseApplicationError):
    """Raised when LLM generation fails."""

    def __init__(self, message: str, model: str | None = None, **kwargs: object) -> None:
        super().__init__(
            message=message,
            error_code="LLM_GENERATION_FAILED",
            details={"model": model},
            **kwargs,
        )