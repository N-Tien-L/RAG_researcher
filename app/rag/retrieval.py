"""Retrieval helpers for pgvector."""

from typing import Any, Dict, List, Optional

from app.vectorstore.pgvector_store import query_chunks as pgvector_query_chunks

def retrieve_chunks(
    embedding: List[float],
    collection_name: str,
    top_k: int = 5,
    where: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Return the nearest chunks for a query embedding (pgvector)."""

    return pgvector_query_chunks(
        embedding=embedding,
        collection_name=collection_name,
        top_k=top_k,
        where=where,
    )