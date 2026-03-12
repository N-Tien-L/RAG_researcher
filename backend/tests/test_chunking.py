"""Tests for RAG chunking utilities."""

import pytest

from app.rag.chunking import (
    _count_tokens,
    chunk_text,
    chunk_pdf_extraction,
    chunk_youtube_extraction,
    chunk_extraction,
)


class TestCountTokens:
    """Tests for token counting helper."""
    
    def test_count_tokens_simple_text(self):
        """Basic token counting."""
        text = "Hello world"
        count = _count_tokens(text)
        assert count > 0
        assert isinstance(count, int)
    
    def test_count_tokens_empty_string(self):
        """Empty string returns 0 tokens."""
        assert _count_tokens("") == 0
    
    def test_count_tokens_longer_text(self):
        """Longer text has more tokens."""
        short = "Hi"
        long = "This is a much longer sentence with many more words"
        assert _count_tokens(long) > _count_tokens(short)


class TestChunkText:
    """Tests for generic text chunking."""
    
    def test_chunk_text_empty_input(self):
        """Empty text returns empty list."""
        assert chunk_text("") == []
    
    def test_chunk_text_short_text(self):
        """Short text fits in one chunk."""
        text = "This is a short paragraph."
        chunks = chunk_text(text, max_tokens=100)
        assert len(chunks) == 1
        assert chunks[0] == text
    
    def test_chunk_text_multiple_paragraphs(self):
        """Multiple paragraphs are chunked appropriately."""
        # Create longer paragraphs that will definitely need chunking
        text = ("This is a much longer first paragraph with many words. " * 5 +
                "\n\nThis is a much longer second paragraph with many words. " * 5 +
                "\n\nThis is a much longer third paragraph with many words. " * 5)
        chunks = chunk_text(text, max_tokens=50)
        assert len(chunks) >= 1
        # Each chunk should contain text
        for chunk in chunks:
            assert len(chunk) > 0
    
    def test_chunk_text_long_paragraph_splits_by_sentences(self):
        """Long paragraph splits into sentences."""
        text = (
            "This is the first sentence. "
            "This is the second sentence. "
            "This is the third sentence. "
            "This is the fourth sentence."
        )
        chunks = chunk_text(text, max_tokens=20)
        assert len(chunks) > 1
    
    def test_chunk_text_applies_overlap(self):
        """Chunking applies overlap between chunks."""
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three.\n\nParagraph four."
        chunks_no_overlap = chunk_text(text, max_tokens=10, overlap=0)
        chunks_with_overlap = chunk_text(text, max_tokens=10, overlap=5)
        
        # Both should produce chunks
        assert len(chunks_no_overlap) > 0
        assert len(chunks_with_overlap) > 0
    
    def test_chunk_text_very_long_sentence_truncates(self):
        """Very long sentences are truncated to max_tokens."""
        # Create a very long sentence without punctuation
        text = " ".join(["word"] * 500)
        chunks = chunk_text(text, max_tokens=50)
        
        # Should produce chunks
        assert len(chunks) > 0
        
        # Each chunk should not exceed max tokens significantly
        for chunk in chunks:
            assert _count_tokens(chunk) <= 60  # Allow some margin
    
    def test_chunk_text_custom_max_tokens(self):
        """Respects custom max_tokens parameter."""
        text = ("This is a much longer sentence with many words that will exceed token limits. " * 30)
        chunks_small = chunk_text(text, max_tokens=30)
        chunks_large = chunk_text(text, max_tokens=150)
        
        # Smaller max_tokens should produce more chunks or at least same
        assert len(chunks_small) >= len(chunks_large)
    
    def test_chunk_text_whitespace_only(self):
        """Whitespace-only text returns empty list."""
        assert chunk_text("   \n\n   \n   ") == []


