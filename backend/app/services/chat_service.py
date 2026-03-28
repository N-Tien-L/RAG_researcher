"""Business logic for chat session and message management.

Provides :class:`ChatService` which handles ``ChatSession``,
``ChatMessage``, and ``ChatSessionSource`` records.  Route handlers in
``api/routes/chats.py`` and ``api/routes/messages.py`` consume this
service via the ``deps.chat_service`` FastAPI dependency.
"""

from __future__ import annotations

from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models, schemas
from app.llm.groq_client import fallback_chat_title, generate_chat_title
from app.core.logging import get_logger
from app.services.exceptions import ResourceConflict, ResourceNotFound

logger = get_logger(__name__)


class ChatService:
    """Service layer for chat session and message operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # Chat sessions ----------------------------------------------------------
    async def create_chat_session(
        self, chat_in: schemas.ChatSessionCreate
    ) -> schemas.ChatSessionRead:
        """Create a new chat session.
        
        Args:
            chat_in: Chat session creation data.
            
        Returns:
            Created chat session data.
            
        Raises:
            ResourceNotFound: If user does not exist.
        """
        # Ensure user exists
        user = await self.db.get(models.User, chat_in.user_id)
        if not user:
            raise ResourceNotFound("User not found")

        title = chat_in.title or None

        chat = models.ChatSession(
            user_id=chat_in.user_id,
            title=title,
            collections=chat_in.collections or [],
        )
        self.db.add(chat)

        await self.db.commit()
        await self.db.refresh(chat)
        return schemas.ChatSessionRead.model_validate(chat)

    async def _build_chat_title(self, first_message: str) -> str:
        """Generate a short title from the first user message.

        Args:
            first_message: Initial chat message content.

        Returns:
            A short title suitable for the chat session.
        """
        try:
            return await generate_chat_title(first_message)
        except Exception as exc:
            logger.warning(
                "groq_chat_title_generation_failed",
                error=str(exc),
            )
            return fallback_chat_title(first_message)

    async def update_chat_title(self, chat_session_id: UUID, title: str) -> None:
        """Update the title of a chat session.

        Args:
            chat_session_id: UUID of the chat session.
            title: New title to set.

        Raises:
            ResourceNotFound: If chat session does not exist.
        """
        chat = await self.db.get(models.ChatSession, chat_session_id)
        if not chat:
            raise ResourceNotFound("Chat session not found")
        chat.title = title
        await self.db.commit()

    async def get_chat_session(self, chat_session_id: UUID) -> schemas.ChatSessionRead:
        """Get chat session by ID.
        
        Args:
            chat_session_id: UUID of the chat session.
            
        Returns:
            Chat session data.
            
        Raises:
            ResourceNotFound: If chat session does not exist.
        """
        chat = await self.db.get(models.ChatSession, chat_session_id)
        if not chat:
            raise ResourceNotFound("Chat session not found")
        return schemas.ChatSessionRead.model_validate(chat)

    async def list_chat_sessions_for_user(self, user_id: UUID) -> list[schemas.ChatSessionRead]:
        """List all chat sessions for a user.
        
        Args:
            user_id: UUID of the user.
            
        Returns:
            List of chat sessions ordered by creation date descending.
        """
        stmt = (
            select(models.ChatSession)
            .where(models.ChatSession.user_id == user_id)
            .order_by(models.ChatSession.created_at.desc())
        )
        result = await self.db.execute(stmt)
        chats = result.scalars().all()
        return [schemas.ChatSessionRead.model_validate(chat) for chat in chats]

    # Messages ---------------------------------------------------------------
    async def get_chat_history(self, chat_session_id: UUID) -> list[schemas.ChatMessageRead]:
        """Get all messages for a chat session.
        
        Args:
            chat_session_id: UUID of the chat session.
            
        Returns:
            List of chat messages.
            
        Raises:
            ResourceNotFound: If chat session does not exist.
        """
        chat = await self.db.get(models.ChatSession, chat_session_id)
        if not chat:
            raise ResourceNotFound("Chat session not found")
        
        # Query messages explicitly to avoid lazy loading in async context
        stmt = (
            select(models.ChatMessage)
            .where(models.ChatMessage.chat_id == chat_session_id)
            .order_by(models.ChatMessage.created_at)
        )
        result = await self.db.execute(stmt)
        messages = result.scalars().all()

        def _to_message_read(msg: models.ChatMessage, sources: list[dict] | None = None) -> schemas.ChatMessageRead:
            return schemas.ChatMessageRead.model_validate(
                {
                    "id": msg.id,
                    "chat_id": msg.chat_id,
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at,
                    "sources": sources or [],
                }
            )

        # For each message, attach any persisted per-message sources
        out: list[schemas.ChatMessageRead] = []
        try:
            for msg in messages:
                # Retrieve any ChatMessageSource entries for this message
                src_stmt = (
                    select(models.ChatMessageSource.payload)
                    .where(models.ChatMessageSource.chat_message_id == msg.id)
                    .order_by(models.ChatMessageSource.created_at)
                )
                src_res = await self.db.execute(src_stmt)
                payloads = [p for (p,) in src_res.all()]

                # payloads are JSON strings; attempt to parse to dicts, otherwise pass raw
                parsed: list[dict] = []
                for payload in payloads:
                    try:
                        import json

                        parsed.append(json.loads(payload))
                    except Exception:
                        parsed.append({"raw": payload})

                out.append(_to_message_read(msg, parsed))
        except ProgrammingError as exc:
            if "chat_message_sources" not in str(exc):
                raise
            await self.db.rollback()
            logger.warning("chat_message_sources_missing_table", error=str(exc))
            return [_to_message_read(msg) for msg in messages]

        return out

    async def add_message_to_chat(
        self, message_in: schemas.ChatMessageCreate
    ) -> schemas.ChatMessageRead:
        """Add a message to a chat session.
        
        Args:
            message_in: Message creation data.
            
        Returns:
            Created message data.
            
        Raises:
            ResourceNotFound: If chat session does not exist.
        """
        chat = await self.db.get(models.ChatSession, message_in.chat_id)
        if not chat:
            raise ResourceNotFound("Chat session not found")

        message = models.ChatMessage(
            chat_id=message_in.chat_id,
            role=message_in.role.value,
            content=message_in.content,
        )
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        return schemas.ChatMessageRead.model_validate(message)

    async def add_assistant_message_with_sources(
        self, chat_id: UUID, content: str, sources: list[dict]
    ) -> schemas.ChatMessageRead:
        """Create an assistant message and persist associated per-message
        source payloads.

        Args:
            chat_id: UUID of chat session.
            content: Assistant message content.
            sources: List of dict payloads returned by the RAG pipeline.

        Returns:
            Persisted ChatMessageRead (with `sources` populated).
        """
        chat = await self.db.get(models.ChatSession, chat_id)
        if not chat:
            raise ResourceNotFound("Chat session not found")

        message = models.ChatMessage(
            chat_id=chat_id,
            role=schemas.ChatRole.assistant.value,
            content=content,
        )
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)

        # Persist per-message source payloads
        import json

        for src in sources:
            # Convert UUID/datetime and other non-JSON-native values first.
            normalized_src = jsonable_encoder(src)
            payload_text = json.dumps(normalized_src)
            msg_src = models.ChatMessageSource(
                chat_message_id=message.id,
                chunk_id=str(normalized_src.get("chunk_id")) if normalized_src.get("chunk_id") else None,
                payload=payload_text,
            )
            self.db.add(msg_src)

        await self.db.commit()

        # Build returned schema with parsed sources
        parsed_sources = []
        for src in sources:
            parsed_sources.append(jsonable_encoder(src))

        return schemas.ChatMessageRead.model_validate(
            {
                "id": message.id,
                "chat_id": message.chat_id,
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at,
                "sources": parsed_sources,
            }
        )

    # Sources linkage -------------------------------------------------------
    async def link_source_to_chat(
        self,
        chat_session_id: UUID,
        source_id: UUID,
        *,
        ignore_existing: bool = False,
    ) -> schemas.ChatSessionSourceRead:
        """Link a source to a chat session.
        
        Args:
            chat_session_id: UUID of the chat session.
            source_id: UUID of the source.
            
        Returns:
            Created link data.
            
        Raises:
            ResourceNotFound: If chat session or source does not exist.
            ResourceConflict: If link already exists and ``ignore_existing`` is False.
        """
        chat = await self.db.get(models.ChatSession, chat_session_id)
        if not chat:
            raise ResourceNotFound("Chat session not found")
        source = await self.db.get(models.Source, source_id)
        if not source:
            raise ResourceNotFound("Source not found")

        existing_stmt = (
            select(models.ChatSessionSource)
            .where(models.ChatSessionSource.chat_session_id == chat_session_id)
            .where(models.ChatSessionSource.source_id == source_id)
        )
        if ignore_existing:
            existing_result = await self.db.execute(existing_stmt)
            existing = existing_result.scalars().first()
            if existing is not None:
                return schemas.ChatSessionSourceRead.model_validate(existing)

        link = models.ChatSessionSource(
            chat_session_id=chat_session_id,
            source_id=source_id,
        )
        self.db.add(link)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            if ignore_existing:
                existing_result = await self.db.execute(existing_stmt)
                existing = existing_result.scalars().first()
                if existing is not None:
                    return schemas.ChatSessionSourceRead.model_validate(existing)
            raise ResourceConflict("Link already exists") from exc

        await self.db.refresh(link)
        return schemas.ChatSessionSourceRead.model_validate(link)

    async def list_ready_source_ids_for_chat(self, chat_session_id: UUID) -> list[str]:
        """List UUIDs of ready sources linked to a chat session."""
        stmt = (
            select(models.Source.id)
            .join(
                models.ChatSessionSource,
                models.ChatSessionSource.source_id == models.Source.id,
            )
            .where(models.ChatSessionSource.chat_session_id == chat_session_id)
            .where(models.Source.status == schemas.SourceStatus.ready.value)
        )
        result = await self.db.execute(stmt)
        return [str(source_id) for source_id in result.scalars().all()]

    async def list_sources_for_chat(self, chat_session_id: UUID) -> list[schemas.SourceRead]:
        """List all linked sources for a chat session.

        Args:
            chat_session_id: UUID of the chat session.

        Returns:
            Linked sources in reverse creation order.

        Raises:
            ResourceNotFound: If chat session does not exist.
        """
        chat = await self.db.get(models.ChatSession, chat_session_id)
        if not chat:
            raise ResourceNotFound("Chat session not found")

        stmt = (
            select(models.Source)
            .join(
                models.ChatSessionSource,
                models.ChatSessionSource.source_id == models.Source.id,
            )
            .where(models.ChatSessionSource.chat_session_id == chat_session_id)
            .order_by(models.ChatSessionSource.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return [schemas.SourceRead.model_validate(source) for source in result.scalars().all()]

    async def delete_chat_session(self, chat_session_id: UUID) -> None:
        """Delete a chat session and its related messages.

        Args:
            chat_session_id: UUID of the chat session to delete.

        Raises:
            ResourceNotFound: If the chat session does not exist.
        """
        chat = await self.db.get(models.ChatSession, chat_session_id)
        if not chat:
            raise ResourceNotFound("Chat session not found")
        await self.db.delete(chat)
        await self.db.commit()
