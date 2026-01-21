"""High-level RAG pipeline orchestration hooks."""

from typing import Any, Dict

from app.rag.chunking import (
    chunk_pdf_extraction,
    chunk_youtube_extraction,
    chunk_extraction,
)
from app.utils.text import standardize_text


class RagPipeline:
    """Lightweight placeholder pipeline tying extraction + chunking together."""

    def __init__(self, max_tokens: int = 300, overlap: int = 40) -> None:
        self.max_tokens = max_tokens
        self.overlap = overlap

    def prepare_document(self, extraction: Dict[str, Any], source_id=None):
        extraction = dict(extraction)
        metadata = extraction.get("metadata", {})
        source_type = metadata.get("source_type")

        # Standardize text depending on the structure of extraction
        if source_type == "pdf" and "page_texts" in extraction:
            page_texts = extraction.get("page_texts", {})
            extraction["page_texts"] = {
                page_num: standardize_text(text or "")
                for page_num, text in page_texts.items()
            }
            return chunk_pdf_extraction(
                extraction,
                max_tokens=self.max_tokens,
                overlap=self.overlap,
                source_id=source_id,
            )

        if source_type == "youtube" and "segments" in extraction:
            segments = extraction.get("segments", [])
            for seg in segments:
                if "text" in seg and seg["text"]:
                    seg["text"] = standardize_text(seg["text"])
            extraction["segments"] = segments
            return chunk_youtube_extraction(
                extraction,
                max_tokens=self.max_tokens,
                source_id=source_id,
            )

        # Fallback: flat text document
        text = extraction.get("text", "")
        extraction["text"] = standardize_text(text or "")
        return chunk_extraction(
            extraction,
            max_tokens=self.max_tokens,
            overlap=self.overlap,
            source_id=source_id,
        )