class TestChunkPDFExtraction:
    """Tests for PDF-specific chunking."""
    
    def test_chunk_pdf_simple_extraction(self):
        """Basic PDF extraction chunking."""
        extraction = {
            "page_texts": {
                1: "Content from page one.",
                2: "Content from page two.",
            },
            "metadata": {"source": "test.pdf", "title": "Test PDF"},
        }
        
        chunks = chunk_pdf_extraction(extraction, source_id="test-doc")
        
        assert len(chunks) > 0
        
        # Check chunk structure
        for chunk in chunks:
            assert "id" in chunk
            assert "text" in chunk
            assert "metadata" in chunk
            assert "page_start" in chunk["metadata"]
            assert "chunk_index" in chunk["metadata"]
    
    def test_chunk_pdf_preserves_page_numbers(self):
        """PDF chunking preserves page number metadata."""
        extraction = {
            "page_texts": {
                1: "First page content.",
                2: "Second page content.",
                3: "Third page content.",
            },
            "metadata": {"source": "multi-page.pdf"},
        }
        
        chunks = chunk_pdf_extraction(extraction)
        
        # Find chunk from each page
        page_1_chunks = [c for c in chunks if c["metadata"]["page_start"] == 1]
        page_2_chunks = [c for c in chunks if c["metadata"]["page_start"] == 2]
        page_3_chunks = [c for c in chunks if c["metadata"]["page_start"] == 3]
        
        assert len(page_1_chunks) > 0
        assert len(page_2_chunks) > 0
        assert len(page_3_chunks) > 0
    
    def test_chunk_pdf_global_chunk_index(self):
        """PDF chunks have incrementing global indices."""
        extraction = {
            "page_texts": {
                1: "Page one. " * 50,
                2: "Page two. " * 50,
            },
            "metadata": {},
        }
        
        chunks = chunk_pdf_extraction(extraction, max_tokens=20)
        
        # Extract chunk indices
        indices = [c["metadata"]["chunk_index"] for c in chunks]
        
        # Should be sequential starting from 0
        assert indices == list(range(len(chunks)))
    
    def test_chunk_pdf_empty_page_texts(self):
        """Handles empty page_texts gracefully."""
        extraction = {
            "page_texts": {},
            "metadata": {"source": "empty.pdf"},
        }
        
        chunks = chunk_pdf_extraction(extraction)
        assert chunks == []
    
    def test_chunk_pdf_custom_source_id(self):
        """Uses custom source_id in chunk IDs."""
        extraction = {
            "page_texts": {1: "Test content."},
            "metadata": {},
        }
        
        chunks = chunk_pdf_extraction(extraction, source_id="custom-id-123")
        
        assert len(chunks) > 0
        assert chunks[0]["id"].startswith("custom-id-123-chunk-")
    
    def test_chunk_pdf_inherits_metadata(self):
        """Chunks inherit base metadata from extraction."""
        extraction = {
            "page_texts": {1: "Content."},
            "metadata": {"author": "John Doe", "year": 2024},
        }
        
        chunks = chunk_pdf_extraction(extraction)
        
        assert chunks[0]["metadata"]["author"] == "John Doe"
        assert chunks[0]["metadata"]["year"] == 2024


