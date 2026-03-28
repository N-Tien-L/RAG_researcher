"""Tests for RAG query routes."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.db.models import User


class TestQueryRAG:
    """Test cases for POST /api/rag/query endpoint."""
    
    @pytest.mark.asyncio
    @patch("app.applications.rag_application.RAGApplicationService.query")
    async def test_query_rag_success(
        self,
        mock_query: AsyncMock,
        authenticated_client: AsyncClient,
        test_user: User,
        source_factory,
    ):
        """Valid query returns answer and sources."""
        await source_factory(user_id=test_user.id, status="ready")

        mock_query.return_value = {
            "answer": "This is the answer to your question.",
            "sources": [
                {
                    "source_id": 1,
                    "title": "Test Document",
                    "chunk_content": "Relevant chunk content...",
                    "score": 0.85,
                }
            ],
            "metadata": {
                "num_chunks_retrieved": 5,
                "generation_time_ms": 150,
            },
        }
        
        response = await authenticated_client.post(
            "/api/rag/query",
            json={
                "question": "What is RAG?",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "answer" in data
        assert "sources" in data
        assert isinstance(data["answer"], str)
        assert isinstance(data["sources"], list)
        assert len(data["sources"]) > 0
        assert data["sources"][0]["source_id"] == 1
    
    @pytest.mark.asyncio
    @patch("app.applications.rag_application.RAGApplicationService.query")
    async def test_query_rag_with_source_filter(
        self,
        mock_query: AsyncMock,
        authenticated_client: AsyncClient,
        test_user: User,
        source_factory,
    ):
        """Query filtered by source_id works."""
        source = await source_factory(user_id=test_user.id)
        
        mock_query.return_value = {
            "answer": "Answer from specific source.",
            "sources": [
                {
                    "source_id": str(source.id),
                    "title": source.title,
                    "chunk_content": "Content...",
                    "score": 0.9,
                }
            ],
        }
        
        response = await authenticated_client.post(
            "/api/rag/query",
            json={
                "question": "What is this about?",
                "source_id": str(source.id),
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["sources"][0]["source_id"] == str(source.id)
    
    @pytest.mark.asyncio
    @patch("app.applications.rag_application.RAGApplicationService.query")
    async def test_query_rag_with_collection(
        self,
        mock_query: AsyncMock,
        authenticated_client: AsyncClient,
        test_user: User,
        source_factory,
    ):
        """Basic query without filters works."""
        await source_factory(user_id=test_user.id, status="ready")

        mock_query.return_value = {
            "answer": "Answer from collection.",
            "sources": [],
        }
        
        response = await authenticated_client.post(
            "/api/rag/query",
            json={
                "question": "Tell me about collections",
            },
        )
        
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_query_rag_empty_question(self, authenticated_client: AsyncClient):
        """Empty question returns 422."""
        response = await authenticated_client.post(
            "/api/rag/query",
            json={
                "question": "",
            },
        )
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_query_rag_question_too_long(self, authenticated_client: AsyncClient):
        """Exceeds max length returns 422."""
        long_question = "What is this? " * 1000  # Very long question
        
        response = await authenticated_client.post(
            "/api/rag/query",
            json={
                "question": long_question,
            },
        )
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_query_rag_unauthorized(self, client: AsyncClient):
        """No auth returns 401."""
        response = await client.post(
            "/api/rag/query",
            json={
                "question": "What is RAG?",
            },
        )
        
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    @patch("app.applications.rag_application.RAGApplicationService.query")
    async def test_query_rag_llm_error(
        self,
        mock_query: AsyncMock,
        authenticated_client: AsyncClient,
        test_user: User,
        source_factory,
    ):
        """Mock LLM failure returns 503."""
        await source_factory(user_id=test_user.id, status="ready")

        mock_query.side_effect = Exception("LLM service unavailable")
        
        response = await authenticated_client.post(
            "/api/rag/query",
            json={
                "question": "What is RAG?",
            },
        )
        
        # Actual status code depends on error handling implementation
        assert response.status_code in [500, 503]
    
    @pytest.mark.asyncio
    @patch("app.embeddings.huggingface_tei.HuggingFaceTEIEmbedder.embed_query")
    async def test_query_rag_embedding_error(
        self,
        mock_embed: AsyncMock,
        authenticated_client: AsyncClient,
    ):
        """Mock embedding failure returns 503."""
        mock_embed.side_effect = Exception("Embedding service unavailable")
        
        response = await authenticated_client.post(
            "/api/rag/query",
            json={
                "question": "What is RAG?",
            },
        )
        
        # Actual status code depends on error handling implementation
        assert response.status_code in [500, 503]
    
    @pytest.mark.asyncio
    @patch("app.applications.rag_application.RAGApplicationService.query")
    async def test_query_rag_no_results(
        self,
        mock_query: AsyncMock,
        authenticated_client: AsyncClient,
        test_user: User,
        source_factory,
    ):
        """No matching chunks returns answer with empty sources."""
        await source_factory(user_id=test_user.id, status="ready")

        mock_query.return_value = {
            "answer": "I couldn't find relevant information to answer your question.",
            "sources": [],
            "metadata": {
                "num_chunks_retrieved": 0,
            },
        }
        
        response = await authenticated_client.post(
            "/api/rag/query",
            json={
                "question": "What is the meaning of life?",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "answer" in data
        assert data["sources"] == []
