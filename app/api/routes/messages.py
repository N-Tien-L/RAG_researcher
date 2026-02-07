"""Chat message endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.applications.chat_application import ChatApplicationService
from app.db import schemas
from app.services.chat_service import ChatService, ServiceError

router = APIRouter(prefix="/messages", tags=["messages"])


class SendMessageRequest(BaseModel):
    """Request to send a message in a chat."""
    
    chat_id: UUID
    content: str = Field(..., min_length=1, max_length=10000)
    use_rag: bool = Field(default=True, description="Use RAG for generating response")
    collection_name: str = Field(default="documents")


class SendMessageResponse(BaseModel):
    """Response after sending a message."""
    
    user_message: schemas.ChatMessageRead
    assistant_message: schemas.ChatMessageRead
    sources: list[dict] = Field(default_factory=list)


@router.post("/send", response_model=SendMessageResponse)
async def send_message(
    request: SendMessageRequest,
    db: Annotated[AsyncSession, Depends(deps.db_session)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
) -> SendMessageResponse:
    """Send a message and get RAG-powered response."""
    chat_service = ChatService(db)
    
    # Verify chat ownership
    try:
        chat = await chat_service.get_chat_session(request.chat_id)
    except ServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        ) from exc
    
    if chat.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to send messages in this chat",
        )
    
    if request.use_rag:
        # Use chat application service for RAG-powered response
        chat_app_service = ChatApplicationService(db)
        result = await chat_app_service.send_message_with_rag(
            chat_session_id=request.chat_id,
            user_message=request.content,
            collection_name=request.collection_name,
        )
        return SendMessageResponse(**result)
    else:
        # Just save user message (no AI response)
        user_msg_in = schemas.ChatMessageCreate(
            chat_id=request.chat_id,
            role=schemas.MessageRole.user,
            content=request.content,
        )
        user_msg = await chat_service.add_message_to_chat(user_msg_in)
        
        return SendMessageResponse(
            user_message=user_msg,
            assistant_message=user_msg,  # Placeholder
            sources=[],
        )


@router.get("/{chat_id}/history", response_model=list[schemas.ChatMessageRead])
async def get_chat_history(
    chat_id: UUID,
    service: Annotated[ChatService, Depends(deps.chat_service)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
) -> list[schemas.ChatMessageRead]:
    """Get all messages for a chat session."""
    # Verify chat ownership
    try:
        chat = await service.get_chat_session(chat_id)
    except ServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        ) from exc
    
    if chat.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this chat",
        )
    
    return await service.get_chat_history(chat_id)
