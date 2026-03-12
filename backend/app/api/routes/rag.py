"""RAG query endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.applications.rag_application import RAGApplicationService
from app.db import schemas
from app.services.exceptions import EmbeddingError, LLMError, VectorStoreError

router = APIRouter(prefix="/rag", tags=["rag"])


class RAGQueryRequest(BaseModel):
    """RAG query request schema."""

    question: str = Field(..., min_length=1, max_length=2000, json_schema_extra={"example": "What is RAG?"})
    collection_name: str = Field(default="documents", json_schema_extra={"example": "documents"})
    source_id: str | None = Field(None, json_schema_extra={"example": None})


class RAGQueryResponse(BaseModel):
    """RAG query response schema."""

    answer: str
    sources: list[dict]


@router.post("/query", response_model=RAGQueryResponse)
async def query_rag(
    request: RAGQueryRequest,
    db: Annotated[AsyncSession, Depends(deps.db_session)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
) -> RAGQueryResponse:
    """Query the RAG pipeline with a natural-language question.

    Embeds ``request.question``, retrieves the top-5 relevant chunks from
    the specified ``collection_name``, and generates a grounded answer via
    the configured LLM.  An optional ``source_id`` narrows retrieval to a
    single source document.

    Args:
        request: Query payload with ``question`` (1–2000 chars),
            ``collection_name`` (default ``"documents"``), and optional
            ``source_id`` filter.
        db: Database session used to initialise ``RAGApplicationService``.
        current_user: Authenticated user (required for access control).

    Returns:
        RAGQueryResponse: Generated ``answer`` string and a ``sources`` list
        of chunk metadata dicts (``source_id``, ``chunk_index``, ``score``,
        ``text`` snippet).

    Raises:
        HTTPException: 503 Service Unavailable if the embedding service,
            LLM, or vector store is unreachable.
        HTTPException: 500 Internal Server Error for unexpected failures.
    """
    rag_service = RAGApplicationService(db, top_k=5)
    rag_service = RAGApplicationService(db, top_k=5)
    
    try:
        result = await rag_service.query(
            question=request.question,
            collection_name=request.collection_name,
            source_id=request.source_id,
            user_id=current_user.id,
        )
    except (EmbeddingError, LLMError, VectorStoreError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during RAG query",
        ) from exc

    return RAGQueryResponse(
        answer=result["answer"],
        sources=result["sources"],
    )
