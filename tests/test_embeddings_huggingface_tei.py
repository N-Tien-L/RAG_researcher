"""Unit tests for the HuggingFace text-embeddings inference client."""

import asyncio
from collections import deque
from typing import Iterable, List
from unittest.mock import AsyncMock, patch

import pytest

from app.embeddings import huggingface_tei
from app.embeddings.huggingface_tei import HuggingFaceTEIEmbedder


class _FakeResponse:
    def __init__(self, embeddings: Iterable[List[float]]):
        self._embeddings = list(embeddings)

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"data": [{"embedding": emb} for emb in self._embeddings]}


def test_embed_query_prefixes_payload_with_query_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_payloads = []

    def fake_post(url: str, json: dict, timeout: int):
        captured_payloads.append((url, json, timeout))
        return _FakeResponse([[0.1, 0.2, 0.3]])

    monkeypatch.setattr(huggingface_tei.requests, "post", fake_post)
    monkeypatch.setattr(huggingface_tei.settings, "REDIS_ENABLED", False)

    embedder = HuggingFaceTEIEmbedder(base_url="http://tei", timeout=5)
    vector = asyncio.get_event_loop().run_until_complete(embedder.embed_query("hello world"))

    assert vector == [0.1, 0.2, 0.3]
    assert captured_payloads == [
        ("http://tei/v1/embeddings", {"input": ["query: hello world"]}, 5)
    ]


def test_embed_documents_batches_by_max_size(monkeypatch: pytest.MonkeyPatch) -> None:
    payload_inputs = []
    embeddings_queue = deque([[0.1], [0.2], [0.3]])

    def fake_post(url: str, json: dict, timeout: int):
        batch_embeddings = [embeddings_queue.popleft() for _ in json["input"]]
        payload_inputs.append(json["input"])
        return _FakeResponse(batch_embeddings)

    monkeypatch.setattr(huggingface_tei.requests, "post", fake_post)
    monkeypatch.setattr(huggingface_tei.settings, "REDIS_ENABLED", False)

    embedder = HuggingFaceTEIEmbedder(base_url="http://tei", max_batch_size=2, mode="passage")
    vectors = asyncio.get_event_loop().run_until_complete(
        embedder.embed_documents(["Document A", "Document B", "Document C"])
    )

    assert len(vectors) == 3
    assert payload_inputs == [
        ["passage: Document A", "passage: Document B"],
        ["passage: Document C"],
    ]
