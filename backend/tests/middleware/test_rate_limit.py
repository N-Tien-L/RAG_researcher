"""Tests for rate limiting middleware."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.middleware.rate_limit import RateLimiter, RateLimitMiddleware
from app.services.exceptions import RateLimitExceeded


class TestRateLimiter:
    """Test suite for RateLimiter sliding window algorithm."""

    def test_initialization(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter(limit=10, window_seconds=60, cleanup_interval=300)
        
        assert limiter.limit == 10
        assert limiter.window_seconds == 60
        assert limiter.cleanup_interval == 300
        assert limiter._requests == {}

    def test_check_rate_limit_first_request(self):
        """Test first request is always allowed."""
        limiter = RateLimiter(limit=5, window_seconds=60, cleanup_interval=300)
        
        is_allowed, remaining, retry_after = limiter.check_rate_limit("user123")
        
        assert is_allowed is True
        assert remaining == 4  # 5 - 1 = 4 remaining
        assert retry_after == 0

    def test_check_rate_limit_within_limit(self):
        """Test requests within rate limit are allowed."""
        limiter = RateLimiter(limit=3, window_seconds=60, cleanup_interval=300)
        
        # First request
        is_allowed1, remaining1, _ = limiter.check_rate_limit("user123")
        # Second request
        is_allowed2, remaining2, _ = limiter.check_rate_limit("user123")
        # Third request
        is_allowed3, remaining3, _ = limiter.check_rate_limit("user123")
        
        assert is_allowed1 is True and remaining1 == 2
        assert is_allowed2 is True and remaining2 == 1
        assert is_allowed3 is True and remaining3 == 0

    def test_check_rate_limit_exceed_limit(self):
        """Test request exceeding rate limit is blocked."""
        limiter = RateLimiter(limit=2, window_seconds=60, cleanup_interval=300)
        
        # First two requests allowed
        limiter.check_rate_limit("user123")
        limiter.check_rate_limit("user123")
        
        # Third request should be blocked
        is_allowed, remaining, retry_after = limiter.check_rate_limit("user123")
        
        assert is_allowed is False
        assert remaining == 0
        assert retry_after > 0
        assert retry_after <= 61  # Should be within window + 1

    def test_check_rate_limit_different_users(self):
        """Test different users have independent rate limits."""
        limiter = RateLimiter(limit=2, window_seconds=60, cleanup_interval=300)
        
        # User1 makes 2 requests
        limiter.check_rate_limit("user1")
        limiter.check_rate_limit("user1")
        
        # User1 blocked, but user2 should be allowed
        is_allowed1, _, _ = limiter.check_rate_limit("user1")
        is_allowed2, _, _ = limiter.check_rate_limit("user2")
        
        assert is_allowed1 is False
        assert is_allowed2 is True

    def test_check_rate_limit_sliding_window(self):
        """Test that old requests outside window are not counted."""
        limiter = RateLimiter(limit=2, window_seconds=1, cleanup_interval=300)
        
        # Make 2 requests
        limiter.check_rate_limit("user123")
        limiter.check_rate_limit("user123")
        
        # Third request blocked
        is_allowed, _, _ = limiter.check_rate_limit("user123")
        assert is_allowed is False
        
        # Wait for window to pass
        time.sleep(1.1)
        
        # Now should be allowed again
        is_allowed, remaining, _ = limiter.check_rate_limit("user123")
        assert is_allowed is True
        assert remaining == 1

    def test_cleanup_old_entries(self):
        """Test cleanup removes old timestamps."""
        limiter = RateLimiter(limit=5, window_seconds=1, cleanup_interval=1)
        
        # Add some requests
        limiter.check_rate_limit("user1")
        limiter.check_rate_limit("user2")
        
        # Wait for window to pass
        time.sleep(1.1)
        
        # Trigger cleanup through a new request
        limiter.check_rate_limit("user3")
        
        # Old users should have been cleaned up
        # user3 should have 1 request, others should be empty or removed
        assert "user3" in limiter._requests
        assert len(limiter._requests["user3"]) == 1

    def test_get_user_requests_filters_old_timestamps(self):
        """Test that _get_user_requests filters old timestamps."""
        limiter = RateLimiter(limit=5, window_seconds=1, cleanup_interval=300)
        
        # Manually add old and new timestamps
        current_time = time.time()
        limiter._requests["user123"] = [
            current_time - 5,  # Old (outside window)
            current_time - 0.5,  # New (inside window)
            current_time,  # New (inside window)
        ]
        
        requests = limiter._get_user_requests("user123")
        
        assert len(requests) == 2  # Only 2 recent requests

    def test_add_request(self):
        """Test adding request timestamp."""
        limiter = RateLimiter(limit=5, window_seconds=60, cleanup_interval=300)
        
        current_time = time.time()
        limiter._add_request("user123", current_time)
        
        assert "user123" in limiter._requests
        assert current_time in limiter._requests["user123"]


@pytest.mark.asyncio
class TestRateLimitMiddleware:
    """Test suite for RateLimitMiddleware."""

    async def test_middleware_disabled(self):
        """Test middleware doesn't rate limit when disabled."""
        mock_app = MagicMock()
        mock_settings = MagicMock()
        mock_settings.RATE_LIMIT_ENABLED = False
        
        middleware = RateLimitMiddleware(mock_app, mock_settings)
        
        assert middleware.enabled is False
        
        # Create mock request and call_next
        request = MagicMock(spec=Request)
        async def mock_call_next(req):
            return Response("OK")
        
        response = await middleware.dispatch(request, mock_call_next)
        
        assert response.body == b"OK"

    async def test_middleware_whitelisted_paths(self):
        """Test middleware skips whitelisted paths."""
        mock_app = MagicMock()
        mock_settings = MagicMock()
        mock_settings.RATE_LIMIT_ENABLED = True
        mock_settings.RATE_LIMIT_PER_MINUTE = 10
        mock_settings.RATE_LIMIT_WINDOW_SECONDS = 60
        mock_settings.RATE_LIMIT_CLEANUP_INTERVAL = 300
        
        middleware = RateLimitMiddleware(mock_app, mock_settings)
        
        # Create mock request for whitelisted path
        request = MagicMock(spec=Request)
        request.url.path = "/health"
        
        async def mock_call_next(req):
            return Response("Healthy")
        
        response = await middleware.dispatch(request, mock_call_next)
        
        assert response.body == b"Healthy"
        # Should not check rate limit for whitelisted path

    async def test_extract_user_identifier_from_jwt(self):
        """Test extracting user ID from JWT token."""
        mock_app = MagicMock()
        mock_settings = MagicMock()
        mock_settings.RATE_LIMIT_ENABLED = True
        mock_settings.RATE_LIMIT_PER_MINUTE = 10
        mock_settings.RATE_LIMIT_WINDOW_SECONDS = 60
        mock_settings.RATE_LIMIT_CLEANUP_INTERVAL = 300
        mock_settings.SECRET_KEY = "test_secret"
        mock_settings.JWT_ALGORITHM = "HS256"
        
        middleware = RateLimitMiddleware(mock_app, mock_settings)
        
        # Create mock request with JWT
        request = MagicMock(spec=Request)
        request.headers = {"Authorization": "Bearer mock_token"}
        
        with patch("app.middleware.rate_limit.decode_access_token") as mock_decode:
            mock_decode.return_value = {"sub": "user_456"}
            
            user_id = middleware._extract_user_identifier(request)
            
            assert user_id == "user:user_456"
            mock_decode.assert_called_once_with("mock_token", "test_secret", "HS256")

    async def test_extract_user_identifier_invalid_token(self):
        """Test falling back to IP when token is invalid."""
        from app.utils.auth import TokenDecodeError
        
        mock_app = MagicMock()
        mock_settings = MagicMock()
        mock_settings.RATE_LIMIT_ENABLED = True
        mock_settings.RATE_LIMIT_PER_MINUTE = 10
        mock_settings.RATE_LIMIT_WINDOW_SECONDS = 60
        mock_settings.RATE_LIMIT_CLEANUP_INTERVAL = 300
        mock_settings.SECRET_KEY = "test_secret"
        mock_settings.JWT_ALGORITHM = "HS256"
        
        middleware = RateLimitMiddleware(mock_app, mock_settings)
        
        # Create mock request with invalid JWT
        client_mock = MagicMock()
        client_mock.host = "192.168.1.1"
        
        request = MagicMock(spec=Request)
        request.headers = {"Authorization": "Bearer invalid_token"}
        request.client = client_mock
        
        with patch("app.middleware.rate_limit.decode_access_token") as mock_decode:
            mock_decode.side_effect = TokenDecodeError("Invalid token")
            
            user_id = middleware._extract_user_identifier(request)
            
            assert user_id == "ip:192.168.1.1"

    async def test_extract_user_identifier_no_token(self):
        """Test falling back to IP when no token provided."""
        mock_app = MagicMock()
        mock_settings = MagicMock()
        mock_settings.RATE_LIMIT_ENABLED = True
        mock_settings.RATE_LIMIT_PER_MINUTE = 10
        mock_settings.RATE_LIMIT_WINDOW_SECONDS = 60
        mock_settings.RATE_LIMIT_CLEANUP_INTERVAL = 300
        
        middleware = RateLimitMiddleware(mock_app, mock_settings)
        
        # Create mock request without auth header
        client_mock = MagicMock()
        client_mock.host = "10.0.0.5"
        
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = client_mock
        
        user_id = middleware._extract_user_identifier(request)
        
        assert user_id == "ip:10.0.0.5"

    async def test_dispatch_rate_limit_exceeded(self):
        """Test middleware raises RateLimitExceeded when limit is hit."""
        mock_app = MagicMock()
        mock_settings = MagicMock()
        mock_settings.RATE_LIMIT_ENABLED = True
        mock_settings.RATE_LIMIT_PER_MINUTE = 2
        mock_settings.RATE_LIMIT_WINDOW_SECONDS = 60
        mock_settings.RATE_LIMIT_CLEANUP_INTERVAL = 300
        mock_settings.SECRET_KEY = "test_secret"
        mock_settings.JWT_ALGORITHM = "HS256"
        
        middleware = RateLimitMiddleware(mock_app, mock_settings)
        
        client_mock = MagicMock()
        client_mock.host = "192.168.1.1"
        
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = client_mock
        request.url.path = "/api/test"
        
        async def mock_call_next(req):
            return Response("OK")
        
        # First two requests should succeed
        await middleware.dispatch(request, mock_call_next)
        await middleware.dispatch(request, mock_call_next)
        
        # Third request should raise RateLimitExceeded
        with pytest.raises(RateLimitExceeded) as exc_info:
            await middleware.dispatch(request, mock_call_next)
        
        assert "Rate limit exceeded" in str(exc_info.value)
        assert exc_info.value.retry_after > 0
        assert exc_info.value.limit == 2

    async def test_dispatch_adds_rate_limit_headers(self):
        """Test middleware adds rate limit headers to response."""
        mock_app = MagicMock()
        mock_settings = MagicMock()
        mock_settings.RATE_LIMIT_ENABLED = True
        mock_settings.RATE_LIMIT_PER_MINUTE = 10
        mock_settings.RATE_LIMIT_WINDOW_SECONDS = 60
        mock_settings.RATE_LIMIT_CLEANUP_INTERVAL = 300
        mock_settings.SECRET_KEY = "test_secret"
        mock_settings.JWT_ALGORITHM = "HS256"
        
        middleware = RateLimitMiddleware(mock_app, mock_settings)
        
        client_mock = MagicMock()
        client_mock.host = "192.168.1.1"
        
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = client_mock
        request.url.path = "/api/test"
        
        async def mock_call_next(req):
            return Response("OK")
        
        response = await middleware.dispatch(request, mock_call_next)
        
        assert "X-RateLimit-Limit" in response.headers
        assert response.headers["X-RateLimit-Limit"] == "10"
        assert "X-RateLimit-Remaining" in response.headers
        assert response.headers["X-RateLimit-Remaining"] == "9"  # After 1 request
        assert "X-RateLimit-Reset" in response.headers
