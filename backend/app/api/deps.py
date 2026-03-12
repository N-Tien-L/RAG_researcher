"""Shared FastAPI dependencies."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import schemas
from app.db.sessions import get_db
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.exceptions import AuthenticationError
from app.services.source_service import SourceService
from app.services.user_service import UserService


oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_PREFIX}/auth/login")


async def db_session(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncGenerator[AsyncSession, None]:
    """Provide an async SQLAlchemy session per-request.

    Args:
        db: Database session injected by FastAPI dependency system.

    Yields:
        AsyncSession: Live database session scoped to the request.
    """
    yield db


def user_service(db: Annotated[AsyncSession, Depends(db_session)]) -> UserService:
    """Dependency to inject UserService with a live DB session."""
    return UserService(db)


def auth_service(db: Annotated[AsyncSession, Depends(db_session)]) -> AuthService:
    """Dependency to inject AuthService with a live DB session."""
    return AuthService(db)


def chat_service(db: Annotated[AsyncSession, Depends(db_session)]) -> ChatService:
    """Dependency to inject ChatService with a live DB session."""
    return ChatService(db)


def source_service(db: Annotated[AsyncSession, Depends(db_session)]) -> SourceService:
    """Dependency to inject SourceService with a live DB session."""
    return SourceService(db)


async def current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    service: Annotated[AuthService, Depends(auth_service)],
) -> schemas.UserRead:
    """Get current authenticated user from JWT token."""
    try:
        user = await service.get_current_user(token)
        structlog.contextvars.bind_contextvars(user_id=str(user.id))
        return user
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc