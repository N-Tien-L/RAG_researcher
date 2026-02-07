"""RAG query endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.applications.rag_application import RAGApplicationService
from app.db import schemas

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
    """Query RAG system with a question.
    
    Retrieves relevant context from vector store and generates an answer using LLM.
    """
    rag_service = RAGApplicationService(db, top_k=5)
    
    result = await rag_service.query(
        question=request.question,
        collection_name=request.collection_name,
        source_id=request.source_id,
        user_id=current_user.id,
    )

    return RAGQueryResponse(
        answer=result["answer"],
        sources=result["sources"],
    )
