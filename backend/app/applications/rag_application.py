"""Application-level RAG orchestration combining retrieval and generation."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db import schemas as db_schemas
from app.rag.pipeline import RAGPipeline

logger = get_logger(__name__)


class RAGApplicationService:
    """Orchestrates RAG queries: handles pipeline initialization and execution."""

    def __init__(self, db: AsyncSession, top_k: int = 5) -> None:
        """Initialize RAG application service.
        
        Args:
            db: Async database session.
            top_k: Number of chunks to retrieve.
        """
        self.db = db
        self.pipeline = RAGPipeline(top_k=top_k)

    async def query(
        self,
        question: str,
        source_ids: list[str] | None = None,
        source_id: str | None = None,
        user_id: UUID | None = None,
        chat_history: list[db_schemas.ChatMessageRead] | None = None,
    ) -> dict[str, Any]:
        """Execute a RAG query and return the answer with source metadata.

        Args:
            question: Natural-language question to answer.
            source_ids: Optional list of allowed source UUIDs.
            source_id: Optional source UUID to restrict retrieval to a single
                document.
            user_id: Caller's user ID — used for structured logging only.
            chat_history: Prior conversation turns from the database.  Converted
                to LangChain messages for multi-turn context.

        Returns:
            dict: ``{"answer": str, "sources": list[dict]}`` where each source
            dict contains chunk metadata (``source_id``, ``chunk_index``,
            ``score``, ``text`` snippet).
        """
        logger.info(
            "RAG query started",
            question=question[:100],
            source_ids_count=len(source_ids or []),
            user_id=str(user_id) if user_id else None,
        )

        # Build filters
        where = {}
        if source_ids is not None:
            where["source_ids"] = source_ids
        if source_id:
            where["source_id"] = source_id

        # Convert DB history to LangChain messages
        lc_history = RAGPipeline._to_langchain_messages(chat_history or [])

        # Execute RAG pipeline
        result = await self.pipeline.query(
            db=self.db,
            question=question,
            where=where if where else None,
            chat_history=lc_history,
        )

        logger.info(
            "RAG query completed",
            answer_length=len(result["answer"]),
            num_sources=len(result["sources"]),
        )

        return result
