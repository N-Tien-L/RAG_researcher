"""Tests for observability middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.middleware.observability import ObservabilityMiddleware


@pytest.mark.asyncio
class TestObservabilityMiddleware:
    """Test suite for ObservabilityMiddleware."""

    async def test_middleware_tracks_request(self):
        """Test middleware tracks request metrics and tracing."""
        mock_app = MagicMock()
        middleware = ObservabilityMiddleware(mock_app)
        
        # Create mock request
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/test"
        request.state.request_id = "req-123"
        
        async def mock_call_next(req):
            return Response("OK", status_code=200)
        
        with patch("app.middleware.observability.settings") as mock_settings:
            mock_settings.ENABLE_METRICS = True
            
            with patch("app.middleware.observability.get_tracer") as mock_get_tracer:
                mock_tracer = MagicMock()
                mock_span = MagicMock()
                mock_span.__enter__ = MagicMock(return_value=mock_span)
                mock_span.__exit__ = MagicMock(return_value=False)
                mock_span.set_attribute = MagicMock()
                mock_span.record_exception = MagicMock()
                mock_span.set_status = MagicMock()
                
                # Mock span context
                mock_span_ctx = MagicMock()
                mock_span_ctx.trace_id = 12345678901234567890
                mock_span_ctx.span_id = 9876543210
                mock_span.get_span_context = MagicMock(return_value=mock_span_ctx)
                
                mock_tracer.start_as_current_span = MagicMock(return_value=mock_span)
                mock_get_tracer.return_value = mock_tracer
                
                with patch("app.middleware.observability.active_requests") as mock_active:
                    with patch("app.middleware.observability.record_http_request") as mock_record:
                        response = await middleware.dispatch(request, mock_call_next)
                        
                        assert response.status_code == 200
                        mock_active.inc.assert_called_once()
                        mock_active.dec.assert_called_once()
                        mock_record.assert_called_once()
                        
                        # Verify span attributes were set
                        mock_span.set_attribute.assert_any_call("http.method", "GET")
                        mock_span.set_attribute.assert_any_call("http.path", "/api/test")
                        mock_span.set_attribute.assert_any_call("request_id", "req-123")

    async def test_middleware_handles_exception(self):
        """Test middleware handles exceptions during request processing."""
        mock_app = MagicMock()
        middleware = ObservabilityMiddleware(mock_app)
        
        # Create mock request
        request = MagicMock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/error"
        request.state.request_id = None
        
        async def mock_call_next_error(req):
            raise ValueError("Test error")
        
        with patch("app.middleware.observability.settings") as mock_settings:
            mock_settings.ENABLE_METRICS = True
            
            with patch("app.middleware.observability.get_tracer") as mock_get_tracer:
                mock_tracer = MagicMock()
                mock_span = MagicMock()
                mock_span.__enter__ = MagicMock(return_value=mock_span)
                mock_span.__exit__ = MagicMock(return_value=False)
                mock_span.set_attribute = MagicMock()
                mock_span.record_exception = MagicMock()
                mock_span.set_status = MagicMock()
                mock_span.get_span_context = MagicMock(return_value=None)
                
                mock_tracer.start_as_current_span = MagicMock(return_value=mock_span)
                mock_get_tracer.return_value = mock_tracer
                
                with patch("app.middleware.observability.active_requests") as mock_active:
                    with patch("app.middleware.observability.record_http_request") as mock_record:
                        with pytest.raises(ValueError, match="Test error"):
                            await middleware.dispatch(request, mock_call_next_error)
                        
                        # Verify exception was recorded
                        mock_span.record_exception.assert_called_once()
                        mock_span.set_status.assert_called_once()
                        
                        # Metrics should still be recorded
                        mock_active.inc.assert_called_once()
                        mock_active.dec.assert_called_once()
                        mock_record.assert_called_once()

    async def test_middleware_adds_trace_headers(self):
        """Test middleware adds trace ID and span ID to response headers."""
        mock_app = MagicMock()
        middleware = ObservabilityMiddleware(mock_app)
        
        # Create mock request
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/test"
        request.state.request_id = "req-456"
        
        async def mock_call_next(req):
            return Response("OK", status_code=200)
        
        with patch("app.middleware.observability.settings") as mock_settings:
            mock_settings.ENABLE_METRICS = False
            
            with patch("app.middleware.observability.get_tracer") as mock_get_tracer:
                mock_tracer = MagicMock()
                mock_span = MagicMock()
                mock_span.__enter__ = MagicMock(return_value=mock_span)
                mock_span.__exit__ = MagicMock(return_value=False)
                mock_span.set_attribute = MagicMock()
                
                # Mock span context with trace and span IDs
                mock_span_ctx = MagicMock()
                mock_span_ctx.trace_id = 0x1234567890abcdef1234567890abcdef
                mock_span_ctx.span_id = 0x1234567890abcdef
                mock_span.get_span_context = MagicMock(return_value=mock_span_ctx)
                
                mock_tracer.start_as_current_span = MagicMock(return_value=mock_span)
                mock_get_tracer.return_value = mock_tracer
                
                response = await middleware.dispatch(request, mock_call_next)
                
                # Verify trace headers were added
                assert "X-Trace-ID" in response.headers
                assert "X-Span-ID" in response.headers
                assert len(response.headers["X-Trace-ID"]) == 32  # 32 hex chars
                assert len(response.headers["X-Span-ID"]) == 16  # 16 hex chars

    async def test_middleware_with_user_context(self):
        """Test middleware includes user_id in span when available."""
        mock_app = MagicMock()
        middleware = ObservabilityMiddleware(mock_app)
        
        # Create mock request
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/user-action"
        request.state.request_id = "req-789"
        
        async def mock_call_next(req):
            return Response("OK", status_code=200)
        
        with patch("app.middleware.observability.settings") as mock_settings:
            mock_settings.ENABLE_METRICS = True
            
            with patch("app.middleware.observability.get_tracer") as mock_get_tracer:
                mock_tracer = MagicMock()
                mock_span = MagicMock()
                mock_span.__enter__ = MagicMock(return_value=mock_span)
                mock_span.__exit__ = MagicMock(return_value=False)
                mock_span.set_attribute = MagicMock()
                mock_span.get_span_context = MagicMock(return_value=None)
                
                mock_tracer.start_as_current_span = MagicMock(return_value=mock_span)
                mock_get_tracer.return_value = mock_tracer
                
                # Mock structlog contextvars with user_id
                with patch("structlog.contextvars.get_contextvars") as mock_get_ctx:
                    mock_get_ctx.return_value = {"user_id": "user-123"}
                    
                    with patch("app.middleware.observability.active_requests"):
                        with patch("app.middleware.observability.record_http_request"):
                            await middleware.dispatch(request, mock_call_next)
                            
                            # Verify user_id was set as span attribute
                            mock_span.set_attribute.assert_any_call("user_id", "user-123")
