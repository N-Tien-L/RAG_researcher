"""Chat message endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.applications.chat_application import ChatApplicationService
from app.db import schemas
from app.services.chat_service import ChatService
from app.services.exceptions import ServiceError

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
    """Send a user message and receive an assistant reply.

    When ``request.use_rag`` is ``True`` (default), the message is routed
    through ``ChatApplicationService.send_message_with_rag``, which retrieves
    relevant document chunks from the vector store and generates a grounded
    answer via the configured LLM.  When ``False``, only the user message is
    persisted and the ``assistant_message`` field in the response is a
    placeholder.

    Ownership is enforced: the caller must own the target chat session.

    Args:
        request: Message payload including ``chat_id``, ``content``,
            ``use_rag`` flag, and target ``collection_name``.
        db: Database session used to initialise application services.
        current_user: Authenticated user; must own the chat session.

    Returns:
        SendMessageResponse: Persisted ``user_message``, generated
        ``assistant_message``, and a ``sources`` list of retrieved chunk
        metadata (empty when ``use_rag=False``).

    Raises:
        HTTPException: 404 Not Found if the chat session does not exist.
        HTTPException: 403 Forbidden if the caller does not own the session.
    """
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
            role=schemas.ChatRole.user,
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
    """Return the full message history for a chat session.

    Messages are returned in ascending ``created_at`` order (oldest first).
    Ownership is enforced: only the chat session owner may read its history.

    Args:
        chat_id: UUID of the chat session whose history to retrieve.
        service: Chat service for database query.
        current_user: Authenticated user; must own the chat session.

    Returns:
        list[schemas.ChatMessageRead]: All messages in the session, ordered
        chronologically.

    Raises:
        HTTPException: 404 Not Found if the chat session does not exist.
        HTTPException: 403 Forbidden if the caller does not own the session.
    """
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
