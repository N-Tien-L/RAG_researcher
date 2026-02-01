from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, status

from app.api import deps
from app.db import schemas
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/", response_model=schemas.UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    user_in: schemas.UserCreate,
    service: UserService = Depends(deps.user_service),
) -> schemas.UserRead:
    return service.create_user(user_in)


@router.get("/{user_id}", response_model=schemas.UserRead)
def get_user(
    user_id: UUID,
    service: UserService = Depends(deps.user_service),
    current_user: schemas.UserRead = Depends(deps.current_user),
) -> schemas.UserRead:
    return service.get_user(user_id)


@router.get("/", response_model=List[schemas.UserRead])
def list_user(
    skip: int = 0,
    limit: int = 100,
    service: UserService = Depends(deps.user_service),
    current_user: schemas.UserRead = Depends(deps.current_user),
) -> List[schemas.UserRead]:
    return service.list_user(skip, limit)


@router.patch("/{user_id}", response_model=schemas.UserRead)
def update_user(
    user_id: UUID,
    user_update: schemas.UserUpdate,
    service: UserService = Depends(deps.user_service),
    current_user: schemas.UserRead = Depends(deps.current_user),
) -> schemas.UserRead:
    return service.update_user(user_id, user_update)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: UUID,
    service: UserService = Depends(deps.user_service),
    current_user: schemas.UserRead = Depends(deps.current_user),
) -> None:
    service.delete_user(user_id)
