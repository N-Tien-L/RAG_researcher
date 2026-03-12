"""Tests for custom exceptions."""

import pytest

from app.services.exceptions import IngestionError, LLMError


class TestIngestionError:
    """Tests for IngestionError exception."""
    
    def test_ingestion_error_with_kwargs(self):
        """IngestionError accepts request context kwargs."""
        error = IngestionError(
            message="Test error",
            stage="extraction",
            source_id="test-123",
            request_id="req-456",  # Allowed kwarg
            user_id="user-789",  # Allowed kwarg
        )
        
        assert error.message == "Test error"
        assert error.details["stage"] == "extraction"
        assert error.details["source_id"] == "test-123"
        assert error.error_code == "INGESTION_EXTRACTION"
        assert error.request_id == "req-456"
        assert error.user_id == "user-789"


class TestLLMError:
    """Tests for LLMError exception."""
    
    def test_llm_error_with_kwargs(self):
        """LLMError accepts request context kwargs."""
        error = LLMError(
            message="Generation failed",
            model="gpt-4",
            request_id="req-789",  # Allowed kwarg
            user_id="user-123",  # Allowed kwarg
        )
        
        assert error.message == "Generation failed"
        assert error.details["model"] == "gpt-4"
        assert error.error_code == "LLM_GENERATION_FAILED"
        assert error.request_id == "req-789"
        assert error.user_id == "user-123"
