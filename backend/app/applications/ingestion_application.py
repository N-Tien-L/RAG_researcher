"""Application-level orchestration for ingestion workflows."""

import hashlib
import time
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db import schemas
from app.embeddings.huggingface_tei import HuggingFaceTEIEmbedder
from app.ingestion.loaders import (
    PDFExtractionError,
    YouTubeExtractionError,
    extract_from_pdf,
    extract_from_youtube,
)
from app.rag.chunking import (
    chunk_extraction,
    chunk_pdf_extraction,
    chunk_youtube_extraction,
)
from app.observability.metrics import (
    record_database_query,
    record_embedding,
    record_ingestion_job,
)
from app.observability.tracing import add_span_event, trace_context_manager
from app.services.exceptions import (
    EmbeddingError,
    IngestionError,
    VectorStoreError,
    get_request_context_data,
)
from app.services.source_service import SourceService
from app.utils.text import standardize_text
from app.vectorstore.pgvector_store import (
    delete_chunks_by_source,
    get_existing_file_hash,
    insert_chunks,
)

logger = get_logger(__name__)


class IngestionApplicationService:
    """Orchestrates source ingestion: extraction, chunking, embedding, storage."""

    def __init__(self, db: AsyncSession, max_tokens: int = 300, overlap: int = 40) -> None:
        """Initialize ingestion orchestrator.
        
        Args:
            db: Async database session.
            max_tokens: Maximum tokens per chunk.
            overlap: Overlap tokens between chunks.
        """
        self.db = db
        self.max_tokens = max_tokens
        self.overlap = overlap
        self.source_service = SourceService(db)

    def _compute_content_hash(self, texts: list[str], source_type: str) -> str:
        """Compute a deterministic SHA-256 hash of post-chunked content.

        The hash incorporates the joined chunk texts, chunking parameters
        (``max_tokens``, ``overlap``), and ``source_type`` so that changing any
        chunking configuration invalidates the stored hash and triggers a
        re-ingestion on the next ``process_source`` call.

        Args:
            texts: List of chunk text strings produced by the chunker.
            source_type: Source type identifier (e.g. ``"pdf"``, ``"youtube"``).

        Returns:
            str: Hex-encoded SHA-256 digest.
        """
        payload = (
            "||".join(texts) +
            f"|max_tokens={self.max_tokens}|overlap={self.overlap}|source_type={source_type}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _compute_file_hash_from_extraction(self, extraction: dict[str, Any]) -> str:
        """Compute a SHA-256 hash of the raw extracted content before chunking.

        Detects the extraction format and concatenates the appropriate text
        fields:

        * **PDF** (``extraction["page_texts"]`` present): joins all page text
          values in order.
        * **YouTube** (``extraction["segments"]`` present): joins all segment
          ``"text"`` fields.
        * **Generic** (fallback): uses ``extraction.get("text", "")``.  

        Args:
            extraction: Raw extraction dict returned by a loader function
                (``extract_from_pdf`` or ``extract_from_youtube``).

        Returns:
            str: Hex-encoded SHA-256 digest of the combined raw text.
        """
        if "page_texts" in extraction:
            combined = "\n".join(extraction["page_texts"].values())
        elif "segments" in extraction:
            combined = "\n".join(seg.get("text", "") for seg in extraction["segments"])
        else:
            combined = extraction.get("text", "")
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def _compute_file_hash_from_path(self, source_path: str) -> str | None:
        """Compute SHA-256 from a source file path when available."""
        try:
            path = Path(source_path)
            if not path.is_file():
                return None

            digest = hashlib.sha256()
            with path.open("rb") as source_file:
                while True:
                    chunk = source_file.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
            return digest.hexdigest()
        except OSError:
            return None

    def _prepare_chunks(self, extraction: dict[str, Any], source_id: str) -> list[dict[str, Any]]:
        """Route extraction output to the appropriate chunker and return chunks.

        Dispatching logic:

        * ``source_type == "pdf"`` and ``"page_texts"`` key present
          -> :func:`app.rag.chunking.chunk_pdf_extraction`.
        * ``source_type == "youtube"`` and ``"segments"`` key present
          -> :func:`app.rag.chunking.chunk_youtube_extraction`.
        * All other cases -> :func:`app.rag.chunking.chunk_extraction`.

        Text in every case is first normalised with
        :func:`app.utils.text.standardize_text` before chunking.

        Args:
            extraction: Raw extraction dict (with ``metadata.source_type``).
            source_id: UUID string of the parent ``Source`` record; embedded in
                each chunk's metadata.

        Returns:
            list[dict]: List of chunk dicts, each containing at minimum
            ``"text"``, ``"source_id"``, ``"chunk_index"``, and
            ``"metadata"`` keys.
        """
        metadata = extraction.get("metadata", {})
        source_type = metadata.get("source_type")

        if source_type == "pdf" and "page_texts" in extraction:
            extraction["page_texts"] = {
                k: standardize_text(v or "")
                for k, v in extraction["page_texts"].items()
            }
            return chunk_pdf_extraction(
                extraction,
                max_tokens=self.max_tokens,
                overlap=self.overlap,
                source_id=source_id,
            )

        if source_type == "youtube" and "segments" in extraction:
            for seg in extraction["segments"]:
                seg["text"] = standardize_text(seg.get("text", ""))
            return chunk_youtube_extraction(
                extraction,
                max_tokens=self.max_tokens,
                source_id=source_id,
            )

        extraction["text"] = standardize_text(extraction.get("text", ""))
        return chunk_extraction(
            extraction,
            max_tokens=self.max_tokens,
            overlap=self.overlap,
            source_id=source_id,
        )

    async def process_source(
        self,
        source_id: str,
        source: str,
        source_type: Literal["pdf", "youtube"],
        extra_metadata: dict[str, Any] | None = None,
        *,
        source_uuid: str | None = None,
        source_key: str | None = None,
    ) -> dict[str, Any]:
        """Extract, chunk, embed, and store a source with smart re-ingestion.

        If the source's raw content hash matches the previously stored hash the
        job is marked ``'skipped'`` and no embeddings are recomputed.  If the
        hash differs, stale chunks are deleted before new ones are inserted.

        Args:
            source_id: UUID string of the ``Source`` database record.
            source: File path (PDF) or URL (YouTube) for the loader.
            source_type: ``"pdf"`` or ``"youtube"``.
            extra_metadata: Additional key/value pairs merged into each chunk's
                metadata (e.g. ``source_name``, ``source_uri``).
            source_uuid: UUID forwarded to chunk metadata for traceability.
            source_key: Stable deduplication key stored in chunk metadata.

        Returns:
            dict: ``{"chunks_added": int, "ids": list[str],
            "content_hash": str, "status": "ingested" | "skipped"}``.

        Raises:
            ValueError: If ``source_type`` is not ``"pdf"`` or ``"youtube"``.
            IngestionError: If extraction, chunking, or vector-store insertion
                fails.
            EmbeddingError: If the TEI embedding service is unreachable.
            VectorStoreError: If pgvector insertion fails.
        """
        logger.info("Starting ingestion", source=source, source_type=source_type)
        start_time = time.perf_counter()

        # Update source status to processing
        await self.source_service.update_source_status(
            source_id, schemas.SourceStatus.processing
        )

        try:
            with trace_context_manager(
                "ingestion.process_source",
                {
                    "source_id": source_id,
                    "source_type": source_type,
                },
            ):
                # Extract content
                try:
                    with trace_context_manager(
                        "ingestion.extract",
                        {"source_type": source_type},
                    ):
                        if source_type == "pdf":
                            extraction = extract_from_pdf(source)
                        elif source_type == "youtube":
                            extraction = extract_from_youtube(source)
                        else:
                            raise ValueError(f"Unsupported source_type: {source_type}")
                except (PDFExtractionError, YouTubeExtractionError) as exc:
                    raise IngestionError(
                        message=f"Failed to extract content from {source_type} source",
                        stage="extraction",
                        source_id=source_id,
                        **get_request_context_data(),
                    ) from exc

                # Merge metadata
                base_metadata = extraction.get("metadata", {})
                if extra_metadata:
                    base_metadata = {**base_metadata, **extra_metadata}

                if source_uuid:
                    base_metadata["source_uuid"] = source_uuid
                if source_key:
                    base_metadata["source_key"] = source_key

                extraction["metadata"] = base_metadata

                file_hash = self._compute_file_hash_from_extraction(extraction)
                if source_type == "pdf":
                    file_hash = self._compute_file_hash_from_path(source) or file_hash
                add_span_event("content_hash_computed", {"source_id": source_id})

                # Smart re-ingest logic
                existing_hash = await get_existing_file_hash(self.db, source_id)
                if existing_hash and existing_hash == file_hash:
                    logger.info("Source unchanged; skipping ingestion", source_id=source_id)
                    add_span_event("duplicate_detected", {"source_id": source_id})
                    await self.source_service.update_source_status(
                        source_id, schemas.SourceStatus.ready
                    )
                    record_ingestion_job(
                        source_type=source_type,
                        status="skipped",
                        duration_seconds=time.perf_counter() - start_time,
                        chunks_count=0,
                    )
                    return {
                        "chunks_added": 0,
                        "ids": [],
                        "content_hash": file_hash,
                        "status": "skipped",
                    }

                if existing_hash and existing_hash != file_hash:
                    deleted = await delete_chunks_by_source(self.db, source_id)
                    logger.info(
                        "Source modified; re-ingesting",
                        source_id=source_id,
                        deleted_chunks=deleted,
                    )

                # Chunk content
                try:
                    with trace_context_manager("ingestion.chunk"):
                        chunks = self._prepare_chunks(extraction, source_id)
                    add_span_event("chunks_prepared", {"chunks_count": len(chunks)})
                except Exception as exc:
                    raise IngestionError(
                        message="Failed to chunk extracted content",
                        stage="chunking",
                        source_id=source_id,
                        **get_request_context_data(),
                    ) from exc

                # Generate embeddings
                embedder = HuggingFaceTEIEmbedder(
                    base_url=settings.TEI_URL,
                    max_batch_size=settings.TEI_MAX_BATCH,
                    mode="passage",
                )

                texts = [c["text"] for c in chunks]
                try:
                    with trace_context_manager(
                        "ingestion.embed",
                        {"provider": "huggingface_tei", "mode": "passage"},
                    ):
                        embed_start = time.perf_counter()
                        embeddings = await embedder.embed_documents(texts)
                        embed_duration = time.perf_counter() - embed_start
                        record_embedding(
                            provider="huggingface_tei",
                            mode="passage",
                            duration_seconds=embed_duration,
                            batch_size=len(texts),
                        )
                except Exception as exc:
                    raise EmbeddingError(
                        message="Failed to generate embeddings for document chunks",
                        provider="huggingface_tei",
                        **get_request_context_data(),
                    ) from exc

                # Canonical source content hash is based on raw extracted content
                # so deduplication remains stable across chunking strategy changes.
                content_hash = file_hash

                # Insert chunks
                try:
                    with trace_context_manager("ingestion.store"):
                        store_start = time.perf_counter()
                        inserted = await insert_chunks(
                            self.db,
                            chunks=chunks,
                            embeddings=embeddings,
                            source_id=source_id,
                            file_hash=file_hash,
                        )
                        store_duration = time.perf_counter() - store_start
                        record_database_query("INSERT", "document_chunks", store_duration)
                except Exception as exc:
                    raise VectorStoreError(
                        message="Failed to insert chunks into vector store",
                        operation="insert",
                        **get_request_context_data(),
                    ) from exc

                logger.info(
                    "Ingestion completed",
                    chunks_added=inserted,
                )

                # Update source status and metadata
                await self.source_service.update_source_status(
                    source_id, schemas.SourceStatus.ready
                )

                record_ingestion_job(
                    source_type=source_type,
                    status="success",
                    duration_seconds=time.perf_counter() - start_time,
                    chunks_count=inserted,
                )

                return {
                    "chunks_added": inserted,
                    "ids": [c["id"] for c in chunks],
                    "content_hash": content_hash,
                    "status": "ingested",
                }

        except (IngestionError, EmbeddingError, VectorStoreError) as exc:
            logger.error(
                "Ingestion failed with known error",
                source_id=source_id,
                error_code=exc.error_code,
                error=str(exc),
            )
            await self.source_service.update_source_status(
                source_id, schemas.SourceStatus.failed
            )
            record_ingestion_job(
                source_type=source_type,
                status="failure",
                duration_seconds=time.perf_counter() - start_time,
                chunks_count=0,
            )
            raise
        except Exception as exc:
            logger.error(
                "Ingestion failed with unexpected error",
                source_id=source_id,
                error=str(exc),
                exc_info=True,
            )
            await self.source_service.update_source_status(
                source_id, schemas.SourceStatus.failed
            )
            record_ingestion_job(
                source_type=source_type,
                status="failure",
                duration_seconds=time.perf_counter() - start_time,
                chunks_count=0,
            )
            raise IngestionError(
                message="Unexpected error during ingestion",
                stage="unknown",
                source_id=source_id,
                **get_request_context_data(),
            ) from exc
