"""Async retrieval helpers for pgvector."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.vectorstore.pgvector_store import query_chunks as pgvector_query_chunks


async def retrieve_chunks(
    db: AsyncSession,
    embedding: list[float],
    collection_name: str,
    top_k: int = 5,
    where: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Retrieve nearest chunks for a query embedding (async pgvector).
    
    Args:
        db: Async database session.
        embedding: Query embedding vector.
        collection_name: Collection to search in.
        top_k: Number of results to return.
        where: Optional metadata filters.
        
    Returns:
        List of chunks with metadata and similarity scores.
    """
    return await pgvector_query_chunks(
        db=db,
        embedding=embedding,
        collection_name=collection_name,
        top_k=top_k,
        where=where,
    )