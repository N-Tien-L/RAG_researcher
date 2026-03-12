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
    """Create a new chat session for the authenticated user.

    Ownership is enforced: ``chat_in.user_id`` must match ``current_user.id``.

    Args:
        chat_in: Chat session creation data (user_id, optional title).
        service: Chat service for database persistence.
        current_user: Authenticated user who will own the session.

    Returns:
        schemas.ChatSessionRead: The newly created chat session.

    Raises:
        HTTPException: 403 Forbidden if ``chat_in.user_id`` differs from the
            authenticated user's ID.
        HTTPException: 400 Bad Request if creation fails.
    """
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
    """Retrieve a chat session by its ID.

    Ownership is enforced: only the session owner may access it.

    Args:
        chat_session_id: UUID of the chat session to retrieve.
        service: Chat service for database lookup.
        current_user: Authenticated user; must be the session owner.

    Returns:
        schemas.ChatSessionRead: The requested chat session.

    Raises:
        HTTPException: 404 Not Found if the session does not exist.
        HTTPException: 403 Forbidden if the caller is not the session owner.
    """
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
    """List all chat sessions owned by the current user.

    Args:
        service: Chat service for database query.
        current_user: Authenticated user whose sessions are listed.

    Returns:
        list[schemas.ChatSessionRead]: All chat sessions for the user.
    """
    return await service.list_chat_sessions_for_user(current_user.id)


@router.post("/{chat_session_id}/sources/{source_id}", response_model=schemas.ChatSessionSourceRead)
async def link_source_to_chat(
    chat_session_id: UUID,
    source_id: UUID,
    service: Annotated[ChatService, Depends(deps.chat_service)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
) -> schemas.ChatSessionSourceRead:
    """Associate a source with a chat session for scoped RAG retrieval.

    Ownership is enforced: only the chat session owner may link sources.

    Args:
        chat_session_id: UUID of the target chat session.
        source_id: UUID of the source to associate.
        service: Chat service for database update.
        current_user: Authenticated user; must own the chat session.

    Returns:
        schemas.ChatSessionSourceRead: The created chat–source association record.

    Raises:
        HTTPException: 404 Not Found if the chat session does not exist.
        HTTPException: 403 Forbidden if the caller does not own the session.
        HTTPException: 400 Bad Request if the association cannot be created.
    """
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
