"""Pydantic DTOs for persisted SQLAlchemy models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# Shared enums -----------------------------------------------------------------


class ChatRole(str, Enum):
    """Allowed roles for chat message senders."""

    user = "user"
    assistant = "assistant"
    system = "system"


class SourceType(str, Enum):
    """Allowed source content types for ingestion."""

    pdf = "pdf"
    youtube = "youtube"
    text = "text"


class SourceStatus(str, Enum):
    """Processing status of a source."""

    processing = "processing"
    ready = "ready"
    failed = "failed"


# Base helpers -----------------------------------------------------------------


class ORMModel(BaseModel):
    """Base Pydantic model with ``from_attributes=True`` for ORM compatibility.

    All schemas that map to SQLAlchemy models should inherit from this class
    so that ``model_validate(orm_instance)`` works without extra configuration.
    """

    model_config = ConfigDict(from_attributes=True)


class TimestampedModel(ORMModel):
    """Mixin that adds a ``created_at`` timestamp field."""

    created_at: datetime


# User -------------------------------------------------------------------------


class UserBase(ORMModel):
    """Shared user fields used by create and read schemas."""

    email: EmailStr
    username: Optional[str] = None


class UserCreate(UserBase):
    """Request schema for registering a new user."""

    password: str


class UserUpdate(ORMModel):
    """Request schema for partial user profile updates."""

    email: Optional[EmailStr] = None
    username: Optional[str] = None


class UserChangePassword(ORMModel):
    current_password: str
    new_password: str
	

class UserRead(UserBase, TimestampedModel):
    """Response schema for user data returned from the API."""

    id: UUID


# Auth -------------------------------------------------------------------------


# Remove unused LoginRequest
# class LoginRequest(ORMModel):
# 	email: EmailStr
# 	password: str


class Token(ORMModel):
    """JWT access token response returned from the login endpoint."""

    access_token: str
    token_type: str = "bearer"


class TokenPayload(ORMModel):
    """Decoded JWT payload fields extracted during token validation."""

    sub: UUID | None = None
    exp: int | None = None


# Chat sessions ----------------------------------------------------------------


class ChatSessionBase(ORMModel):
    """Shared chat session fields used by create and read schemas."""

    title: Optional[str] = None
    collections: List[str] = Field(default_factory=list)


class ChatSessionCreate(ChatSessionBase):
    """Request schema for creating a new chat session."""

    user_id: UUID


class ChatSessionUpdate(ORMModel):
    """Request schema for partial chat session updates."""

    title: Optional[str] = None
    collections: Optional[List[str]] = None


class ChatSessionRead(ChatSessionBase, TimestampedModel):
    """Response schema for chat session data returned from the API."""

    id: UUID
    user_id: UUID


# Chat messages ----------------------------------------------------------------


class ChatMessageBase(ORMModel):
    """Shared message fields used by create and read schemas."""

    role: ChatRole
    content: str


class ChatMessageCreate(ChatMessageBase):
    """Request schema for adding a new message to a chat session."""

    chat_id: UUID


class ChatMessageRead(ChatMessageBase, TimestampedModel):
    """Response schema for a single chat message."""

    id: UUID
    chat_id: UUID


# Sources ----------------------------------------------------------------------


class SourceBase(ORMModel):
    """Shared source fields used by create and read schemas."""

    type: SourceType
	title: str
	collection_name: str
	status: SourceStatus = SourceStatus.processing
	source_key: Optional[str] = None
	source_uri: Optional[str] = None
	external_id: Optional[str] = None
	content_hash: Optional[str] = None
	last_ingested_at: Optional[datetime] = None
	updated_at: Optional[datetime] = None


class SourceCreate(SourceBase):
    """Request schema for creating a new source record."""

    user_id: UUID


class SourceUpdate(ORMModel):
    """Request schema for partial source record updates."""

    title: Optional[str] = None
	collection_name: Optional[str] = None
	status: Optional[SourceStatus] = None
	source_key: Optional[str] = None
	source_uri: Optional[str] = None
	external_id: Optional[str] = None
	content_hash: Optional[str] = None
	last_ingested_at: Optional[datetime] = None
	updated_at: Optional[datetime] = None


class SourceRead(SourceBase, TimestampedModel):
    """Response schema for a source record returned from the API."""

    id: UUID
    user_id: UUID


class SourceProcessResponse(ORMModel):
    """Response from source processing/ingestion.

    The ``status`` field is either ``'ingested'`` (new or modified source
    was fully ingested) or ``'skipped'`` (content hash unchanged, no
    re-ingestion performed).
    """
	source: SourceRead
	chunks_added: int
	collection: str
	ids: list[str]
	content_hash: str
	status: str  # 'ingested' or 'skipped'


# Chat-session-to-source links --------------------------------------------------


class ChatSessionSourceBase(ORMModel):
    """Shared fields for the chat-session-to-source link."""

    chat_session_id: UUID
    source_id: UUID


class ChatSessionSourceCreate(ChatSessionSourceBase):
    """Request schema for linking a source to a chat session."""

    pass


class ChatSessionSourceRead(ChatSessionSourceBase, TimestampedModel):
    """Response schema for a chat-session-to-source link."""

    pass


# Rich / nested views ----------------------------------------------------------


class ChatSessionWithMessages(ChatSessionRead):
    """Extended chat session view that includes all messages."""

    messages: List[ChatMessageRead] = Field(default_factory=list)


class ChatSessionWithSources(ChatSessionRead):
    """Extended chat session view that includes all linked sources."""

    sources: List[SourceRead] = Field(default_factory=list)


class ChatSessionDetail(ChatSessionRead):
	messages: List[ChatMessageRead] = Field(default_factory=list)
	sources: List[SourceRead] = Field(default_factory=list)
