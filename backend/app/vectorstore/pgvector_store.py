"""Async pgvector storage helpers using dependency-injected AsyncSession."""

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentChunk
from app.services.exceptions import VectorStoreError, get_request_context_data


async def get_existing_file_hash(db: AsyncSession, source_id: str) -> str | None:
    """Return the ``file_hash`` of the first stored chunk for a source.

    Used by the ingestion pipeline to detect unchanged sources and skip
    re-embedding when the hash matches the newly extracted content.

    Args:
        db: Async database session.
        source_id: UUID string of the ``Source`` record.

    Returns:
        str | None: The stored file hash, or ``None`` if no chunks exist yet.
    """
    stmt = (
        select(DocumentChunk.file_hash)
        .where(DocumentChunk.source_id == source_id)
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def delete_chunks_by_source(db: AsyncSession, source_id: str) -> int:
    """Delete all ``DocumentChunk`` rows belonging to a source.

    Used before re-ingesting a source whose content has changed (hash
    mismatch).  Rolls back and raises ``VectorStoreError`` on failure.

    Args:
        db: Async database session.
        source_id: UUID string of the ``Source`` record.

    Returns:
        int: Number of deleted rows.

    Raises:
        VectorStoreError: If the DELETE statement fails.
    """
    try:
        stmt = delete(DocumentChunk).where(DocumentChunk.source_id == source_id)
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount
    except Exception as exc:
        await db.rollback()
        raise VectorStoreError(
            message="Failed to delete chunks from database",
            operation="delete",
            **get_request_context_data(),
        ) from exc


async def insert_chunks(
    db: AsyncSession,
    *,
    chunks: list[dict[str, Any]],
    embeddings: list[list[float]],
    source_id: str,
    file_hash: str,
) -> int:
    """Bulk-insert document chunks with pre-computed embeddings into pgvector.

    Creates one ``DocumentChunk`` ORM object per chunk, bulk-adds them to
    the session, and commits.  Rolls back and raises ``VectorStoreError``
    on any database error.

    Args:
        db: Async database session.
        chunks: Chunk dicts from the chunker; each must have ``"id"`` and
            ``"text"`` keys.
        embeddings: Pre-computed embedding vectors in the same order as
            *chunks*.
        source_id: UUID string of the parent ``Source`` record.
        file_hash: SHA-256 hash of the raw source content; stored on every
            chunk row for deduplication checks.

    Returns:
        int: Number of rows inserted.

    Raises:
        VectorStoreError: If the bulk INSERT or COMMIT fails.
    """
    objects = [
        DocumentChunk(
            chunk_id=chunk["id"],
            content=chunk["text"],
            embedding=embeddings[idx],
            source_id=source_id,
            file_hash=file_hash,
        )
        for idx, chunk in enumerate(chunks)
    ]
    
    try:
        db.add_all(objects)
        await db.commit()
        return len(objects)
    except Exception as exc:
        await db.rollback()
        raise VectorStoreError(
            message="Failed to insert chunks into database",
            operation="insert",
            **get_request_context_data(),
        ) from exc


async def query_chunks(
    db: AsyncSession,
    *,
    embedding: list[float],
    top_k: int = 5,
    where: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Retrieve top-k chunks by cosine similarity to a query embedding.

    Executes a pgvector ``<=>`` cosine-distance ORDER BY query against
    ``DocumentChunk``, optionally filtered by metadata fields in *where*.
    Converts the raw ``distance`` to a ``score`` (``1 - distance``) so
    higher values mean higher relevance.

    Args:
        db: Async database session.
        embedding: Query embedding vector (dimension must match stored vectors).
        top_k: Maximum number of results to return (default 5).
        where: Optional metadata filter dict.  Currently supported key:
            ``"source_id"`` (str) or ``"source_ids"`` (list[str]).

    Returns:
        list[dict]: Each dict contains ``"id"``, ``"text"``, ``"source_id"``,
        ``"distance"`` (float, lower is better), ``"score"`` (float,
        higher is better), and ``"metadata"`` (source_id, file_hash).

    Raises:
        VectorStoreError: If the similarity search query fails.
    """
    stmt = (
        select(
            DocumentChunk.chunk_id.label("id"),
            DocumentChunk.content.label("text"),
            DocumentChunk.source_id.label("source_id"),
            DocumentChunk.file_hash.label("file_hash"),
            DocumentChunk.embedding.cosine_distance(embedding).label("distance"),
        )
        .order_by("distance")
        .limit(top_k)
    )

    # Apply metadata filters
    if where:
        if "source_id" in where:
            stmt = stmt.where(DocumentChunk.source_id == where["source_id"])
        if "source_ids" in where:
            source_ids = where["source_ids"]
            if not source_ids:
                return []
            stmt = stmt.where(DocumentChunk.source_id.in_(source_ids))

    try:
        result = await db.execute(stmt)
        rows = result.all()
    except Exception as exc:
        raise VectorStoreError(
            message="Failed to query chunks from database",
            operation="query",
            **get_request_context_data(),
        ) from exc
    
    return [
        {
            "id": row.id,
            "text": row.text,
            "source_id": str(row.source_id),
            "distance": float(row.distance),
            "score": 1 - float(row.distance),  # Convert distance to similarity score
            "metadata": {
                "source_id": str(row.source_id),
                "file_hash": row.file_hash,
            },
        }
        for row in rows
    ]
