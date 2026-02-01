# shared FastAPI dependencies

from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import schemas
from app.db.sessions import get_db
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.exceptions import AuthenticationError
from app.services.source_service import SourceService
from app.services.user_service import UserService


oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_PREFIX}/auth/login")


def db_session() -> Generator[Session, None, None]:
    """Provide a SQLAlchemy session per-request."""

    yield from get_db()


def user_service(db: Session = Depends(db_session)) -> UserService:
    """Dependency to inject ChatService with a live DB session."""

    return UserService(db)


def auth_service(db: Session = Depends(db_session)) -> AuthService:
    """Dependency to inject AuthService with a live DB session."""

    return AuthService(db)


def chat_service(db: Session = Depends(db_session)) -> ChatService:
    """Dependency to inject ChatService with a live DB session."""

    return ChatService(db)


def source_service(db: Session = Depends(db_session)) -> SourceService:
    """Dependency to inject SourceService with a live DB session."""

    return SourceService(db)


def current_user(
    token: str = Depends(oauth2_scheme),
    service: AuthService = Depends(auth_service),
) -> schemas.UserRead:
    try:
        return service.get_current_user(token)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        ) from exc