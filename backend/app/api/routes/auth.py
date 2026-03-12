"""Authentication routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api import deps
from app.db import schemas
from app.services.auth_service import AuthService
from app.services.exceptions import AuthenticationError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.Token)
async def login(
    credentials: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: Annotated[AuthService, Depends(deps.auth_service)],
) -> schemas.Token:
    """Authenticate user and return access token."""
    try:
        # Note: OAuth2PasswordRequestForm uses 'username' field for email
        user = await service.login(credentials.username, credentials.password)
        access_token = service.issue_token(user)
        return schemas.Token(access_token=access_token)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.get("/me", response_model=schemas.UserRead)
async def read_current_user(
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
) -> schemas.UserRead:
    """Get current authenticated user information."""
    return current_user
