"""Unit tests for retrieval helpers and the RAG pipeline."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.rag import pipeline as pipeline_module
from app.rag import retrieval


def test_retrieve_chunks_formats_pgvector_response(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_results = [
        {"id": "c1", "text": "doc one", "metadata": {"page": 1}, "distance": 0.05},
        {"id": "c2", "text": "doc two", "metadata": {"page": 2}, "distance": 0.42},
    ]
    query_mock = AsyncMock(return_value=fake_results)
    monkeypatch.setattr(retrieval, "pgvector_query_chunks", query_mock)

    # Mock db session
    fake_db = MagicMock()
    
    embedding = [0.1, 0.2]
    where_filter = {"tag": "python"}
    chunks = asyncio.get_event_loop().run_until_complete(
        retrieval.retrieve_chunks(
            db=fake_db,
            embedding=embedding,
            collection_name="docs",
            top_k=2,
            where=where_filter,
        )
    )

    query_mock.assert_called_once_with(
        db=fake_db,
        embedding=embedding,
        collection_name="docs",
        top_k=2,
        where=where_filter,
    )
    assert chunks == fake_results


def test_retrieve_chunks_returns_empty_when_no_results(monkeypatch: pytest.MonkeyPatch) -> None:
    query_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(retrieval, "pgvector_query_chunks", query_mock)

    # Mock db session
    fake_db = MagicMock()
    
    chunks = asyncio.get_event_loop().run_until_complete(
        retrieval.retrieve_chunks(db=fake_db, embedding=[0.9], collection_name="docs")
    )

    query_mock.assert_called_once()
    assert chunks == []


def test_rag_pipeline_retrieve_invokes_embedder_and_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_embedder = AsyncMock()
    fake_embedder.embed_query.return_value = [0.77]
    monkeypatch.setattr(
        pipeline_module,
        "HuggingFaceTEIEmbedder",
        MagicMock(return_value=fake_embedder),
    )
    # Prevent real LLM client instantiation regardless of LLM_PROVIDER setting
    monkeypatch.setattr(pipeline_module, "ChatOllama", MagicMock())
    monkeypatch.setattr(pipeline_module, "KaggleChatModel", MagicMock())

    # Mock chunks with expected structure (dict with text, score, etc.)
    retrieved_chunks = [
        {"id": "c1", "text": "chunk-1", "score": 0.9, "metadata": {}},
        {"id": "c2", "text": "chunk-2", "score": 0.8, "metadata": {}},
    ]
    retrieve_mock = AsyncMock(return_value=retrieved_chunks)
    monkeypatch.setattr(pipeline_module, "retrieve_chunks", retrieve_mock)

    # Mock db session
    fake_db = MagicMock()
    
    pipeline = pipeline_module.RAGPipeline(top_k=7)
    result = asyncio.get_event_loop().run_until_complete(
        pipeline._retrieve_and_format(
            db=fake_db,
            query="What is RAG?",
            collection_name="docs",
            where=None,
        )
    )

    fake_embedder.embed_query.assert_called_once_with("What is RAG?")
    retrieve_mock.assert_called_once()
    
    # Verify result structure
    assert "context" in result
    assert "chunks" in result
    assert result["chunks"] == retrieved_chunks
