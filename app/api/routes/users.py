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
    """Create a new user."""
    return await service.create_user(user_in)


@router.get("/{user_id}", response_model=schemas.UserRead)
async def get_user(
    user_id: UUID,
    service: Annotated[UserService, Depends(deps.user_service)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
) -> schemas.UserRead:
    """Get user by ID."""
    return await service.get_user(user_id)


@router.get("/", response_model=list[schemas.UserRead])
async def list_users(
    service: Annotated[UserService, Depends(deps.user_service)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
    skip: int = 0,
    limit: int = 100,
) -> list[schemas.UserRead]:
    """List users with pagination."""
    return await service.list_users(skip, limit)


@router.patch("/{user_id}", response_model=schemas.UserRead)
async def update_user(
    user_id: UUID,
    user_update: schemas.UserUpdate,
    service: Annotated[UserService, Depends(deps.user_service)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
) -> schemas.UserRead:
    """Update user information."""
    return await service.update_user(user_id, user_update)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    service: Annotated[UserService, Depends(deps.user_service)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
) -> None:
    """Delete a user."""
    await service.delete_user(user_id)
