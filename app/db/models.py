from datetime import datetime
import uuid

from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    Enum,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# User model
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    chat_sessions = relationship(
        "ChatSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    sources = relationship(
        "Source",
        back_populates="user",
        cascade="all, delete-orphan",
    )

# ChatSession model
class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    title = Column(String(255), nullable=True)

    # List of collection names used by this chat
    collections = Column(ARRAY(String), nullable=False, default=list)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="chat_sessions")
    messages = relationship(
        "ChatMessage",
        back_populates="chat_session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    source_links = relationship(
        "ChatSessionSource",
        back_populates="chat_session",
        cascade="all, delete-orphan",
    )

    sources = relationship(
        "Source",
        secondary="chat_session_sources",
        viewonly=True,
    )

# ChatMessage model
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id"),
        nullable=False,
    )

    role = Column(
        Enum("user", "assistant", "system", name="chat_role"),
        nullable=False,
    )
    content = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    chat_session = relationship("ChatSession", back_populates="messages")

# Source model
class Source(Base):
    __tablename__ = "sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    type = Column(
        Enum("pdf", "youtube", "text", name="source_type"),
        nullable=False,
    )
    title = Column(String(255), nullable=False)

    status = Column(
        Enum("processing", "ready", "failed", name="source_status"),
        nullable=False,
        default="processing",
    )

    collection_name = Column(String(255), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="sources")

    chat_session_links = relationship(
        "ChatSessionSource",
        back_populates="source",
        cascade="all, delete-orphan",
    )

# ChatSessionSource model for the Many-to-Many relationship between chatSession and Source
class ChatSessionSource(Base):
    __tablename__ = "chat_session_sources"

    chat_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id"),
        primary_key=True,
    )
    source_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sources.id"),
        primary_key=True,
    )

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Optional future fields:
    # is_active = Column(Boolean, default=True)
    # collection_name_override = Column(String)

    # Relationships
    chat_session = relationship("ChatSession", back_populates="source_links")
    source = relationship("Source", back_populates="chat_session_links")
