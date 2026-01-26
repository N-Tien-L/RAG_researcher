"""Application-level ingestion orchestration."""

from typing import Any, Dict, Literal, Optional

from app.core.config import get_env
from app.core.logging import configure_logging
from app.embeddings.huggingface_tei import HuggingFaceTEIEmbedder
from app.ingestion.loaders import extract_from_pdf, extract_from_youtube
from app.rag.chunking import (
    chunk_extraction,
    chunk_pdf_extraction,
    chunk_youtube_extraction,
)
from app.utils.text import standardize_text
from app.vectorstore.chroma import get_collection

logger = configure_logging(__name__)


class IngestionService:
    def __init__(self, max_tokens: int = 300, overlap: int = 40):
        self.max_tokens = max_tokens
        self.overlap = overlap

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
    ) -> Dict[str, Any]:

        logger.info("Starting ingestion", extra={"source": source})

        if source_type == "pdf":
            extraction = extract_from_pdf(source)
        elif source_type == "youtube":
            extraction = extract_from_youtube(source)
        else:
            raise ValueError(f"Unsupported source_type: {source_type}")

        if extra_metadata:
            extraction["metadata"] = {
                **extraction.get("metadata", {}),
                **extra_metadata,
            }

        source_id = extraction["metadata"]["source"]
        chunks = self._prepare_chunks(extraction, source_id)

        embedder = HuggingFaceTEIEmbedder(
            base_url=get_env("TEI_URL", "http://localhost:8080"),
            max_batch_size=int(get_env("TEI_MAX_BATCH", "8")),
            mode=get_env("TEI_MODE", "passage"),
        )

        texts = [c["text"] for c in chunks]
        embeddings = embedder.embed_documents(texts)

        collection = get_collection(collection_name)

        collection.add(
            ids=[c["id"] for c in chunks],
            documents=texts,
            metadatas=[c["metadata"] for c in chunks],
            embeddings=embeddings,
        )

        logger.info(
            "Ingestion completed",
            extra={"chunks_added": len(chunks), "collection": collection_name},
        )

        return {
            "chunks_added": len(chunks),
            "collection": collection_name,
            "ids": [c["id"] for c in chunks],
        }
