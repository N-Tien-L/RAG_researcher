"""High-level RAG pipeline orchestration hooks."""

from typing import Any, Dict, List, Optional

from app.rag.chunking import chunk_extraction
from app.utils.text import standardize_text


class RagPipeline:
    """Lightweight placeholder pipeline tying extraction + chunking together."""

    def __init__(self, max_tokens: int = 300, overlap: int = 40) -> None:
        self.max_tokens = max_tokens
        self.overlap = overlap

    def prepare_document(
        self, extraction: Dict[str, Any], source_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Standardize text then chunk into structured payloads."""

        standardized = standardize_text(extraction.get("text", ""))
        normalized = dict(extraction)
        normalized["text"] = standardized
        return chunk_extraction(
            normalized, max_tokens=self.max_tokens, overlap=self.overlap, source_id=source_id
        )
