"""Application-level chat orchestration combining chat management and RAG."""

from uuid import UUID
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db import schemas
from app.services.chat_service import ChatService
from app.applications.rag_application import RAGApplicationService
 
from app.db.sessions import async_session_maker

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

    def _schedule_title_generation(
        self, chat_session_id: UUID, first_message: str, assistant_content: str | None = None
    ) -> None:
        """Schedule background generation of a chat title.

        This uses the global async session maker to run title creation in a
        separate task so it doesn't block the request/response path.
        """
        try:
            asyncio.create_task(
                self._background_generate_title(chat_session_id, first_message, assistant_content)
            )
        except Exception as exc:  # pragma: no cover - scheduling failures should not break flow
            logger.warning("failed_to_schedule_title_generation", error=str(exc))

    async def _background_generate_title(
        self, chat_session_id: UUID, first_message: str, assistant_content: str | None = None
    ) -> None:
        """Background task: open a fresh DB session, generate title, update DB, and optionally notify UI.

        The notification hook is optional; if present the module
        `app.core.notifications.notify_chat_title_updated` will be awaited.
        """
        if async_session_maker is None:
            logger.warning("async_session_maker_unavailable_for_title_generation")
            return

        async with async_session_maker() as session:
            try:
                svc = ChatService(session)
                title = await svc._build_chat_title(first_message)
                await svc.update_chat_title(chat_session_id, title)

                # Optional notification hook for real-time frontends.
                try:
                    from app.core import notifications

                    notify = getattr(notifications, "notify_chat_title_updated", None)
                    if notify is not None:
                        maybe_coro = notify(chat_session_id=str(chat_session_id), title=title)
                        if asyncio.iscoroutine(maybe_coro):
                            await maybe_coro
                except Exception:
                    # Don't fail the background task if notification hook is missing/failed
                    logger.debug("no_notifications_hook_or_notify_failed")
            except Exception as exc:
                logger.warning("background_title_generation_failed", error=str(exc))

    async def send_message_with_rag(
        self,
        chat_session_id: UUID,
        user_message: str,
    ) -> dict[str, object]:
        """Persist a user message and generate a RAG-powered assistant reply.

        Fetches the prior conversation history (capped at
        ``settings.CHAT_HISTORY_MAX_TURNS * 2`` messages) before saving the
        new user message so the current turn is excluded from context.
        The RAG query uses the trimmed history for multi-turn coherence.

        Args:
            chat_session_id: UUID of the target chat session.
            user_message: The user's text input.

        Returns:
            dict: ``{"user_message": ChatMessageRead,
            "assistant_message": ChatMessageRead,
            "sources": list[dict],
            "chat_title": str | None}`` where ``sources`` contains chunk
            metadata returned by the RAG pipeline and ``chat_title`` is set
            only on the first turn.
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

        linked_source_ids = await self.chat_service.list_ready_source_ids_for_chat(
            chat_session_id,
        )

        _NO_SOURCES_FALLBACK = "I don't know. No ready sources are linked to this chat yet."

        if not linked_source_ids:
            assistant_msg_in = schemas.ChatMessageCreate(
                chat_id=chat_session_id,
                role=schemas.ChatRole.assistant,
                content=_NO_SOURCES_FALLBACK,
            )
            assistant_msg = await self.chat_service.add_message_to_chat(assistant_msg_in)

            chat_title: str | None = None
            if not raw_history:
                current_chat = await self.chat_service.get_chat_session(chat_session_id)
                title_val = current_chat.title.strip() if current_chat.title else None
                # Trigger background title generation if title is missing or still the default 'New Chat'
                if title_val is None or title_val.lower() == "new chat":
                    self._schedule_title_generation(chat_session_id, user_message, None)

            return {
                "user_message": user_msg,
                "assistant_message": assistant_msg,
                "sources": [],
                "chat_title": chat_title,
            }

        # Get RAG response with conversation history
        rag_result = await self.rag_service.query(
            question=user_message,
            source_ids=linked_source_ids,
            chat_history=trimmed_history,
        )

        # Save assistant message and persist per-message sources
        assistant_content = rag_result["answer"]
        assistant_msg = await self.chat_service.add_assistant_message_with_sources(
            chat_session_id, assistant_content, rag_result.get("sources", []),
        )

        logger.info(
            "Chat message processed",
            chat_session_id=str(chat_session_id),
            sources_used=len(rag_result["sources"]),
        )

        # Deferred (background) title generation on the first turn.
        chat_title: str | None = None
        if not raw_history:
            current_chat = await self.chat_service.get_chat_session(chat_session_id)
            title_val = current_chat.title.strip() if current_chat.title else None
            # If title is missing or equals 'New Chat', schedule background generation
            if title_val is None or title_val.lower() == "new chat":
                self._schedule_title_generation(chat_session_id, user_message, assistant_msg.content)

        return {
            "user_message": user_msg,
            "assistant_message": assistant_msg,
            "sources": rag_result["sources"],
            "chat_title": chat_title,
        }
