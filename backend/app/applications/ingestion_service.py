"""Application-level ingestion orchestration."""

import hashlib
from typing import Any, Dict, Literal, Optional

from app.core.config import get_env
from app.core.config import settings
from app.core.logging import configure_logging
from app.embeddings.huggingface_tei import HuggingFaceTEIEmbedder
from app.ingestion.loaders import extract_from_pdf, extract_from_youtube
from app.rag.chunking import (
    chunk_extraction,
    chunk_pdf_extraction,
    chunk_youtube_extraction,
)
from app.utils.text import standardize_text
from app.vectorstore.pgvector_store import (
    delete_chunks_by_source,
    get_existing_file_hash,
    insert_chunks,
)

logger = configure_logging(__name__)


class IngestionService:
    def __init__(self, max_tokens: int = 300, overlap: int = 40):
        self.max_tokens = max_tokens
        self.overlap = overlap

    def _compute_content_hash(self, texts: list[str], source_type: str) -> str:
        payload = "||".join(texts) + f"|max_tokens={self.max_tokens}|overlap={self.overlap}|source_type={source_type}"
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def _compute_file_hash_from_extraction(self, extraction: Dict[str, Any]) -> str:
        """Hash raw extracted content before chunking."""
        if "page_texts" in extraction:
            combined = "\n".join(extraction["page_texts"].values())
        elif "segments" in extraction:
            combined = "\n".join(seg.get("text", "") for seg in extraction["segments"])
        else:
            combined = extraction.get("text", "")
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def _prepare_chunks(self, extraction: Dict[str, Any], source_id: str):
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

    def ingest(
        self,
        source: str,
        source_type: Literal["pdf", "youtube"],
        collection_name: str = "documents",
        extra_metadata: Optional[Dict[str, Any]] = None,
        *,
        source_uuid: Optional[str] = None,
        source_key: Optional[str] = None,
        delete_existing: bool = False,
    ) -> Dict[str, Any]:

        logger.info("Starting ingestion", extra={"source": source})

        if source_type == "pdf":
            extraction = extract_from_pdf(source)
        elif source_type == "youtube":
            extraction = extract_from_youtube(source)
        else:
            raise ValueError(f"Unsupported source_type: {source_type}")

        base_metadata = extraction.get("metadata", {})
        if extra_metadata:
            base_metadata = {**base_metadata, **extra_metadata}

        if source_uuid:
            base_metadata["source_uuid"] = source_uuid
        if source_key:
            base_metadata["source_key"] = source_key

        extraction["metadata"] = base_metadata

        source_id = source_uuid or base_metadata.get("source") or source

        file_hash = self._compute_file_hash_from_extraction(extraction)

        # Smart re-ingest logic (pgvector-only)
        existing_hash = get_existing_file_hash(source_id)
        if existing_hash and existing_hash == file_hash:
            logger.info("Source unchanged; skipping ingestion", extra={"source_id": source_id})
            return {
                "chunks_added": 0,
                "collection": collection_name,
                "ids": [],
                "content_hash": file_hash,
                "status": "skipped",
            }

        if existing_hash and existing_hash != file_hash:
            deleted = delete_chunks_by_source(source_id)
            logger.info(
                "Source modified; re-ingesting",
                extra={"source_id": source_id, "deleted_chunks": deleted},
            )

        chunks = self._prepare_chunks(extraction, source_id)

        embedder = HuggingFaceTEIEmbedder(
            base_url=get_env("TEI_URL", "http://localhost:8080"),
            max_batch_size=int(get_env("TEI_MAX_BATCH", "8")),
            mode=get_env("TEI_MODE", "passage"),
        )

        texts = [c["text"] for c in chunks]
        embeddings = embedder._embed(texts, mode=embedder.mode)

        content_hash = self._compute_content_hash(texts, source_type)

        inserted = insert_chunks(
            chunks=chunks,
            embeddings=embeddings,
            source_id=source_id,
            file_hash=file_hash,
            collection_name=collection_name,
        )
        logger.info(
            "Ingestion completed (pgvector)",
            extra={"chunks_added": inserted, "collection": collection_name},
        )
        return {
            "chunks_added": inserted,
            "collection": collection_name,
            "ids": [c["id"] for c in chunks],
            "content_hash": content_hash,
            "status": "ingested",
        }
