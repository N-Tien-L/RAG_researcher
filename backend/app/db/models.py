"""SQLAlchemy ORM models for the RAG Researcher application."""

from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import declarative_base, relationship
from app.core.config import settings

Base = declarative_base()


def _utcnow() -> datetime:
    """Return the current UTC datetime.

    Returns:
        datetime: Timezone-aware UTC timestamp.
    """
    return datetime.now(timezone.utc)


class User(Base):
    """ORM model for the ``users`` table.

    Represents an application user with hashed credentials and ownership
    relationships to chat sessions and sources.
    """
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # Primary key UUID
    email = Column(String(255), unique=True, nullable=False)  # Unique email address used for login
    username = Column(String(100), unique=True, nullable=True)  # Optional display name
    password_hash = Column(String(255), nullable=False)  # bcrypt-hashed password

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)  # Account creation timestamp

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


class ChatSession(Base):
    """ORM model for the ``chat_sessions`` table.

    A chat session belongs to one user and may reference multiple sources.
    The ``collections`` field stores a PostgreSQL ARRAY of collection names
    that scope vector retrieval for this session.
    """
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    title = Column(String(255), nullable=True)

    # PostgreSQL ARRAY of collection names scoping retrieval for this session
    collections = Column(ARRAY(String), nullable=False, default=list)

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

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


class ChatMessage(Base):
    """ORM model for the ``chat_messages`` table.

    Stores individual messages within a chat session.  The ``role`` column
    accepts three enum values: ``user``, ``assistant``, and ``system``.
    Messages are ordered by ``created_at`` via the relationship on
    ``ChatSession``.
    """
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

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Relationships
    chat_session = relationship("ChatSession", back_populates="messages")


class Source(Base):
    """ORM model for the ``sources`` table.

    Represents an ingested content source (PDF or YouTube).  Key fields:

    - ``type``: enum ``pdf`` | ``youtube`` | ``text``
    - ``status``: enum ``processing`` | ``ready`` | ``failed``
    - ``content_hash``: SHA-256 of raw extracted content, used for smart
      re-ingestion deduplication (skip if unchanged, re-ingest if modified)
    - ``source_key``: stable deduplication key (file path or YouTube video ID)
    - ``source_uri``: original URI (absolute path for PDFs, URL for YouTube)
    - ``external_id``: platform-specific ID (e.g. YouTube video ID)
    """
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

    source_key = Column(String(512), nullable=True)
    source_uri = Column(Text, nullable=True)
    external_id = Column(String(255), nullable=True)
    content_hash = Column(String(128), nullable=True)

    last_ingested_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="sources")

    chat_session_links = relationship(
        "ChatSessionSource",
        back_populates="source",
        cascade="all, delete-orphan",
    )

    # Note: document_chunks stored in pgvector table keyed by source_id string; no FK relationship here.


class DocumentChunk(Base):
    """ORM model for the ``document_chunks`` table.

    Stores text chunks alongside their pgvector embeddings for similarity
    search.  Key fields:

    - ``embedding``: pgvector ``Vector(EMBEDDING_DIM)`` column used for
      nearest-neighbour queries via L2 distance
    - ``file_hash``: SHA-256 of the parent source raw content, used to
      detect stale chunks during re-ingestion
    - ``chunk_id``: human-readable stable ID in the form ``{source_id}-chunk-{N}``
    """
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id = Column(String(255), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(dim=settings.EMBEDDING_DIM), nullable=False)  # pgvector column
    source_id = Column(String(255), nullable=False)
    file_hash = Column(String(128), nullable=False)  # SHA-256 for deduplication
    collection_name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class ChatSessionSource(Base):
    """ORM model for the ``chat_session_sources`` join table.

    Implements the many-to-many relationship between ``ChatSession`` and
    ``Source``.  A source can belong to multiple chat sessions and a chat
    session can reference multiple sources.
    """
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

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Optional future fields:
    # is_active = Column(Boolean, default=True)
    # collection_name_override = Column(String)

    # Relationships
    chat_session = relationship("ChatSession", back_populates="source_links")
    source = relationship("Source", back_populates="chat_session_links")
