"""Pgvector storage helpers."""

from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DocumentChunk
from app.db.sessions import session_local


def _get_session() -> Session:
    if session_local is None:
        raise RuntimeError("Database engine is not initialized")
    return session_local()


def get_existing_file_hash(source_id: str) -> Optional[str]:
    session = _get_session()
    try:
        return (
            session.query(DocumentChunk.file_hash)
            .filter(DocumentChunk.source_id == source_id)
            .limit(1)
            .scalar()
        )
    finally:
        session.close()


def delete_chunks_by_source(source_id: str) -> int:
    session = _get_session()
    try:
        result = session.query(DocumentChunk).filter(DocumentChunk.source_id == source_id).delete()
        session.commit()
        return result
    finally:
        session.close()


def insert_chunks(
    *,
    chunks: Iterable[Dict[str, Any]],
    embeddings: List[List[float]],
    source_id: str,
    file_hash: str,
    collection_name: str,
) -> int:
    session = _get_session()
    try:
        objects = []
        for idx, chunk in enumerate(chunks):
            objects.append(
                DocumentChunk(
                    chunk_id=chunk["id"],
                    content=chunk["text"],
                    embedding=embeddings[idx],
                    source_id=source_id,
                    file_hash=file_hash,
                    collection_name=collection_name,
                )
            )
        session.bulk_save_objects(objects)
        session.commit()
        return len(objects)
    finally:
        session.close()


def query_chunks(
    *,
    embedding: List[float],
    collection_name: str,
    top_k: int = 5,
    where: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    session = _get_session()
    try:
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

        if where:
            if "source_id" in where:
                stmt = stmt.where(DocumentChunk.source_id == where["source_id"])

        rows = session.execute(stmt).all()
        results: List[Dict[str, Any]] = []
        for row in rows:
            data = dict(row._mapping)
            data["metadata"] = {"source_id": data.get("source_id"), "file_hash": data.get("file_hash")}
            results.append(data)
        return results
    finally:
        session.close()
