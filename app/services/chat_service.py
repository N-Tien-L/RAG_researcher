"""Business logic for chat sessions and messages."""

from __future__ import annotations

from typing import List
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import models, schemas


class ServiceError(Exception):
    """Raised when a business rule is violated or a resource is missing."""


class ChatService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # Chat sessions ----------------------------------------------------------
    def create_chat_session(
        self, chat_in: schemas.ChatSessionCreate
    ) -> schemas.ChatSessionRead:
        # ensure user exists
        user = self.db.get(models.User, chat_in.user_id)
        if not user:
            raise ServiceError("User not found")

        chat = models.ChatSession(
            user_id=chat_in.user_id,
            title=chat_in.title,
            collections=chat_in.collections or [],
        )
        self.db.add(chat)
        self.db.commit()
        self.db.refresh(chat)
        return schemas.ChatSessionRead.model_validate(chat)

    def get_chat_session(self, chat_session_id: UUID) -> schemas.ChatSessionRead:
        chat = self.db.get(models.ChatSession, chat_session_id)
        if not chat:
            raise ServiceError("Chat session not found")
        return schemas.ChatSessionRead.model_validate(chat)

    def list_chat_sessions_for_user(self, user_id: UUID) -> List[schemas.ChatSessionRead]:
        chats = (
            self.db.query(models.ChatSession)
            .filter(models.ChatSession.user_id == user_id)
            .order_by(models.ChatSession.created_at.desc())
            .all()
        )
        return [schemas.ChatSessionRead.model_validate(chat) for chat in chats]

    # Messages ---------------------------------------------------------------
    def get_chat_history(self, chat_session_id: UUID) -> List[schemas.ChatMessageRead]:
        chat = self.db.get(models.ChatSession, chat_session_id)
        if not chat:
            raise ServiceError("Chat session not found")
        return [schemas.ChatMessageRead.model_validate(msg) for msg in chat.messages]

    def add_message_to_chat(
        self, message_in: schemas.ChatMessageCreate
    ) -> schemas.ChatMessageRead:
        chat = self.db.get(models.ChatSession, message_in.chat_id)
        if not chat:
            raise ServiceError("Chat session not found")

        message = models.ChatMessage(
            chat_id=message_in.chat_id,
            role=message_in.role.value,
            content=message_in.content,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return schemas.ChatMessageRead.model_validate(message)

    # Sources linkage -------------------------------------------------------
    def link_source_to_chat(
        self, chat_session_id: UUID, source_id: UUID
    ) -> schemas.ChatSessionSourceRead:
        chat = self.db.get(models.ChatSession, chat_session_id)
        if not chat:
            raise ServiceError("Chat session not found")
        source = self.db.get(models.Source, source_id)
        if not source:
            raise ServiceError("Source not found")

        link = models.ChatSessionSource(
            chat_session_id=chat_session_id,
            source_id=source_id,
        )
        self.db.add(link)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            # Likely duplicate link
            raise ServiceError("Link already exists") from exc
        self.db.refresh(link)
        return schemas.ChatSessionSourceRead.model_validate(link)
