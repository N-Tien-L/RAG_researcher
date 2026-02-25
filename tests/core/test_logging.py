"""Tests for structured logging utilities."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import structlog
import pytest

from app.core.logging import (
    add_app_context,
    add_trace_context,
    bind_trace_context,
    configure_logging,
    get_logger,
    log_cache_operation,
    log_generation,
    log_retrieval,
)
from app.core.config import settings


class TestAddContextHelpers:
    """Tests for context injection helpers."""

    def test_add_app_context_sets_app(self) -> None:
        event = add_app_context(None, "info", {"message": "test"})
        assert event["app"] == "rag_researcher"

    def test_add_trace_context_when_recording(self) -> None:
        mock_ctx = SimpleNamespace(trace_id=123, span_id=456)
        mock_span = Mock()
        mock_span.is_recording.return_value = True
        mock_span.get_span_context.return_value = mock_ctx

        with patch("app.core.logging.trace.get_current_span", return_value=mock_span):
            result = add_trace_context(None, "info", {"base": "value"})

        assert result["trace_id"] == format(123, "032x")
        assert result["span_id"] == format(456, "016x")
        assert result["base"] == "value"

    def test_add_trace_context_when_not_recording(self) -> None:
        mock_span = Mock()
        mock_span.is_recording.return_value = False

        with patch("app.core.logging.trace.get_current_span", return_value=mock_span):
            result = add_trace_context(None, "info", {"keep": "value"})

        assert result == {"keep": "value"}


class TestConfigureLogging:
    """Tests for configure_logging behavior."""

    @patch("app.core.logging.structlog.configure")
    @patch("app.core.logging.logging.basicConfig")
    @patch("app.core.logging.logging.StreamHandler")
    def test_configure_logging_adds_json_renderer(self, stream_handler: MagicMock, basic_config: MagicMock, structlog_config: MagicMock) -> None:
        stream_handler.return_value = MagicMock()

        configure_logging(json_logs=True)

        processors = structlog_config.call_args.kwargs["processors"]
        assert processors[-1].__class__ is structlog.processors.JSONRenderer

    @patch("app.core.logging.structlog.configure")
    @patch("app.core.logging.logging.basicConfig")
    @patch("app.core.logging.logging.StreamHandler")
    def test_configure_logging_adds_console_renderer(self, stream_handler: MagicMock, basic_config: MagicMock, structlog_config: MagicMock) -> None:
        stream_handler.return_value = MagicMock()

        configure_logging(json_logs=False)

        processors = structlog_config.call_args.kwargs["processors"]
        assert isinstance(processors[-1], structlog.dev.ConsoleRenderer)
        assert processors[-2] is structlog.processors.format_exc_info

    @patch("app.core.logging.structlog.configure")
    @patch("app.core.logging.logging.basicConfig")
    @patch("app.core.logging.logging.StreamHandler")
    def test_configure_logging_adds_loki_handler_when_enabled(self, stream_handler: MagicMock, basic_config: MagicMock, structlog_config: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
        stream_handler.return_value = MagicMock()
        mock_loki_handler = MagicMock()
        mock_loki_class = MagicMock(return_value=mock_loki_handler)

        monkeypatch.setattr(settings, "LOKI_ENABLED", True)
        monkeypatch.setattr(settings, "LOKI_ENDPOINT", "http://loki")

        with patch.dict("sys.modules", {"logging_loki": SimpleNamespace(LokiHandler=mock_loki_class)}):
            configure_logging(json_logs=True)

        handlers = basic_config.call_args.kwargs["handlers"]
        assert mock_loki_handler in handlers
        mock_loki_class.assert_called_once()


class TestLoggerUtilities:
    """Tests for logger helpers and wrappers."""

    def test_get_logger_returns_structlog_logger(self) -> None:
        logger = get_logger("test")
        assert isinstance(
            logger,
            (structlog.stdlib.BoundLogger, structlog.stdlib.BoundLoggerLazyProxy),
        )

    def test_bind_trace_context_when_recording(self) -> None:
        mock_ctx = SimpleNamespace(trace_id=987, span_id=654)
        mock_span = Mock()
        mock_span.is_recording.return_value = True
        mock_span.get_span_context.return_value = mock_ctx

        with patch("app.core.logging.trace.get_current_span", return_value=mock_span), patch(
            "app.core.logging.structlog.contextvars.bind_contextvars"
        ) as bind_ctx:
            bind_trace_context()

        bind_ctx.assert_called_once_with(
            trace_id=format(987, "032x"),
            span_id=format(654, "016x"),
        )

    def test_bind_trace_context_when_not_recording(self) -> None:
        mock_span = Mock()
        mock_span.is_recording.return_value = False

        with patch("app.core.logging.trace.get_current_span", return_value=mock_span), patch(
            "app.core.logging.structlog.contextvars.bind_contextvars"
        ) as bind_ctx:
            bind_trace_context()

        bind_ctx.assert_not_called()

    def test_log_retrieval_calls_logger(self) -> None:
        logger = Mock()
        log_retrieval(logger, "query", 3, 0.9, 12.3)
        logger.info.assert_called_once_with(
            "retrieval_completed",
            query="query",
            num_chunks=3,
            top_score=0.9,
            retrieval_time_ms=12.3,
        )

    def test_log_generation_calls_logger(self) -> None:
        logger = Mock()
        log_generation(logger, "question", 120, 42, 55.5)
        logger.info.assert_called_once_with(
            "generation_completed",
            query="question",
            response_length=120,
            tokens_used=42,
            generation_time_ms=55.5,
        )

    def test_log_cache_operation_truncates_key_and_rounds_time(self) -> None:
        logger = Mock()
        key = "1234567890abcdef1234567890"
        log_cache_operation(logger, "hit", "embedding", key, 12.3456)
        logger.info.assert_called_once_with(
            "cache_operation",
            operation="hit",
            cache_type="embedding",
            key_hash="1234567890abcdef",
            execution_time_ms=12.35,
        )
