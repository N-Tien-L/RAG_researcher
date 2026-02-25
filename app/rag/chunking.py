"""Chunking utilities to prepare text for embedding and storage."""
import re
from typing import Any, Dict, List, Optional

from transformers import AutoTokenizer

# Tokenizer is used ONLY for token budgeting
tokenizer = AutoTokenizer.from_pretrained("gpt2")


# -------------------------
# Token helpers
# -------------------------

def _count_tokens(text: str) -> int:
    """Count tokens for a given text."""
    return len(tokenizer.encode(text))


# -------------------------
# Generic token-aware chunker
# -------------------------

def chunk_text(
    text: str,
    max_tokens: int = 300,
    overlap: int = 40,
) -> List[str]:
    """
    Token-aware chunking for flat text.
    Used as a fallback for unknown sources.
    """

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
        para_tokens = _count_tokens(para)

        # Paragraph too large → split into sentences
        if para_tokens > max_tokens:
            sentences = [
                s.strip()
                for s in re.split(r"(?<=[.!?])\s+", para)
                if s.strip()
            ]

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

        if current_tokens + para_tokens > max_tokens:
            flush_chunk()

        current_parts.append(para)
        current_tokens += para_tokens

    if current_parts:
        chunks.append(" ".join(current_parts))

    return chunks


# -------------------------
# PDF-aware chunking
# -------------------------

def chunk_pdf_extraction(
    extraction: Dict[str, Any],
    max_tokens: int = 300,
    overlap: int = 40,
    source_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Chunk PDF extraction while preserving page numbers.
    """

    page_texts: Dict[int, str] = extraction.get("page_texts", {})
    base_metadata = extraction.get("metadata", {})
    doc_id = source_id or base_metadata.get("source") or "pdf"

    chunks: List[Dict[str, Any]] = []
    global_idx = 0

    for page_num, page_text in page_texts.items():
        page_chunks = chunk_text(
            page_text,
            max_tokens=max_tokens,
            overlap=overlap,
        )

        for chunk in page_chunks:
            chunks.append({
                "id": f"{doc_id}-chunk-{global_idx}",
                "text": chunk,
                "metadata": {
                    **base_metadata,
                    "chunk_index": global_idx,
                    "page_start": page_num,
                    "page_end": page_num,
                },
            })
            global_idx += 1

    return chunks


# -------------------------
# YouTube-aware chunking
# -------------------------

def chunk_youtube_extraction(
    extraction: Dict[str, Any],
    max_tokens: int = 300,
    # overlap: int = 40,            # YouTube chunking avoids token overlap to preserve accurate timestamps
    source_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Chunk YouTube transcripts while preserving timestamps.
    """

    segments = extraction.get("segments", [])
    base_metadata = extraction.get("metadata", {})
    doc_id = source_id or base_metadata.get("video_id") or "youtube"

    chunks: List[Dict[str, Any]] = []

    current_texts: List[str] = []
    current_tokens = 0
    start_time: Optional[float] = None
    global_idx = 0

    for seg in segments:
        seg_text = seg.get("text", "").strip()
        if not seg_text:
            continue

        seg_tokens = _count_tokens(seg_text)

        if start_time is None:
            start_time = seg["start"]

        if current_tokens + seg_tokens > max_tokens:
            end_time = seg["start"]

            chunks.append({
                "id": f"{doc_id}-chunk-{global_idx}",
                "text": " ".join(current_texts),
                "metadata": {
                    **base_metadata,
                    "chunk_index": global_idx,
                    "start_time": start_time,
                    "end_time": end_time,
                },
            })

            global_idx += 1
            current_texts = []
            current_tokens = 0
            start_time = seg["start"]

        current_texts.append(seg_text)
        current_tokens += seg_tokens

    if current_texts:
        last = segments[-1]
        chunks.append({
            "id": f"{doc_id}-chunk-{global_idx}",
            "text": " ".join(current_texts),
            "metadata": {
                **base_metadata,
                "chunk_index": global_idx,
                "start_time": start_time,
                "end_time": last["start"] + last["duration"],
            },
        })

    return chunks


# -------------------------
# Unified entry point
# -------------------------

def chunk_extraction(
    extraction: Dict[str, Any],
    max_tokens: int = 300,
    overlap: int = 40,
    source_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Unified chunking entry point.
    Automatically routes based on source type.
    """

    metadata = extraction.get("metadata", {})
    source_type = metadata.get("source_type")

    if source_type == "pdf" and "page_texts" in extraction:
        return chunk_pdf_extraction(
            extraction,
            max_tokens=max_tokens,
            overlap=overlap,
            source_id=source_id,
        )

    if source_type == "youtube" and "segments" in extraction:
        return chunk_youtube_extraction(
            extraction,
            max_tokens=max_tokens,
            source_id=source_id,
        )

    # Fallback: flat text
    text = extraction.get("text", "")
    base_metadata = metadata
    doc_id = source_id or base_metadata.get("source") or "doc"

    chunk_texts = chunk_text(text, max_tokens=max_tokens, overlap=overlap)
    chunks: List[Dict[str, Any]] = []

    for idx, chunk in enumerate(chunk_texts):
        chunks.append({
            "id": f"{doc_id}-chunk-{idx}",
            "text": chunk,
            "metadata": {**base_metadata, "chunk_index": idx},
        })

    return chunks