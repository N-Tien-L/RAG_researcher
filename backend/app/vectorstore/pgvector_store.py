"""Async pgvector storage helpers using dependency-injected AsyncSession."""

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentChunk
from app.services.exceptions import VectorStoreError, get_request_context_data


async def get_existing_file_hash(db: AsyncSession, source_id: str) -> str | None:
    """Get file hash for existing source.
    
    Args:
        db: Async database session.
        source_id: Source identifier.
        
    Returns:
        File hash if exists, None otherwise.
    """
    stmt = (
        select(DocumentChunk.file_hash)
        .where(DocumentChunk.source_id == source_id)
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def delete_chunks_by_source(db: AsyncSession, source_id: str) -> int:
    """Delete all chunks for a given source.
    
    Args:
        db: Async database session.
        source_id: Source identifier.
        
    Returns:
        Number of deleted chunks.
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
    collection_name: str,
) -> int:
    """Insert chunks with embeddings into pgvector.
    
    Args:
        db: Async database session.
        chunks: List of chunk dictionaries with 'id' and 'text' keys.
        embeddings: List of embedding vectors.
        source_id: Source identifier.
        file_hash: Hash of source content.
        collection_name: Collection/namespace name.
        
    Returns:
        Number of inserted chunks.
    """
    objects = [
        DocumentChunk(
            chunk_id=chunk["id"],
            content=chunk["text"],
            embedding=embeddings[idx],
            source_id=source_id,
            file_hash=file_hash,
            collection_name=collection_name,
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
    collection_name: str,
    top_k: int = 5,
    where: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Query chunks using vector similarity search.
    
    Args:
        db: Async database session.
        embedding: Query embedding vector.
        collection_name: Collection/namespace to search.
        top_k: Number of results to return.
        where: Optional metadata filters (e.g., {'source_id': 'xyz'}).
        
    Returns:
        List of chunks with metadata and similarity scores.
    """
    stmt = (
        select(
            DocumentChunk.chunk_id.label("id"),
            DocumentChunk.content.label("text"),
            DocumentChunk.source_id.label("source_id"),
            DocumentChunk.file_hash.label("file_hash"),
            DocumentChunk.embedding.cosine_distance(embedding).label("distance"),
        )
        .where(DocumentChunk.collection_name == collection_name)
        .order_by("distance")
        .limit(top_k)
    )

    # Apply metadata filters
    if where:
        if "source_id" in where:
            stmt = stmt.where(DocumentChunk.source_id == where["source_id"])

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
            "source_id": row.source_id,
            "distance": float(row.distance),
            "score": 1 - float(row.distance),  # Convert distance to similarity score
            "metadata": {
                "source_id": row.source_id,
                "file_hash": row.file_hash,
            },
        }
        for row in rows
    ]
