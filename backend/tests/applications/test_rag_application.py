"""Tests for RAGApplicationService - orchestrates RAG query pipeline."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.applications.rag_application import RAGApplicationService


@pytest.mark.asyncio
class TestRAGApplicationService:
    """Test suite for RAGApplicationService."""

    async def test_query_basic_success(self, test_db_session: AsyncSession):
        """Test basic RAG query returns answer and sources."""
        service = RAGApplicationService(test_db_session, top_k=5)

        # Mock pipeline response
        mock_result = {
            "answer": "Python is a high-level programming language.",
            "sources": [
                {
                    "source_id": "src-1",
                    "chunk_id": "chunk-1",
                    "content": "Python is a high-level...",
                    "score": 0.95,
                }
            ],
        }
        service.pipeline.query = AsyncMock(return_value=mock_result)

        # Execute
        result = await service.query(
            question="What is Python?",
            collection_name="documents",
        )

        # Assert result structure
        assert "answer" in result
        assert "sources" in result
        assert result["answer"] == "Python is a high-level programming language."
        assert len(result["sources"]) == 1
        assert result["sources"][0]["source_id"] == "src-1"

        # Verify pipeline called correctly
        service.pipeline.query.assert_called_once()
        call_kwargs = service.pipeline.query.call_args.kwargs
        assert call_kwargs["question"] == "What is Python?"
        assert call_kwargs["collection_name"] == "documents"
        assert call_kwargs["where"] is None

    async def test_query_with_source_filter(self, test_db_session: AsyncSession):
        """Test RAG query with source_id filter."""
        service = RAGApplicationService(test_db_session, top_k=3)

        mock_result = {
            "answer": "Filtered answer",
            "sources": [{"source_id": "specific-source", "content": "..."}],
        }
        service.pipeline.query = AsyncMock(return_value=mock_result)

        # Execute with source filter
        result = await service.query(
            question="Test question",
            collection_name="documents",
            source_id="specific-source",
        )

        # Verify filter applied
        call_kwargs = service.pipeline.query.call_args.kwargs
        assert call_kwargs["where"] == {"source_id": "specific-source"}
        assert result["sources"][0]["source_id"] == "specific-source"

    async def test_query_with_user_id_logging(self, test_db_session: AsyncSession):
        """Test that user_id is included in logging context."""
        service = RAGApplicationService(test_db_session)

        mock_result = {"answer": "Test answer", "sources": []}
        service.pipeline.query = AsyncMock(return_value=mock_result)

        user_id = uuid4()

        # Execute with user_id
        with patch("app.applications.rag_application.logger") as mock_logger:
            await service.query(
                question="Test question",
                collection_name="documents",
                user_id=user_id,
            )

            # Verify logging called with user_id
            assert mock_logger.info.call_count >= 2  # Start and completion logs
            start_log_call = mock_logger.info.call_args_list[0]
            assert str(user_id) in str(start_log_call)

    async def test_query_without_user_id(self, test_db_session: AsyncSession):
        """Test query works without user_id (anonymous requests)."""
        service = RAGApplicationService(test_db_session)

        mock_result = {"answer": "Test answer", "sources": []}
        service.pipeline.query = AsyncMock(return_value=mock_result)

        # Execute without user_id
        result = await service.query(
            question="Test question",
            collection_name="documents",
        )

        # Should complete successfully
        assert result["answer"] == "Test answer"

    async def test_query_empty_sources(self, test_db_session: AsyncSession):
        """Test query with no relevant sources found."""
        service = RAGApplicationService(test_db_session, top_k=5)

        mock_result = {
            "answer": "I don't have enough information to answer that.",
            "sources": [],
        }
        service.pipeline.query = AsyncMock(return_value=mock_result)

        # Execute
        result = await service.query(
            question="Obscure question with no context",
            collection_name="documents",
        )

        # Assert graceful handling
        assert result["answer"] is not None
        assert len(result["sources"]) == 0

    async def test_query_respects_top_k_parameter(self, test_db_session: AsyncSession):
        """Test that top_k is properly passed to pipeline."""
        # Initialize with custom top_k
        service = RAGApplicationService(test_db_session, top_k=10)

        assert service.pipeline.top_k == 10

        # Change top_k
        service_small = RAGApplicationService(test_db_session, top_k=2)
        assert service_small.pipeline.top_k == 2

    async def test_query_long_question_truncation(self, test_db_session: AsyncSession):
        """Test query with very long question (logging should truncate)."""
        service = RAGApplicationService(test_db_session)

        mock_result = {"answer": "Response", "sources": []}
        service.pipeline.query = AsyncMock(return_value=mock_result)

        # Very long question
        long_question = "What is " + "X" * 500

        with patch("app.applications.rag_application.logger") as mock_logger:
            await service.query(
                question=long_question,
                collection_name="documents",
            )

            # Verify question was truncated in logging (first 100 chars)
            start_log = mock_logger.info.call_args_list[0]
            logged_question = start_log[1]["question"]
            assert len(logged_question) == 100
            assert logged_question == long_question[:100]

    async def test_query_multiple_sources(self, test_db_session: AsyncSession):
        """Test query returning multiple sources."""
        service = RAGApplicationService(test_db_session, top_k=5)

        mock_result = {
            "answer": "Comprehensive answer from multiple sources.",
            "sources": [
                {"source_id": f"src-{i}", "content": f"Content {i}", "score": 0.9 - i * 0.1}
                for i in range(5)
            ],
        }
        service.pipeline.query = AsyncMock(return_value=mock_result)

        # Execute
        result = await service.query(
            question="Complex question",
            collection_name="documents",
        )

        # Assert all sources returned
        assert len(result["sources"]) == 5
        assert result["sources"][0]["source_id"] == "src-0"
        assert result["sources"][4]["source_id"] == "src-4"

    async def test_query_pipeline_error_propagates(self, test_db_session: AsyncSession):
        """Test that pipeline errors are propagated."""
        service = RAGApplicationService(test_db_session)

        # Mock pipeline to raise error
        service.pipeline.query = AsyncMock(
            side_effect=Exception("Embedding service unavailable")
        )

        # Execute and expect error
        with pytest.raises(Exception) as exc_info:
            await service.query(
                question="Test",
                collection_name="documents",
            )

        assert "Embedding service unavailable" in str(exc_info.value)

    async def test_service_initialization(self, test_db_session: AsyncSession):
        """Test service initializes with correct configuration."""
        service = RAGApplicationService(test_db_session, top_k=7)

        # Assert initialization
        assert service.db is test_db_session
        assert service.pipeline is not None
        assert service.pipeline.top_k == 7

    async def test_query_with_complex_filters(self, test_db_session: AsyncSession):
        """Test that only source_id filter is applied (no other filters supported)."""
        service = RAGApplicationService(test_db_session)

        mock_result = {"answer": "Filtered", "sources": []}
        service.pipeline.query = AsyncMock(return_value=mock_result)

        # Execute with source_id filter
        await service.query(
            question="Test",
            collection_name="docs",
            source_id="my-source",
        )

        # Verify only source_id in where clause
        call_kwargs = service.pipeline.query.call_args.kwargs
        assert call_kwargs["where"] == {"source_id": "my-source"}
        assert len(call_kwargs["where"]) == 1

    async def test_query_logs_answer_length(self, test_db_session: AsyncSession):
        """Test completion logging includes answer length metric."""
        service = RAGApplicationService(test_db_session)

        long_answer = "A" * 500
        mock_result = {"answer": long_answer, "sources": []}
        service.pipeline.query = AsyncMock(return_value=mock_result)

        with patch("app.applications.rag_application.logger") as mock_logger:
            await service.query(
                question="Test",
                collection_name="documents",
            )

            # Check completion log
            completion_log = mock_logger.info.call_args_list[1]
            assert completion_log[1]["answer_length"] == 500
            assert completion_log[1]["num_sources"] == 0
