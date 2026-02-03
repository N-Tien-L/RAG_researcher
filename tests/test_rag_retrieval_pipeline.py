"""Unit tests for retrieval helpers and the RAG pipeline."""

from unittest.mock import MagicMock

import pytest

from app.rag import pipeline as pipeline_module
from app.rag import retrieval


def test_retrieve_chunks_formats_pgvector_response(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_results = [
        {"id": "c1", "text": "doc one", "metadata": {"page": 1}, "distance": 0.05},
        {"id": "c2", "text": "doc two", "metadata": {"page": 2}, "distance": 0.42},
    ]
    query_mock = MagicMock(return_value=fake_results)
    monkeypatch.setattr(retrieval, "pgvector_query_chunks", query_mock)

    embedding = [0.1, 0.2]
    where_filter = {"tag": "python"}
    chunks = retrieval.retrieve_chunks(
        embedding=embedding,
        collection_name="docs",
        top_k=2,
        where=where_filter,
    )

    query_mock.assert_called_once_with(
        embedding=embedding,
        collection_name="docs",
        top_k=2,
        where=where_filter,
    )
    assert chunks == fake_results


def test_retrieve_chunks_returns_empty_when_no_results(monkeypatch: pytest.MonkeyPatch) -> None:
    query_mock = MagicMock(return_value=[])
    monkeypatch.setattr(retrieval, "pgvector_query_chunks", query_mock)

    chunks = retrieval.retrieve_chunks(embedding=[0.9], collection_name="docs")

    query_mock.assert_called_once()
    assert chunks == []


def test_rag_pipeline_retrieve_invokes_embedder_and_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_embedder = MagicMock()
    fake_embedder.embed_query.return_value = [0.77]
    monkeypatch.setattr(
        pipeline_module,
        "HuggingFaceTEIEmbedder",
        MagicMock(return_value=fake_embedder),
    )
    monkeypatch.setattr(pipeline_module, "get_env", lambda key, default=None: default)

    retrieved_chunks = ["chunk-1", "chunk-2"]
    retrieve_mock = MagicMock(return_value=retrieved_chunks)
    monkeypatch.setattr(pipeline_module, "retrieve_chunks", retrieve_mock)

    pipeline = pipeline_module.RagPipeline(top_k=7)
    result = pipeline.retrieve("What is RAG?", collection_name="docs")

    fake_embedder.embed_query.assert_called_once_with("What is RAG?")
    retrieve_mock.assert_called_once_with(
        embedding=[0.77],
        collection_name="docs",
        top_k=7,
    )
    assert result == retrieved_chunks
