"""Rate limiting middleware using sliding window algorithm."""

import time
import threading
from typing import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import Settings
from app.services.exceptions import RateLimitExceeded
from app.utils.auth import TokenDecodeError, decode_access_token

logger = structlog.get_logger(__name__)


class RateLimiter:
    """Sliding window rate limiter with in-memory storage."""

    def __init__(self, limit: int, window_seconds: int, cleanup_interval: int):
        """Initialize rate limiter.

        Args:
            limit: Maximum requests allowed in window.
            window_seconds: Time window in seconds.
            cleanup_interval: Interval in seconds to clean up old entries.
        """
        self.limit = limit
        self.window_seconds = window_seconds
        self.cleanup_interval = cleanup_interval
        self._requests: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.time()

    def _cleanup_old_entries(self) -> None:
        """Remove timestamps older than the window.

        Should be called within a lock context.
        """
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds

        # Remove old timestamps for all users
        for user_id in list(self._requests.keys()):
            self._requests[user_id] = [
                ts for ts in self._requests[user_id] if ts > cutoff_time
            ]
            # Remove user entry if no timestamps remain
            if not self._requests[user_id]:
                del self._requests[user_id]

        self._last_cleanup = current_time

    def _get_user_requests(self, user_id: str) -> list[float]:
        """Get request timestamps for a user.

        Args:
            user_id: User identifier.

        Returns:
            List of request timestamps within the window.
        """
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds

        # Filter timestamps within the current window
        if user_id in self._requests:
            self._requests[user_id] = [
                ts for ts in self._requests[user_id] if ts > cutoff_time
            ]
            return self._requests[user_id]
        return []

    def _add_request(self, user_id: str, timestamp: float) -> None:
        """Add new request timestamp.

        Args:
            user_id: User identifier.
            timestamp: Request timestamp.
        """
        if user_id not in self._requests:
            self._requests[user_id] = []
        self._requests[user_id].append(timestamp)

    def check_rate_limit(self, user_id: str) -> tuple[bool, int, int]:
        """Check if request is allowed under rate limit.

        Args:
            user_id: User identifier.

        Returns:
            Tuple of (is_allowed, remaining, retry_after):
                - is_allowed: Whether the request is allowed.
                - remaining: Requests remaining in current window.
                - retry_after: Seconds to wait before retrying (if not allowed).
        """
        with self._lock:
            # Periodic cleanup
            current_time = time.time()
            if current_time - self._last_cleanup > self.cleanup_interval:
                self._cleanup_old_entries()

            # Get requests in current window
            user_requests = self._get_user_requests(user_id)
            request_count = len(user_requests)

            # Check if limit exceeded
            if request_count >= self.limit:
                # Calculate retry_after based on oldest request in window
                oldest_request = min(user_requests) if user_requests else current_time
                retry_after = int(self.window_seconds - (current_time - oldest_request)) + 1
                return False, 0, retry_after

            # Allow request and add timestamp
            self._add_request(user_id, current_time)
            remaining = self.limit - request_count - 1

            return True, remaining, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware for rate limiting requests."""

    # Endpoints that should not be rate limited
    WHITELISTED_PATHS = {
        "/health",
        "/docs",
        "/openapi.json",
        "/favicon.ico",
    }

    def __init__(self, app, settings: Settings):
        """Initialize rate limit middleware.

        Args:
            app: ASGI application.
            settings: Application settings.
        """
        super().__init__(app)
        self.settings = settings
        self.enabled = settings.RATE_LIMIT_ENABLED

        if self.enabled:
            self.rate_limiter = RateLimiter(
                limit=settings.RATE_LIMIT_PER_MINUTE,
                window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
                cleanup_interval=settings.RATE_LIMIT_CLEANUP_INTERVAL,
            )
            logger.info(
                "rate_limit_middleware_initialized",
                limit=settings.RATE_LIMIT_PER_MINUTE,
                window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
            )

    def _extract_user_identifier(self, request: Request) -> str:
        """Extract user identifier from JWT token or fall back to IP.

        Args:
            request: HTTP request.

        Returns:
            User identifier (user ID from JWT or IP address).
        """
        # Try to extract from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
            try:
                payload = decode_access_token(
                    token,
                    self.settings.SECRET_KEY,
                    self.settings.JWT_ALGORITHM,
                )
                user_id = payload.get("sub")
                if user_id:
                    return f"user:{user_id}"
            except TokenDecodeError:
                # Invalid token, fall back to IP
                pass

        # Fall back to client IP
        client_host = request.client.host if request.client else "unknown"
        return f"ip:{client_host}"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting.

        Args:
            request: HTTP request.
            call_next: Next middleware/handler.

        Returns:
            HTTP response with rate limit headers.
        """
        # Skip if rate limiting is disabled
        if not self.enabled:
            return await call_next(request)

        # Skip rate limiting for whitelisted paths
        if request.url.path in self.WHITELISTED_PATHS:
            return await call_next(request)

        # Extract user identifier
        user_id = self._extract_user_identifier(request)

        # Check rate limit
        is_allowed, remaining, retry_after = self.rate_limiter.check_rate_limit(user_id)

        if not is_allowed:
            # Log rate limit violation
            logger.warning(
                "rate_limit_exceeded",
                user_id=user_id,
                limit=self.settings.RATE_LIMIT_PER_MINUTE,
                retry_after=retry_after,
                path=request.url.path,
            )

            # Raise exception to be handled by exception handler
            raise RateLimitExceeded(
                message=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                retry_after=retry_after,
                limit=self.settings.RATE_LIMIT_PER_MINUTE,
                remaining=0,
            )

        # Log successful rate limit check
        logger.debug(
            "rate_limit_check_passed",
            user_id=user_id,
            remaining=remaining,
            path=request.url.path,
        )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to response
        response.headers["X-RateLimit-Limit"] = str(self.settings.RATE_LIMIT_PER_MINUTE)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        reset_time = int(time.time() + self.rate_limiter.window_seconds)
        response.headers["X-RateLimit-Reset"] = str(reset_time)

        return response
