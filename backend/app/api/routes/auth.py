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
    """Authenticate a user and return a JWT access token.

    Args:
        credentials: OAuth2 password form data.  Note: ``OAuth2PasswordRequestForm``
            uses the ``username`` field to accept the user's **email address**.
        service: Auth service for credential validation.

    Returns:
        schemas.Token: JWT bearer token with ``access_token`` and ``token_type``.

    Raises:
        HTTPException: 401 Unauthorized if credentials are incorrect.
    """
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
    """Return the profile of the currently authenticated user.

    Requires a valid JWT Bearer token in the ``Authorization`` header.

    Args:
        current_user: User resolved from the Bearer token by ``deps.current_user``.

    Returns:
        schemas.UserRead: The authenticated user's profile data.
    """
    return current_user
