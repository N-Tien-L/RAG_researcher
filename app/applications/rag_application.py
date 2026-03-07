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
        collection_name: str,
        source_id: str | None = None,
        user_id: UUID | None = None,
        chat_history: list[db_schemas.ChatMessageRead] | None = None,
    ) -> dict[str, Any]:
        """Execute RAG query with optional filtering.

        Args:
            question: User question.
            collection_name: Collection to search in.
            source_id: Optional filter by source ID.
            user_id: Optional user ID for logging/tracking.
            chat_history: Prior conversation turns from the DB.

        Returns:
            Dictionary with 'answer' and 'sources'.
        """
        logger.info(
            "RAG query started",
            question=question[:100],
            collection=collection_name,
            user_id=str(user_id) if user_id else None,
        )

        # Build filters
        where = {}
        if source_id:
            where["source_id"] = source_id

        # Convert DB history to LangChain messages
        lc_history = RAGPipeline._to_langchain_messages(chat_history or [])

        # Execute RAG pipeline
        result = await self.pipeline.query(
            db=self.db,
            question=question,
            collection_name=collection_name,
            where=where if where else None,
            chat_history=lc_history,
        )

        logger.info(
            "RAG query completed",
            answer_length=len(result["answer"]),
            num_sources=len(result["sources"]),
        )

        return result
