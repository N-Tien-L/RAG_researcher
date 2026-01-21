"""Lightweight unit tests for ingestion helpers."""

import unittest

from app.ingestion.ingest import extract_youtube_video_id
from app.rag.chunking import chunk_text
from app.utils.text import standardize_text


class TestTextStandardization(unittest.TestCase):
    def test_standardize_text_collapses_whitespace(self) -> None:
        raw = "Hello\n\n\nWorld\u00ad!  \t"
        cleaned = standardize_text(raw)
        self.assertEqual(cleaned, "Hello\n\nWorld!")


class TestChunking(unittest.TestCase):
    def test_chunk_text_respects_max_tokens(self) -> None:
        text = "This is a short sentence. " * 50
        chunks = chunk_text(text, max_tokens=40, overlap=5)
        self.assertTrue(chunks)
        for chunk in chunks:
            self.assertLessEqual(len(chunk.split()), 60)  # coarse guard on size


class TestYouTubeExtraction(unittest.TestCase):
    def test_extracts_video_id_from_url(self) -> None:
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.assertEqual(extract_youtube_video_id(url), "dQw4w9WgXcQ")

    def test_handles_plain_id(self) -> None:
        self.assertEqual(extract_youtube_video_id("abcdefghijk"), "abcdefghijk")

    def test_returns_none_for_invalid(self) -> None:
        self.assertIsNone(extract_youtube_video_id("https://example.com"))


if __name__ == "__main__":
    unittest.main()
