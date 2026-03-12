"""Tests for request context middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.middleware.request_context import RequestContextMiddleware


@pytest.mark.asyncio
class TestRequestContextMiddleware:
    """Test suite for RequestContextMiddleware."""

    async def test_middleware_adds_request_id(self):
        """Test middleware adds request ID to request state."""
        mock_app = MagicMock()
        middleware = RequestContextMiddleware(mock_app)
        
        # Create mock request
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        
        async def mock_call_next(req):
            # Verify request_id was set on state
            assert hasattr(req.state, 'request_id')
            assert isinstance(req.state.request_id, str)
            assert len(req.state.request_id) > 0
            return Response("OK")
        
        with patch("structlog.contextvars.bind_contextvars") as mock_bind:
            with patch("structlog.contextvars.clear_contextvars") as mock_clear:
                response = await middleware.dispatch(request, mock_call_next)
                
                assert response.status_code == 200
                mock_bind.assert_called_once()
                mock_clear.assert_called_once()

    async def test_middleware_adds_request_id_header(self):
        """Test middleware adds X-Request-ID header to response."""
        mock_app = MagicMock()
        middleware = RequestContextMiddleware(mock_app)
        
        # Create mock request
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        
        async def mock_call_next(req):
            return Response("OK")
        
        with patch("structlog.contextvars.bind_contextvars"):
            with patch("structlog.contextvars.clear_contextvars"):
                response = await middleware.dispatch(request, mock_call_next)
                
                assert "X-Request-ID" in response.headers
                assert len(response.headers["X-Request-ID"]) == 36  # UUID format

    async def test_middleware_binds_to_structlog(self):
        """Test middleware binds request ID to structlog context."""
        mock_app = MagicMock()
        middleware = RequestContextMiddleware(mock_app)
        
        # Create mock request
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        
        async def mock_call_next(req):
            return Response("OK")
        
        with patch("structlog.contextvars.bind_contextvars") as mock_bind:
            with patch("structlog.contextvars.clear_contextvars"):
                await middleware.dispatch(request, mock_call_next)
                
                # Verify bind was called with request_id
                assert mock_bind.called
                call_kwargs = mock_bind.call_args.kwargs
                assert "request_id" in call_kwargs
                assert isinstance(call_kwargs["request_id"], str)

    async def test_middleware_clears_context_on_completion(self):
        """Test middleware clears structlog context after request."""
        mock_app = MagicMock()
        middleware = RequestContextMiddleware(mock_app)
        
        # Create mock request
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        
        async def mock_call_next(req):
            return Response("OK")
        
        with patch("structlog.contextvars.bind_contextvars"):
            with patch("structlog.contextvars.clear_contextvars") as mock_clear:
                await middleware.dispatch(request, mock_call_next)
                
                # Verify clear was called in finally block
                mock_clear.assert_called_once()

    async def test_middleware_clears_context_on_exception(self):
        """Test middleware clears context even when exception occurs."""
        mock_app = MagicMock()
        middleware = RequestContextMiddleware(mock_app)
        
        # Create mock request
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        
        async def mock_call_next_error(req):
            raise ValueError("Test error")
        
        with patch("structlog.contextvars.bind_contextvars"):
            with patch("structlog.contextvars.clear_contextvars") as mock_clear:
                with pytest.raises(ValueError, match="Test error"):
                    await middleware.dispatch(request, mock_call_next_error)
                
                # Verify clear was called even after exception
                mock_clear.assert_called_once()

    async def test_middleware_request_ids_are_unique(self):
        """Test that each request gets a unique request ID."""
        mock_app = MagicMock()
        middleware = RequestContextMiddleware(mock_app)
        
        request_ids = []
        
        async def mock_call_next(req):
            request_ids.append(req.state.request_id)
            return Response("OK")
        
        with patch("structlog.contextvars.bind_contextvars"):
            with patch("structlog.contextvars.clear_contextvars"):
                # Make multiple requests
                for _ in range(5):
                    request = MagicMock(spec=Request)
                    request.state = MagicMock()
                    await middleware.dispatch(request, mock_call_next)
                
                # Verify all request IDs are unique
                assert len(set(request_ids)) == 5
