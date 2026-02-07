"""Application-level orchestration for ingestion workflows."""

import hashlib
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
        """Compute hash of chunked content."""
        payload = (
            "||".join(texts) +
            f"|max_tokens={self.max_tokens}|overlap={self.overlap}|source_type={source_type}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _compute_file_hash_from_extraction(self, extraction: dict[str, Any]) -> str:
        """Hash raw extracted content before chunking."""
        if "page_texts" in extraction:
            combined = "\n".join(extraction["page_texts"].values())
        elif "segments" in extraction:
            combined = "\n".join(seg.get("text", "") for seg in extraction["segments"])
        else:
            combined = extraction.get("text", "")
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def _prepare_chunks(self, extraction: dict[str, Any], source_id: str) -> list[dict[str, Any]]:
        """Prepare chunks based on source type."""
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
        collection_name: str = "documents",
        extra_metadata: dict[str, Any] | None = None,
        *,
        source_uuid: str | None = None,
        source_key: str | None = None,
    ) -> dict[str, Any]:
        """Process and ingest a source with smart re-import logic.
        
        Args:
            source_id: UUID string of Source record.
            source: Path or URL to source.
            source_type: Type of source ('pdf' or 'youtube').
            collection_name: Collection/namespace name.
            extra_metadata: Additional metadata.
            source_uuid: UUID for tracking.
            source_key: Stable key for deduplication.
            
        Returns:
            Dictionary with ingestion results.
            
        Raises:
            ValueError: If source_type is unsupported.
        """
        logger.info("Starting ingestion", source=source, source_type=source_type)

        # Update source status to processing
        await self.source_service.update_source_status(
            source_id, schemas.SourceStatus.processing
        )

        try:
            # Extract content
            try:
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

            # Smart re-ingest logic
            existing_hash = await get_existing_file_hash(self.db, source_id)
            if existing_hash and existing_hash == file_hash:
                logger.info("Source unchanged; skipping ingestion", source_id=source_id)
                await self.source_service.update_source_status(
                    source_id, schemas.SourceStatus.ready
                )
                return {
                    "chunks_added": 0,
                    "collection": collection_name,
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
                chunks = self._prepare_chunks(extraction, source_id)
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
            # embed_documents is now async with built-in caching
            try:
                embeddings = await embedder.embed_documents(texts)
            except Exception as exc:
                raise EmbeddingError(
                    message="Failed to generate embeddings for document chunks",
                    provider="huggingface_tei",
                    **get_request_context_data(),
                ) from exc

            content_hash = self._compute_content_hash(texts, source_type)

            # Insert chunks
            try:
                inserted = await insert_chunks(
                    self.db,
                    chunks=chunks,
                    embeddings=embeddings,
                    source_id=source_id,
                    file_hash=file_hash,
                    collection_name=collection_name,
                )
            except Exception as exc:
                raise VectorStoreError(
                    message="Failed to insert chunks into vector store",
                    operation="insert",
                    **get_request_context_data(),
                ) from exc

            logger.info(
                "Ingestion completed",
                chunks_added=inserted,
                collection=collection_name,
            )

            # Update source status and metadata
            await self.source_service.update_source_status(
                source_id, schemas.SourceStatus.ready
            )

            return {
                "chunks_added": inserted,
                "collection": collection_name,
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
            raise IngestionError(
                message="Unexpected error during ingestion",
                stage="unknown",
                source_id=source_id,
                **get_request_context_data(),
            ) from exc
