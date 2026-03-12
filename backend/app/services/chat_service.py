"""Business logic for chat sessions and messages."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models, schemas
from app.services.exceptions import ResourceConflict, ResourceNotFound


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

        chat = models.ChatSession(
            user_id=chat_in.user_id,
            title=chat_in.title,
            collections=chat_in.collections or [],
        )
        self.db.add(chat)
        await self.db.commit()
        await self.db.refresh(chat)
        return schemas.ChatSessionRead.model_validate(chat)

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
        return [schemas.ChatMessageRead.model_validate(msg) for msg in messages]

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

    # Sources linkage -------------------------------------------------------
    async def link_source_to_chat(
        self, chat_session_id: UUID, source_id: UUID
    ) -> schemas.ChatSessionSourceRead:
        """Link a source to a chat session.
        
        Args:
            chat_session_id: UUID of the chat session.
            source_id: UUID of the source.
            
        Returns:
            Created link data.
            
        Raises:
            ResourceNotFound: If chat session or source does not exist.
            ResourceConflict: If link already exists.
        """
        chat = await self.db.get(models.ChatSession, chat_session_id)
        if not chat:
            raise ResourceNotFound("Chat session not found")
        source = await self.db.get(models.Source, source_id)
        if not source:
            raise ResourceNotFound("Source not found")

        link = models.ChatSessionSource(
            chat_session_id=chat_session_id,
            source_id=source_id,
        )
        self.db.add(link)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ResourceConflict("Link already exists") from exc
        
        await self.db.refresh(link)
        return schemas.ChatSessionSourceRead.model_validate(link)
