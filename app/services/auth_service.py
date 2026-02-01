from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import models, schemas
from app.services.exceptions import AuthenticationError
from app.utils.auth import TokenDecodeError, create_access_token, decode_access_token
from app.utils.password import check_password


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def login(self, email: str, password: str) -> schemas.UserRead:
        user = self.db.query(models.User).filter(models.User.email == email).first()
        if not user or not check_password(password, user.password_hash):
            raise AuthenticationError("Invalid email or password")

        return schemas.UserRead.model_validate(user)

    def issue_token(self, user: schemas.UserRead) -> str:
        claims = {"sub": str(user.id)}
        return create_access_token(
            claims=claims,
            secret_key=settings.SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            expires_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        )

    def get_current_user(self, token: str) -> schemas.UserRead:
        try:
            payload = decode_access_token(token, settings.SECRET_KEY, settings.JWT_ALGORITHM)
        except TokenDecodeError as exc:
            raise AuthenticationError("Invalid or expired token") from exc

        sub = payload.get("sub")
        if not sub:
            raise AuthenticationError("Invalid token payload")

        user = self.db.get(models.User, UUID(sub))
        if not user:
            raise AuthenticationError("User not found")

        return schemas.UserRead.model_validate(user)
