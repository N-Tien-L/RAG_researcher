"""RAG query endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.applications.rag_application import RAGApplicationService
from app.db import schemas
from app.services.source_service import SourceService
from app.services.exceptions import EmbeddingError, LLMError, VectorStoreError

router = APIRouter(prefix="/rag", tags=["rag"])


class RAGQueryRequest(BaseModel):
    """RAG query request schema."""

    question: str = Field(..., min_length=1, max_length=2000, json_schema_extra={"example": "What is RAG?"})
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
    an optional source scope, and generates a grounded answer via
    the configured LLM.  An optional ``source_id`` narrows retrieval to a
    single source document.

    Args:
        request: Query payload with ``question`` (1–2000 chars),
            and optional ``source_id`` filter.
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
    source_service = SourceService(db)

    user_sources = await source_service.list_sources_for_user(current_user.id)
    ready_source_ids = {
        str(source.id)
        for source in user_sources
        if source.status == schemas.SourceStatus.ready
    }
    user_source_ids = {str(source.id) for source in user_sources}

    scoped_source_ids = list(ready_source_ids)
    if request.source_id is not None:
        if request.source_id not in user_source_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Source not found",
            )
        scoped_source_ids = [request.source_id]
    
    try:
        result = await rag_service.query(
            question=request.question,
            source_ids=scoped_source_ids,
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
