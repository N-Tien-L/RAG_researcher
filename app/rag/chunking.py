"""Chunking utilities to prepare text for embedding and storage."""

import re
from typing import Any, Dict, List, Optional

from transformers import AutoTokenizer

# Use a lightweight tokenizer for token counting only.
tokenizer = AutoTokenizer.from_pretrained("gpt2")


def _count_tokens(text: str) -> int:
    """Count tokens for a given text using the configured tokenizer."""
    return len(tokenizer.encode(text))


def chunk_text(text: str, max_tokens: int = 300, overlap: int = 40) -> List[str]:
    """Token-aware chunking that plays nicely with extraction outputs."""

    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    current_parts: List[str] = []
    current_tokens = 0

    def flush_chunk() -> None:
        nonlocal current_parts, current_tokens
        if current_parts:
            chunks.append(" ".join(current_parts))
        if overlap and current_parts:
            overlap_tokens = tokenizer.encode(" ".join(current_parts))[-overlap:]
            current_parts = [tokenizer.decode(overlap_tokens)]
            current_tokens = len(overlap_tokens)
        else:
            current_parts = []
            current_tokens = 0

    for para in paragraphs:
        para_token_len = _count_tokens(para)

        if para_token_len > max_tokens:
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", para) if s.strip()]
            for sent in sentences:
                sent_tokens = _count_tokens(sent)
                if sent_tokens > max_tokens:
                    tokens = tokenizer.encode(sent)[:max_tokens]
                    sent = tokenizer.decode(tokens)
                    sent_tokens = len(tokens)

                if current_tokens + sent_tokens > max_tokens:
                    flush_chunk()

                current_parts.append(sent)
                current_tokens += sent_tokens
            continue

        if current_tokens + para_token_len > max_tokens:
            flush_chunk()

        current_parts.append(para)
        current_tokens += para_token_len

    if current_parts:
        chunks.append(" ".join(current_parts))

    return chunks


def chunk_extraction(
    extraction: Dict[str, Any],
    max_tokens: int = 300,
    overlap: int = 40,
    source_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Chunk an extraction result (from PDF or YouTube) into structured chunks."""

    text = extraction.get("text", "") if extraction else ""
    base_metadata = extraction.get("metadata", {}) if extraction else {}
    doc_id = source_id or base_metadata.get("source") or "doc"

    chunk_texts = chunk_text(text, max_tokens=max_tokens, overlap=overlap)
    chunks: List[Dict[str, Any]] = []

    for idx, chunk in enumerate(chunk_texts):
        chunk_meta = {**base_metadata, "chunk_index": idx}
        chunks.append({"id": f"{doc_id}-chunk-{idx}", "text": chunk, "metadata": chunk_meta})

    return chunks
