"""Unit tests for ingestion helpers with isolated external dependencies."""

from __future__ import annotations

from typing import Dict, List
from unittest.mock import MagicMock

import pytest
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled, VideoUnavailable

from app.ingestion import loaders
from app.ingestion.loaders import YouTubeExtractionError, _extract_youtube_video_id
from app.rag.chunking import chunk_text
from app.utils.text import standardize_text


# -------------------------------------------------------------------------------------------------
# Text utilities
# -------------------------------------------------------------------------------------------------

def test_standardize_text_collapses_whitespace_and_soft_hyphen() -> None:
    raw = "Hello\n\n\nWorld\u00ad!  \t"
    cleaned = standardize_text(raw)
    assert cleaned == "Hello\n\nWorld!"


def test_standardize_text_strips_control_chars() -> None:
    raw = "A\x00B\nC\x1f"
    cleaned = standardize_text(raw)
    assert cleaned == "AB\nC"
    assert "\x00" not in cleaned and "\x1f" not in cleaned


# -------------------------------------------------------------------------------------------------
# Chunking utilities
# -------------------------------------------------------------------------------------------------

def test_chunk_text_returns_empty_for_blank_input() -> None:
    assert chunk_text("") == []


def test_chunk_text_generates_chunks_under_token_budget() -> None:
    text = "This is a short sentence." * 20
    chunks = chunk_text(text, max_tokens=40, overlap=10)
    assert chunks, "Expected at least one chunk"
    assert all(len(chunk.split()) <= 80 for chunk in chunks)


# -------------------------------------------------------------------------------------------------
# YouTube helpers
# -------------------------------------------------------------------------------------------------

@pytest.fixture
def transcript_segments() -> List[Dict[str, object]]:
    return [
        {"text": "Hello", "start": 0.0, "duration": 2.5},
        {"text": "world", "start": 2.5, "duration": 2.5},
    ]


@pytest.fixture
def mock_transcript_api(monkeypatch: pytest.MonkeyPatch, transcript_segments: List[Dict[str, object]]):
    mock_transcript = MagicMock()
    mock_transcript.to_raw_data.return_value = transcript_segments
    mock_transcript.language_code = "en"
    mock_transcript.is_generated = False

    mock_api = MagicMock()
    mock_api.fetch.return_value = mock_transcript

    api_ctor = MagicMock(return_value=mock_api)
    monkeypatch.setattr(loaders, "YouTubeTranscriptApi", api_ctor)

    return mock_api, mock_transcript


def test_extract_youtube_video_id_supports_common_variants() -> None:
    assert _extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _extract_youtube_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _extract_youtube_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_youtube_video_id_rejects_invalid() -> None:
    assert _extract_youtube_video_id("https://example.com") is None
    assert _extract_youtube_video_id("short") is None


def test_extract_from_youtube_returns_structured_payload(mock_transcript_api, transcript_segments):
    _, mock_transcript = mock_transcript_api
    result = loaders.extract_from_youtube("https://www.youtube.com/watch?v=abcdefghijk")

    assert result["text"] == "Hello world"
    assert result["segments"] == transcript_segments
    assert result["metadata"]["video_id"] == "abcdefghijk"
    assert result["metadata"]["segment_count"] == len(transcript_segments)
    expected_duration = transcript_segments[-1]["start"] + transcript_segments[-1]["duration"]
    assert result["metadata"]["duration_seconds"] == expected_duration
    assert result["metadata"]["video_url"].endswith("abcdefghijk")
    assert result["metadata"]["language"] == mock_transcript.language_code


def test_extract_from_youtube_with_plain_id(mock_transcript_api):
    mock_api, _ = mock_transcript_api
    loaders.extract_from_youtube("abcdefghijk", languages=["es"])
    mock_api.fetch.assert_called_once_with("abcdefghijk", languages=["es"])


def test_extract_from_youtube_defaults_language(mock_transcript_api):
    mock_api, _ = mock_transcript_api
    loaders.extract_from_youtube("https://youtu.be/abcdefghijk")
    mock_api.fetch.assert_called_once_with("abcdefghijk", languages=["en"])


@pytest.mark.parametrize(
    "error, message",
    [
        (TranscriptsDisabled("abc"), "Transcripts disabled"),
        (VideoUnavailable("abc"), "Video unavailable"),
        (NoTranscriptFound("abc", ["en"], {}), "No transcript found"),
    ],
)
def test_extract_from_youtube_maps_known_errors(monkeypatch: pytest.MonkeyPatch, error: Exception, message: str):
    mock_api = MagicMock()
    mock_api.fetch.side_effect = error
    monkeypatch.setattr(loaders, "YouTubeTranscriptApi", MagicMock(return_value=mock_api))

    with pytest.raises(YouTubeExtractionError, match=message):
        loaders.extract_from_youtube("abcdefghijk")


def test_extract_from_youtube_rejects_invalid_urls() -> None:
    with pytest.raises(YouTubeExtractionError, match="Invalid YouTube URL"):
        loaders.extract_from_youtube("https://example.com")
