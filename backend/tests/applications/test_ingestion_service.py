"""Unit tests for standalone IngestionService."""

from __future__ import annotations

import hashlib

import pytest

from app.applications.ingestion_service import IngestionService


class DummyEmbedder:
    """Minimal TEI embedder stub used by ingestion tests."""

    def __init__(self, *args, **kwargs):
        self.mode = kwargs.get("mode", "passage")

    def _embed(self, texts, mode="passage"):
        return [[0.1] * 4 for _ in texts]


def test_compute_content_hash_is_deterministic():
    service = IngestionService(max_tokens=300, overlap=40)
    texts = ["alpha", "beta"]

    first = service._compute_content_hash(texts, "pdf")
    second = service._compute_content_hash(texts, "pdf")

    assert first == second
    assert len(first) == 40


def test_compute_file_hash_from_pdf_extraction():
    service = IngestionService()
    extraction = {"page_texts": {1: "hello", 2: "world"}}

    actual = service._compute_file_hash_from_extraction(extraction)
    expected = hashlib.sha256("hello\nworld".encode("utf-8")).hexdigest()

    assert actual == expected


def test_compute_file_hash_from_youtube_extraction():
    service = IngestionService()
    extraction = {"segments": [{"text": "hello"}, {"text": "world"}]}

    actual = service._compute_file_hash_from_extraction(extraction)
    expected = hashlib.sha256("hello\nworld".encode("utf-8")).hexdigest()

    assert actual == expected


def test_compute_file_hash_from_plain_text_extraction():
    service = IngestionService()
    extraction = {"text": "plain body"}

    actual = service._compute_file_hash_from_extraction(extraction)
    expected = hashlib.sha256("plain body".encode("utf-8")).hexdigest()

    assert actual == expected


def test_prepare_chunks_pdf_branch(monkeypatch):
    service = IngestionService(max_tokens=250, overlap=30)

    captured = {}

    def fake_standardize(text):
        return text.strip().upper()

    def fake_chunk_pdf(extraction, max_tokens, overlap, source_id):
        captured["page_texts"] = extraction["page_texts"]
        captured["max_tokens"] = max_tokens
        captured["overlap"] = overlap
        captured["source_id"] = source_id
        return [{"id": "a", "text": "A"}]

    monkeypatch.setattr("app.applications.ingestion_service.standardize_text", fake_standardize)
    monkeypatch.setattr("app.applications.ingestion_service.chunk_pdf_extraction", fake_chunk_pdf)

    extraction = {
        "metadata": {"source_type": "pdf"},
        "page_texts": {1: " hello ", 2: " world "},
    }

    chunks = service._prepare_chunks(extraction, "src-1")

    assert chunks == [{"id": "a", "text": "A"}]
    assert captured["page_texts"] == {1: "HELLO", 2: "WORLD"}
    assert captured["max_tokens"] == 250
    assert captured["overlap"] == 30
    assert captured["source_id"] == "src-1"


def test_prepare_chunks_youtube_branch(monkeypatch):
    service = IngestionService(max_tokens=220)

    captured = {}

    def fake_standardize(text):
        return f"norm:{text.strip()}"

    def fake_chunk_youtube(extraction, max_tokens, source_id):
        captured["segments"] = extraction["segments"]
        captured["max_tokens"] = max_tokens
        captured["source_id"] = source_id
        return [{"id": "y", "text": "Y"}]

    monkeypatch.setattr("app.applications.ingestion_service.standardize_text", fake_standardize)
    monkeypatch.setattr("app.applications.ingestion_service.chunk_youtube_extraction", fake_chunk_youtube)

    extraction = {
        "metadata": {"source_type": "youtube"},
        "segments": [{"text": " a "}, {"text": " b "}],
    }

    chunks = service._prepare_chunks(extraction, "yt-1")

    assert chunks == [{"id": "y", "text": "Y"}]
    assert captured["segments"] == [{"text": "norm:a"}, {"text": "norm:b"}]
    assert captured["max_tokens"] == 220
    assert captured["source_id"] == "yt-1"


def test_prepare_chunks_fallback_branch(monkeypatch):
    service = IngestionService(max_tokens=100, overlap=10)

    captured = {}

    monkeypatch.setattr("app.applications.ingestion_service.standardize_text", lambda s: s.strip())

    def fake_chunk_generic(extraction, max_tokens, overlap, source_id):
        captured["text"] = extraction["text"]
        captured["max_tokens"] = max_tokens
        captured["overlap"] = overlap
        captured["source_id"] = source_id
        return [{"id": "g", "text": "G"}]

    monkeypatch.setattr("app.applications.ingestion_service.chunk_extraction", fake_chunk_generic)

    extraction = {"metadata": {"source_type": "text"}, "text": " hello "}
    chunks = service._prepare_chunks(extraction, "gen-1")

    assert chunks == [{"id": "g", "text": "G"}]
    assert captured["text"] == "hello"
    assert captured["max_tokens"] == 100
    assert captured["overlap"] == 10
    assert captured["source_id"] == "gen-1"


