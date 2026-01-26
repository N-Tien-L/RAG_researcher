"""Retrieval helpers for Chroma."""

from typing import Any, Dict, List, Optional

from app.vectorstore.chroma import get_collection

def retrieve_chunks(
    embedding: List[float],
    collection_name: str,
    top_k: int = 5,
    where: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Return the nearest chunks for a query embedding."""

    collection = get_collection(collection_name)

    results = collection.query(
        query_embeddings=[embedding],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    chunks: List[Dict[str, Any]] = []
    for idx in range(len(results["ids"][0])):
        chunks.append(
            {
                "id": results["ids"][0][idx],
                "text": results["documents"][0][idx],
                "metadata": results["metadatas"][0][idx],
                "distance": results["distances"][0][idx],
            }
        )

    return chunks