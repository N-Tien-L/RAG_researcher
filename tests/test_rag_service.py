"""Unit tests for the lightweight RagService wrapper."""

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage

from app.applications import rag_service as rag_service_module
from app.applications.rag_service import RagService


def _default_get_env(key: str, default: str | None = None) -> str | None:
    return default


def test_rag_service_answer_returns_llm_text_and_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.4]
    monkeypatch.setattr(
        rag_service_module,
        "HuggingFaceTEIEmbedder",
        MagicMock(return_value=embedder),
    )
    monkeypatch.setattr(rag_service_module, "get_env", _default_get_env)

    llm = MagicMock()
    llm.invoke.return_value = AIMessage(content="final answer")
    monkeypatch.setattr(rag_service_module, "ChatOllama", MagicMock(return_value=llm))

    chunks = [
        {"id": "chunk-1", "text": "alpha", "metadata": {"page": 1}},
        {"id": "chunk-2", "text": "beta", "metadata": {"page": 2}},
    ]
    retrieve_mock = MagicMock(return_value=chunks)
    monkeypatch.setattr(rag_service_module, "retrieve_chunks", retrieve_mock)
    monkeypatch.setattr(
        rag_service_module,
        "qa_prompt",
        lambda context, question: f"PROMPT::{question}::{context}",
    )

    service = RagService(top_k=2)
    response = service.answer("What is alpha?", collection_name="docs", where={"tag": "alpha"})

    embedder.embed_query.assert_called_once_with("What is alpha?")
    retrieve_mock.assert_called_once_with(
        embedding=[0.4],
        collection_name="docs",
        top_k=2,
        where={"tag": "alpha"},
    )
    llm.invoke.assert_called_once()
    assert response["answer"] == "final answer"
    assert response["sources"] == [
        {"chunk_id": "chunk-1", "metadata": {"page": 1}},
        {"chunk_id": "chunk-2", "metadata": {"page": 2}},
    ]


def test_rag_service_answer_returns_fallback_when_no_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1]
    monkeypatch.setattr(
        rag_service_module,
        "HuggingFaceTEIEmbedder",
        MagicMock(return_value=embedder),
    )
    monkeypatch.setattr(rag_service_module, "get_env", _default_get_env)

    llm = MagicMock()
    llm.invoke.side_effect = AssertionError("LLM should not be called when no chunks are found")
    monkeypatch.setattr(rag_service_module, "ChatOllama", MagicMock(return_value=llm))
    monkeypatch.setattr(rag_service_module, "qa_prompt", MagicMock(side_effect=AssertionError("No prompt")))

    retrieve_mock = MagicMock(return_value=[])
    monkeypatch.setattr(rag_service_module, "retrieve_chunks", retrieve_mock)

    service = RagService(top_k=3)
    response = service.answer("Any", collection_name="docs")

    embedder.embed_query.assert_called_once_with("Any")
    retrieve_mock.assert_called_once()
    assert response == {"answer": "I don't know.", "sources": []}