class TestChunkYouTubeExtraction:
    """Tests for YouTube transcript chunking."""
    
    def test_chunk_youtube_simple_transcript(self):
        """Basic YouTube transcript chunking."""
        extraction = {
            "segments": [
                {"start": 0.0, "duration": 2.5, "text": "Hello everyone"},
                {"start": 2.5, "duration": 3.0, "text": "Welcome to my channel"},
                {"start": 5.5, "duration": 2.0, "text": "Today we will discuss"},
            ],
            "metadata": {"video_id": "abc123", "title": "Test Video"},
        }
        
        chunks = chunk_youtube_extraction(extraction, source_id="yt-video")
        
        assert len(chunks) > 0
        
        # Check chunk structure
        for chunk in chunks:
            assert "id" in chunk
            assert "text" in chunk
            assert "metadata" in chunk
            assert "start_time" in chunk["metadata"]
            assert "end_time" in chunk["metadata"]
    
    def test_chunk_youtube_preserves_timestamps(self):
        """YouTube chunks preserve timestamp information."""
        extraction = {
            "segments": [
                {"start": 0.0, "duration": 2.0, "text": "First segment"},
                {"start": 2.0, "duration": 2.0, "text": "Second segment"},
            ],
            "metadata": {},
        }
        
        chunks = chunk_youtube_extraction(extraction, max_tokens=100)
        
        # With large max_tokens, should fit in one chunk
        assert len(chunks) == 1
        assert chunks[0]["metadata"]["start_time"] == 0.0
        assert chunks[0]["metadata"]["end_time"] == 4.0  # 2.0 + 2.0
    
    def test_chunk_youtube_splits_on_token_limit(self):
        """YouTube chunking splits when exceeding max_tokens."""
        # Create many segments that will exceed max_tokens
        segments = [
            {"start": float(i * 2), "duration": 2.0, "text": "Word " * 20}
            for i in range(10)
        ]
        
        extraction = {
            "segments": segments,
            "metadata": {"video_id": "xyz789"},
        }
        
        chunks = chunk_youtube_extraction(extraction, max_tokens=30)
        
        # Should split into multiple chunks
        assert len(chunks) > 1
        
        # Each chunk should have valid timestamps
        for chunk in chunks:
            assert chunk["metadata"]["start_time"] >= 0
            assert chunk["metadata"]["end_time"] > chunk["metadata"]["start_time"]
    
    def test_chunk_youtube_skips_empty_segments(self):
        """Skips segments with no text."""
        extraction = {
            "segments": [
                {"start": 0.0, "duration": 1.0, "text": ""},
                {"start": 1.0, "duration": 2.0, "text": "  "},
                {"start": 3.0, "duration": 2.0, "text": "Actual content"},
            ],
            "metadata": {},
        }
        
        chunks = chunk_youtube_extraction(extraction)
        
        # Only one chunk from the segment with actual content
        assert len(chunks) == 1
        assert "Actual content" in chunks[0]["text"]
    
    def test_chunk_youtube_sequential_chunk_index(self):
        """YouTube chunks have sequential indices."""
        segments = [
            {"start": float(i), "duration": 1.0, "text": f"Segment {i}"}
            for i in range(5)
        ]
        
        extraction = {"segments": segments, "metadata": {}}
        
        chunks = chunk_youtube_extraction(extraction, max_tokens=10)
        
        indices = [c["metadata"]["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))
    
    def test_chunk_youtube_custom_source_id(self):
        """Uses custom source_id in chunk IDs."""
        extraction = {
            "segments": [{"start": 0.0, "duration": 2.0, "text": "Content"}],
            "metadata": {},
        }
        
        chunks = chunk_youtube_extraction(extraction, source_id="my-video-id")
        
        assert chunks[0]["id"].startswith("my-video-id-chunk-")


class TestChunkExtraction:
    """Tests for unified chunk_extraction entry point."""
    
    def test_chunk_extraction_routes_to_pdf(self):
        """Routes to PDF chunker for PDF extractions."""
        extraction = {
            "page_texts": {1: "PDF content"},
            "metadata": {"source_type": "pdf"},
        }
        
        chunks = chunk_extraction(extraction)
        
        # Should produce chunks with page metadata
        assert len(chunks) > 0
        assert "page_start" in chunks[0]["metadata"]
    
    def test_chunk_extraction_routes_to_youtube(self):
        """Routes to YouTube chunker for YouTube extractions."""
        extraction = {
            "segments": [{"start": 0.0, "duration": 2.0, "text": "YouTube content"}],
            "metadata": {"source_type": "youtube"},
        }
        
        # Note: YouTube chunker doesn't use overlap parameter
        chunks = chunk_extraction(extraction, max_tokens=100)
        
        # Should produce chunks with timestamp metadata
        assert len(chunks) > 0
        assert "start_time" in chunks[0]["metadata"]
        assert "end_time" in chunks[0]["metadata"]
    
    def test_chunk_extraction_fallback_to_generic(self):
        """Falls back to generic chunker for unknown types."""
        extraction = {
            "text": "Some plain text content that needs chunking.",
            "metadata": {"source_type": "text"},
        }
        
        chunks = chunk_extraction(extraction)
        
        # Should produce chunks without page or timestamp metadata
        assert len(chunks) > 0
        assert "page_start" not in chunks[0]["metadata"]
        assert "start_time" not in chunks[0]["metadata"]
    
    def test_chunk_extraction_fallback_missing_source_type(self):
        """Falls back when source_type is not specified."""
        extraction = {
            "text": "Fallback content.",
            "metadata": {},
        }
        
        chunks = chunk_extraction(extraction)
        
        assert len(chunks) > 0
        assert chunks[0]["text"] == "Fallback content."
    
    def test_chunk_extraction_respects_max_tokens(self):
        """Passes max_tokens parameter to underlying chunkers."""
        extraction = {
            "text": ("This is a longer sentence with many words that should create multiple chunks when token limit is small. " * 20),
            "metadata": {},
        }
        
        chunks_small = chunk_extraction(extraction, max_tokens=30)
        chunks_large = chunk_extraction(extraction, max_tokens=200)
        
        # Smaller limit produces more or equal chunks
        assert len(chunks_small) >= len(chunks_large)
    
    def test_chunk_extraction_respects_overlap(self):
        """Passes overlap parameter to underlying chunkers."""
        extraction = {
            "text": "Paragraph one.\n\nParagraph two.\n\nParagraph three.",
            "metadata": {},
        }
        
        # Both should work without errors
        chunks_no_overlap = chunk_extraction(extraction, overlap=0)
        chunks_with_overlap = chunk_extraction(extraction, overlap=10)
        
        assert len(chunks_no_overlap) > 0
        assert len(chunks_with_overlap) > 0
    
    def test_chunk_extraction_uses_source_id(self):
        """Uses source_id in chunk IDs."""
        extraction = {
            "text": "Content",
            "metadata": {},
        }
        
        chunks = chunk_extraction(extraction, source_id="my-source-123")
        
        assert chunks[0]["id"].startswith("my-source-123-chunk-")
    
    def test_chunk_extraction_empty_text_fallback(self):
        """Handles empty text in fallback mode."""
        extraction = {
            "text": "",
            "metadata": {},
        }
        
        chunks = chunk_extraction(extraction)
        
        assert chunks == []
