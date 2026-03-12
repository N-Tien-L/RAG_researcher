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
    """Return the GPT-2 token count for *text*.

    Uses the module-level GPT-2 tokenizer for consistent token budgeting
    across all chunking functions.  Does not call any external service.

    Args:
        text: Input string to tokenise.

    Returns:
        int: Number of tokens in *text*.
    """
    return len(tokenizer.encode(text))


# -------------------------
# Generic token-aware chunker
# -------------------------

def chunk_text(
    text: str,
    max_tokens: int = 300,
    overlap: int = 40,
) -> List[str]:
    """Token-aware chunking for flat, unstructured text.

    Splits *text* on double-newline paragraph boundaries first.  Paragraphs
    that exceed ``max_tokens`` are further split at sentence boundaries
    (``[.!?]`` followed by whitespace).  Sentences that still exceed the
    budget are hard-truncated at ``max_tokens``.

    After flushing a chunk, the last ``overlap`` tokens are prepended to the
    next chunk so that semantic continuity is preserved across boundaries.
    Used as the fallback chunker for sources whose type is unknown.

    Args:
        text: Raw text to chunk.
        max_tokens: Maximum GPT-2 tokens allowed per chunk (default 300).
        overlap: Number of trailing tokens from the previous chunk to
            prepend to the next (default 40).

    Returns:
        list[str]: List of text chunk strings.
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
    """Chunk a PDF extraction dict while preserving page-number metadata.

    Iterates over ``extraction["page_texts"]`` in page order and calls
    ``chunk_text`` on each page's content.  Each chunk dict records the page
    number in ``metadata.page_start`` and ``metadata.page_end``.

    Args:
        extraction: Dict returned by :func:`app.ingestion.loaders.extract_from_pdf`.
            Must contain ``"page_texts"`` (``{page_num: str}``) and optionally
            ``"metadata"``.
        max_tokens: Maximum tokens per chunk (default 300).
        overlap: Overlap tokens between adjacent chunks (default 40).
        source_id: UUID string used to prefix chunk IDs
            (e.g. ``"{source_id}-chunk-0"``).  Falls back to metadata
            ``"source"`` then ``"pdf"``.

    Returns:
        list[dict]: Chunk dicts with keys ``"id"``, ``"text"``, and
        ``"metadata"`` (includes ``chunk_index``, ``page_start``,
        ``page_end``, plus all base metadata fields).
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
    """Chunk YouTube transcript segments while preserving start/end timestamps.

    Accumulates transcript ``segments`` until adding the next segment would
    exceed ``max_tokens``.  At that point the current window is flushed as a
    chunk and a new window begins.  Overlap is intentionally omitted to keep
    ``metadata.start_time`` / ``metadata.end_time`` accurate.

    Args:
        extraction: Dict returned by
            :func:`app.ingestion.loaders.extract_from_youtube`.  Must contain
            ``"segments"`` (list of ``{"text", "start", "duration"}`` dicts)
            and optionally ``"metadata"``.
        max_tokens: Maximum tokens per chunk (default 300).
        source_id: UUID string used to prefix chunk IDs.  Falls back to
            metadata ``"video_id"`` then ``"youtube"``.

    Returns:
        list[dict]: Chunk dicts with keys ``"id"``, ``"text"``, and
        ``"metadata"`` (includes ``chunk_index``, ``start_time``,
        ``end_time``, plus all base metadata fields).
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
    """Unified chunking entry point that dispatches by source type.

    Inspects ``extraction["metadata"]["source_type"]`` and routes to the
    most appropriate specialised chunker:

    * ``"pdf"`` with ``"page_texts"`` -> :func:`chunk_pdf_extraction`
    * ``"youtube"`` with ``"segments"`` -> :func:`chunk_youtube_extraction`
    * All other cases -> :func:`chunk_text` (flat-text fallback)

    Args:
        extraction: Raw extraction dict from any loader.  Must contain at
            least ``"metadata"`` and one of ``"page_texts"``, ``"segments"``,
            or ``"text"``.
        max_tokens: Maximum tokens per chunk (default 300).
        overlap: Overlap tokens between adjacent chunks (default 40).
            Ignored by the YouTube path.
        source_id: UUID string used to prefix chunk IDs.

    Returns:
        list[dict]: Chunk dicts with ``"id"``, ``"text"``, and ``"metadata"``
        keys.  Structure matches the output of the dispatched chunker.
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