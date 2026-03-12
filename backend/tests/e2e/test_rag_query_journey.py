"""E2E journey: seeded chunks → full RAG query pipeline.

Exercises the complete flow from HTTP request through middleware, route handler,
RAGApplicationService, LCEL pipeline, and real pgvector cosine-similarity retrieval.

Only the two leaf services are mocked:
- HuggingFaceTEIEmbedder (returns a deterministic E2E_EMBEDDING vector)
- RAGPipeline._generate_answer (returns a static answer string)

The pgvector similarity search runs against real data seeded by the
``seeded_chunks`` fixture.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.e2e.conftest import E2E_ANSWER, E2E_COLLECTION

pytestmark = pytest.mark.e2e


class TestRagQueryJourney:
    """RAG query end-to-end journey tests."""

    @pytest.mark.asyncio
    async def test_query_returns_answer_and_sources(
        self,
        authenticated_client: AsyncClient,
        seeded_chunks: tuple,
    ) -> None:
        """Query flows through real pgvector retrieval and returns the mocked answer.

        Steps
        -----
        1. Seed one DocumentChunk with E2E_EMBEDDING.
        2. POST /api/rag/query with same collection.
        3. Mocked embedder queries with same vector → chunk is retrieved.
        4. Mocked LLM → returns E2E_ANSWER.
        5. Response body contains correct answer and at least one source.
        """
        chunk, source = seeded_chunks

        response = await authenticated_client.post(
            "/api/rag/query",
            json={
                "question": "What is RAG?",
                "collection_name": E2E_COLLECTION,
            },
        )

        assert response.status_code == 200, response.text
        data = response.json()

        assert data["answer"] == E2E_ANSWER
        assert isinstance(data["sources"], list)
        assert len(data["sources"]) >= 1

    @pytest.mark.asyncio
    async def test_query_with_source_id_filter(
        self,
        authenticated_client: AsyncClient,
        seeded_chunks: tuple,
    ) -> None:
        """source_id filter is forwarded to pgvector and chunk is still retrieved."""
        chunk, source = seeded_chunks

        response = await authenticated_client.post(
            "/api/rag/query",
            json={
                "question": "Tell me about this document.",
                "collection_name": E2E_COLLECTION,
                "source_id": str(source.id),
            },
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["answer"] == E2E_ANSWER

    @pytest.mark.asyncio
    async def test_query_against_empty_collection_returns_fallback(
        self,
        authenticated_client: AsyncClient,
        setup_test_db: object,
    ) -> None:
        """Query with no matching chunks returns the pipeline's fallback response."""
        response = await authenticated_client.post(
            "/api/rag/query",
            json={
                "question": "Does anything exist here?",
                "collection_name": "nonexistent_e2e_collection_xyz",
            },
        )

        assert response.status_code == 200, response.text
        data = response.json()
        # Pipeline returns "I don't know…" when no chunks are found
        assert "answer" in data
        assert len(data["answer"]) > 0

    @pytest.mark.asyncio
    async def test_query_without_auth_is_rejected(
        self,
        client: AsyncClient,
        seeded_chunks: tuple,
    ) -> None:
        """Unauthenticated RAG query returns 401."""
        response = await client.post(
            "/api/rag/query",
            json={"question": "Sneaky query", "collection_name": E2E_COLLECTION},
        )
        assert response.status_code == 401
