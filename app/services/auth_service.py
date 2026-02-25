"""Business logic for authentication and authorization."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import config
from app.db import models, schemas
from app.services.exceptions import AuthenticationError
from app.utils.auth import TokenDecodeError, create_access_token, decode_access_token
from app.utils.password import check_password


class AuthService:
    """Service layer for authentication operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def login(self, email: str, password: str) -> schemas.UserRead:
        """Authenticate user with email and password.
        
        Args:
            email: User email address.
            password: Plain text password.
            
        Returns:
            Authenticated user data.
            
        Raises:
            AuthenticationError: If credentials are invalid.
        """
        stmt = select(models.User).where(models.User.email == email)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user or not check_password(password, user.password_hash):
            raise AuthenticationError("Invalid email or password")

        return schemas.UserRead.model_validate(user)

    def issue_token(self, user: schemas.UserRead) -> str:
        """Generate JWT access token for authenticated user.
        
        Args:
            user: Authenticated user data.
            
        Returns:
            JWT access token string.
        """
        claims = {"sub": str(user.id)}
        return create_access_token(
            claims=claims,
            secret_key=config.settings.SECRET_KEY,
            algorithm=config.settings.JWT_ALGORITHM,
            expires_minutes=config.settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        )

    async def get_current_user(self, token: str) -> schemas.UserRead:
        """Retrieve user from JWT token.
        
        Args:
            token: JWT access token.
            
        Returns:
            Current user data.
            
        Raises:
            AuthenticationError: If token is invalid or user not found.
        """
        try:
            payload = decode_access_token(
                token,
                config.settings.SECRET_KEY,
                config.settings.JWT_ALGORITHM,
            )
        except TokenDecodeError as exc:
            raise AuthenticationError("Invalid or expired token") from exc

        sub = payload.get("sub")
        if not sub:
            raise AuthenticationError("Invalid token payload")

        user = await self.db.get(models.User, UUID(sub))
        if not user:
            raise AuthenticationError("User not found")

        return schemas.UserRead.model_validate(user)
