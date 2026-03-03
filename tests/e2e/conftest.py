"""E2E test fixtures.

Patches only the two true external services (TEI embedder + Ollama LLM) so that
all in-process layers — middleware, services, LCEL pipeline, pgvector — run for real.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentChunk, Source, User

# ---------------------------------------------------------------------------
# Constants shared across e2e tests
# ---------------------------------------------------------------------------

#: Deterministic embedding used for every seeded chunk and every mock query.
E2E_EMBEDDING: list[float] = [0.1] * 384

#: Static answer returned by the mocked LLM.
E2E_ANSWER: str = "E2E test answer."

#: Collection name used for all e2e seeded data.
E2E_COLLECTION: str = "e2e_collection"


# ---------------------------------------------------------------------------
# External-service mocks (autouse → active for every e2e test)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_embedder_class():
    """Replace HuggingFaceTEIEmbedder in the pipeline module.

    The replacement instance returns E2E_EMBEDDING for every embed_query /
    embed_documents call, avoiding any HTTP call to the TEI server.
    """
    mock_instance = MagicMock()
    mock_instance.embed_query = AsyncMock(return_value=E2E_EMBEDDING)
    mock_instance.embed_documents = AsyncMock(return_value=[E2E_EMBEDDING])
    mock_instance.dimension = 384

    with patch("app.rag.pipeline.HuggingFaceTEIEmbedder", return_value=mock_instance):
        yield mock_instance


@pytest.fixture(autouse=True)
def mock_generate_answer():
    """Patch RAGPipeline._generate_answer to bypass LCEL + Ollama entirely.

    Returns a deterministic (answer, generation_time_seconds) tuple so that
    the rest of the pipeline (cache lookup, source formatting, metrics) still
    executes.
    """
    with patch(
        "app.rag.pipeline.RAGPipeline._generate_answer",
        new_callable=AsyncMock,
        return_value=(E2E_ANSWER, 0.01),
    ):
        yield


# ---------------------------------------------------------------------------
# DB-level seed fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seeded_source(test_db_session: AsyncSession, test_user: User) -> Source:
    """Insert a Source row into the test database.

    Args:
        test_db_session: Per-test async DB session.
        test_user: Pre-existing test user to own the source.

    Returns:
        Persisted Source instance.
    """
    source = Source(
        user_id=test_user.id,
        type="pdf",
        title="E2E Test Document",
        status="ready",
        collection_name=E2E_COLLECTION,
        source_uri="file://e2e/test.pdf",
    )
    test_db_session.add(source)
    await test_db_session.commit()
    await test_db_session.refresh(source)
    return source


@pytest_asyncio.fixture
async def seeded_chunks(
    test_db_session: AsyncSession,
    seeded_source: Source,
) -> tuple[DocumentChunk, Source]:
    """Insert a DocumentChunk with the deterministic E2E_EMBEDDING into pgvector.

    Having a known embedding means the mocked embed_query will always score a
    near-perfect cosine similarity against this chunk, guaranteeing retrieval.

    Args:
        test_db_session: Per-test async DB session.
        seeded_source: Parent source to link the chunk to.

    Returns:
        Tuple of (DocumentChunk, Source).
    """
    chunk = DocumentChunk(
        id=uuid.uuid4(),
        chunk_id=f"e2e-chunk-{uuid.uuid4()}",
        content="This is E2E test content about Retrieval-Augmented Generation systems.",
        embedding=E2E_EMBEDDING,
        source_id=str(seeded_source.id),
        file_hash="e2e-hash-abc123",
        collection_name=E2E_COLLECTION,
    )
    test_db_session.add(chunk)
    await test_db_session.commit()
    await test_db_session.refresh(chunk)
    return chunk, seeded_source
