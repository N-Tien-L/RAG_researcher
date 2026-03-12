"""Chat session endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api import deps
from app.db import schemas
from app.services.chat_service import ChatService
from app.services.exceptions import ServiceError

router = APIRouter(prefix="/chats", tags=["chats"])


@router.post("/", response_model=schemas.ChatSessionRead, status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    chat_in: schemas.ChatSessionCreate,
    service: Annotated[ChatService, Depends(deps.chat_service)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
) -> schemas.ChatSessionRead:
    """Create a new chat session."""
    # Ensure user can only create chats for themselves
    if chat_in.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create chat for another user",
        )
    
    try:
        return await service.create_chat_session(chat_in)
    except ServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/{chat_session_id}", response_model=schemas.ChatSessionRead)
async def get_chat_session(
    chat_session_id: UUID,
    service: Annotated[ChatService, Depends(deps.chat_service)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
) -> schemas.ChatSessionRead:
    """Get chat session by ID."""
    try:
        chat = await service.get_chat_session(chat_session_id)
    except ServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        ) from exc
    
    # Ensure user can only access their own chats
    if chat.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this chat",
        )
    
    return chat


@router.get("/", response_model=list[schemas.ChatSessionRead])
async def list_chat_sessions(
    service: Annotated[ChatService, Depends(deps.chat_service)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
) -> list[schemas.ChatSessionRead]:
    """List all chat sessions for current user."""
    return await service.list_chat_sessions_for_user(current_user.id)


@router.post("/{chat_session_id}/sources/{source_id}", response_model=schemas.ChatSessionSourceRead)
async def link_source_to_chat(
    chat_session_id: UUID,
    source_id: UUID,
    service: Annotated[ChatService, Depends(deps.chat_service)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
) -> schemas.ChatSessionSourceRead:
    """Link a source to a chat session."""
    # Verify chat ownership
    try:
        chat = await service.get_chat_session(chat_session_id)
    except ServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        ) from exc
    
    if chat.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this chat",
        )
    
    try:
        return await service.link_source_to_chat(chat_session_id, source_id)
    except ServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
