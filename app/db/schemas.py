"""Pydantic DTOs for persisted SQLAlchemy models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# Shared enums -----------------------------------------------------------------


class ChatRole(str, Enum):
	user = "user"
	assistant = "assistant"
	system = "system"


class SourceType(str, Enum):
	pdf = "pdf"
	youtube = "youtube"
	text = "text"


class SourceStatus(str, Enum):
	processing = "processing"
	ready = "ready"
	failed = "failed"


# Base helpers -----------------------------------------------------------------


class ORMModel(BaseModel):
	model_config = ConfigDict(from_attributes=True)


class TimestampedModel(ORMModel):
	created_at: datetime


# User -------------------------------------------------------------------------


class UserBase(ORMModel):
	email: EmailStr
	username: Optional[str] = None


class UserCreate(UserBase):
	password: str


class UserUpdate(ORMModel):
	email: Optional[EmailStr] = None
	username: Optional[str] = None
	password: Optional[str] = None


class UserRead(UserBase, TimestampedModel):
	id: UUID


# Chat sessions ----------------------------------------------------------------


class ChatSessionBase(ORMModel):
	title: Optional[str] = None
	collections: List[str] = Field(default_factory=list)


class ChatSessionCreate(ChatSessionBase):
	user_id: UUID


class ChatSessionUpdate(ORMModel):
	title: Optional[str] = None
	collections: Optional[List[str]] = None


class ChatSessionRead(ChatSessionBase, TimestampedModel):
	id: UUID
	user_id: UUID


# Chat messages ----------------------------------------------------------------


class ChatMessageBase(ORMModel):
	role: ChatRole
	content: str


class ChatMessageCreate(ChatMessageBase):
	chat_id: UUID


class ChatMessageRead(ChatMessageBase, TimestampedModel):
	id: UUID
	chat_id: UUID


# Sources ----------------------------------------------------------------------


class SourceBase(ORMModel):
	type: SourceType
	title: str
	collection_name: str
	status: SourceStatus = SourceStatus.processing


class SourceCreate(SourceBase):
	user_id: UUID


class SourceUpdate(ORMModel):
	title: Optional[str] = None
	collection_name: Optional[str] = None
	status: Optional[SourceStatus] = None


class SourceRead(SourceBase, TimestampedModel):
	id: UUID
	user_id: UUID


# Chat-session-to-source links --------------------------------------------------


class ChatSessionSourceBase(ORMModel):
	chat_session_id: UUID
	source_id: UUID


class ChatSessionSourceCreate(ChatSessionSourceBase):
	pass


class ChatSessionSourceRead(ChatSessionSourceBase, TimestampedModel):
	pass


# Rich / nested views ----------------------------------------------------------


class ChatSessionWithMessages(ChatSessionRead):
	messages: List[ChatMessageRead] = Field(default_factory=list)


class ChatSessionWithSources(ChatSessionRead):
	sources: List[SourceRead] = Field(default_factory=list)


class ChatSessionDetail(ChatSessionRead):
	messages: List[ChatMessageRead] = Field(default_factory=list)
	sources: List[SourceRead] = Field(default_factory=list)