def test_ingest_raises_for_unsupported_source_type():
    service = IngestionService()

    with pytest.raises(ValueError, match="Unsupported source_type"):
        service.ingest("src", "audio")  # type: ignore[arg-type]


def test_ingest_returns_skipped_when_hash_unchanged(monkeypatch):
    service = IngestionService()
    extraction = {
        "metadata": {"source_type": "pdf"},
        "page_texts": {1: "same"},
    }

    monkeypatch.setattr("app.applications.ingestion_service.extract_from_pdf", lambda _: extraction)

    file_hash = service._compute_file_hash_from_extraction(extraction)
    monkeypatch.setattr("app.applications.ingestion_service.get_existing_file_hash", lambda _: file_hash)

    result = service.ingest("file.pdf", "pdf", source_uuid="src-uuid")

    assert result["status"] == "skipped"
    assert result["chunks_added"] == 0
    assert result["ids"] == []
    assert result["content_hash"] == file_hash


def test_ingest_reingests_when_hash_changes(monkeypatch):
    service = IngestionService()
    extraction = {
        "metadata": {"source_type": "pdf"},
        "page_texts": {1: "new"},
    }

    deleted_calls = {}
    inserted_calls = {}

    monkeypatch.setattr("app.applications.ingestion_service.extract_from_pdf", lambda _: extraction)
    monkeypatch.setattr("app.applications.ingestion_service.get_existing_file_hash", lambda _: "old-hash")
    monkeypatch.setattr(
        "app.applications.ingestion_service.delete_chunks_by_source",
        lambda source_id: deleted_calls.setdefault("source_id", source_id) or 3,
    )
    monkeypatch.setattr(
        "app.applications.ingestion_service.HuggingFaceTEIEmbedder",
        DummyEmbedder,
    )
    monkeypatch.setattr(
        "app.applications.ingestion_service.chunk_pdf_extraction",
        lambda *args, **kwargs: [{"id": "c1", "text": "chunk one"}],
    )

    def fake_insert(chunks, embeddings, source_id, file_hash):
        inserted_calls["chunks"] = chunks
        inserted_calls["embeddings"] = embeddings
        inserted_calls["source_id"] = source_id
        inserted_calls["file_hash"] = file_hash
        return 1

    monkeypatch.setattr("app.applications.ingestion_service.insert_chunks", fake_insert)

    result = service.ingest("file.pdf", "pdf", source_uuid="src-uuid", source_key="k1")

    assert deleted_calls["source_id"] == "src-uuid"
    assert inserted_calls["source_id"] == "src-uuid"
    assert inserted_calls["chunks"] == [{"id": "c1", "text": "chunk one"}]
    assert result["status"] == "ingested"
    assert result["chunks_added"] == 1
    assert result["ids"] == ["c1"]


def test_ingest_youtube_uses_extractor_and_extra_metadata(monkeypatch):
    service = IngestionService()

    extraction = {
        "metadata": {"source_type": "youtube", "source": "video-src"},
        "segments": [{"text": "seg a"}],
    }

    monkeypatch.setattr("app.applications.ingestion_service.extract_from_youtube", lambda _: extraction)
    monkeypatch.setattr("app.applications.ingestion_service.get_existing_file_hash", lambda _: None)
    monkeypatch.setattr("app.applications.ingestion_service.HuggingFaceTEIEmbedder", DummyEmbedder)
    monkeypatch.setattr(
        "app.applications.ingestion_service.chunk_youtube_extraction",
        lambda *args, **kwargs: [{"id": "y1", "text": "yt chunk"}],
    )
    monkeypatch.setattr(
        "app.applications.ingestion_service.insert_chunks",
        lambda **kwargs: 1,
    )

    result = service.ingest(
        "https://youtube.test/v",
        "youtube",
        extra_metadata={"foo": "bar"},
        source_key="yt-key",
    )

    assert extraction["metadata"]["foo"] == "bar"
    assert extraction["metadata"]["source_key"] == "yt-key"
    assert result["status"] == "ingested"
    assert result["chunks_added"] == 1
    assert result["ids"] == ["y1"]
