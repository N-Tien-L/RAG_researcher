"""User management routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api import deps
from app.db import schemas
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/", response_model=schemas.UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: schemas.UserCreate,
    service: Annotated[UserService, Depends(deps.user_service)],
) -> schemas.UserRead:
    """Register a new user account.

    This endpoint does not require authentication.

    Args:
        user_in: New user registration data (email, optional username, password).
        service: User service for creating the account.

    Returns:
        schemas.UserRead: The newly created user's profile.

    Raises:
        HTTPException: 409 Conflict if the email or username already exists.
    """
    return await service.create_user(user_in)


@router.get("/{user_id}", response_model=schemas.UserRead)
async def get_user(
    user_id: UUID,
    service: Annotated[UserService, Depends(deps.user_service)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
) -> schemas.UserRead:
    """Retrieve a user by ID.

    Args:
        user_id: UUID of the user to retrieve.
        service: User service for database lookup.
        current_user: Authenticated user (required for access).

    Returns:
        schemas.UserRead: The requested user's profile.

    Raises:
        HTTPException: 404 Not Found if the user does not exist.
    """
    return await service.get_user(user_id)


@router.get("/", response_model=list[schemas.UserRead])
async def list_users(
    service: Annotated[UserService, Depends(deps.user_service)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
    skip: int = 0,
    limit: int = 100,
) -> list[schemas.UserRead]:
    """List users with offset pagination.

    Args:
        service: User service for database query.
        current_user: Authenticated user (required for access).
        skip: Number of records to skip.
        limit: Maximum number of records to return.

    Returns:
        list[schemas.UserRead]: Paginated list of user profiles.
    """
    return await service.list_users(skip, limit)


@router.patch("/{user_id}", response_model=schemas.UserRead)
async def update_user(
    user_id: UUID,
    user_update: schemas.UserUpdate,
    service: Annotated[UserService, Depends(deps.user_service)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
) -> schemas.UserRead:
    """Partially update a user's profile fields.

    Args:
        user_id: UUID of the user to update.
        user_update: Fields to update (partial — only provided fields are changed).
        service: User service for database update.
        current_user: Authenticated user (required for access).

    Returns:
        schemas.UserRead: The updated user profile.

    Raises:
        HTTPException: 404 Not Found if the user does not exist.
    """
    return await service.update_user(user_id, user_update)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    service: Annotated[UserService, Depends(deps.user_service)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
) -> None:
    """Delete a user account and all associated data.

    Args:
        user_id: UUID of the user to delete.
        service: User service for database deletion.
        current_user: Authenticated user (required for access).

    Returns:
        None: 204 No Content on success.

    Raises:
        HTTPException: 404 Not Found if the user does not exist.
    """
    await service.delete_user(user_id)
