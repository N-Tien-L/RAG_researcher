"""Application-level chat orchestration combining chat management and RAG."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db import schemas
from app.services.chat_service import ChatService
from app.applications.rag_application import RAGApplicationService

logger = get_logger(__name__)


class ChatApplicationService:
    """Orchestrates chat sessions with integrated RAG capabilities."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize chat application service.
        
        Args:
            db: Async database session.
        """
        self.db = db
        self.chat_service = ChatService(db)
        self.rag_service = RAGApplicationService(db)

    async def send_message_with_rag(
        self,
        chat_session_id: UUID,
        user_message: str,
        collection_name: str,
    ) -> dict[str, schemas.ChatMessageRead]:
        """Send user message and get RAG-powered assistant response.
        
        Args:
            chat_session_id: UUID of chat session.
            user_message: User's message content.
            collection_name: Collection to query for RAG.
            
        Returns:
            Dictionary with 'user_message' and 'assistant_message' schemas.
        """
        logger.info(
            "Processing chat message with RAG",
            chat_session_id=str(chat_session_id),
            message_length=len(user_message),
        )

        # Fetch history BEFORE saving the new user message so the current
        # turn is excluded and no stripping is needed.
        raw_history = await self.chat_service.get_chat_history(chat_session_id)
        # Cap history to avoid exceeding the model's context window.
        max_messages = settings.CHAT_HISTORY_MAX_TURNS * 2
        trimmed_history = raw_history[-max_messages:] if max_messages > 0 else []

        # Save user message
        user_msg_in = schemas.ChatMessageCreate(
            chat_id=chat_session_id,
            role=schemas.ChatRole.user,
            content=user_message,
        )
        user_msg = await self.chat_service.add_message_to_chat(user_msg_in)

        # Get RAG response with conversation history
        rag_result = await self.rag_service.query(
            question=user_message,
            collection_name=collection_name,
            chat_history=trimmed_history,
        )

        # Save assistant message
        assistant_msg_in = schemas.ChatMessageCreate(
            chat_id=chat_session_id,
            role=schemas.ChatRole.assistant,
            content=rag_result["answer"],
        )
        assistant_msg = await self.chat_service.add_message_to_chat(assistant_msg_in)

        logger.info(
            "Chat message processed",
            chat_session_id=str(chat_session_id),
            sources_used=len(rag_result["sources"]),
        )

        return {
            "user_message": user_msg,
            "assistant_message": assistant_msg,
            "sources": rag_result["sources"],
        }
