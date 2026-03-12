"""Tests for AuthService - authentication and authorization."""

from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.services.auth_service import AuthService
from app.services.exceptions import AuthenticationError
from app.utils.password import hash_password


@pytest.mark.asyncio
class TestAuthService:
    """Test suite for AuthService."""

    async def test_login_success(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test successful login with valid credentials."""
        service = AuthService(test_db_session)

        # Login with correct password (from conftest.py fixture: "testpassword123")
        user = await service.login("test@example.com", "testpassword123")

        assert user.email == "test@example.com"
        assert user.username == "testuser"
        assert user.id == test_user.id

    async def test_login_invalid_email(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test login fails with non-existent email."""
        service = AuthService(test_db_session)

        with pytest.raises(AuthenticationError) as exc_info:
            await service.login("nonexistent@example.com", "testpassword123")

        assert "Invalid email or password" in str(exc_info.value)

    async def test_login_invalid_password(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test login fails with incorrect password."""
        service = AuthService(test_db_session)

        with pytest.raises(AuthenticationError) as exc_info:
            await service.login("test@example.com", "wrongpassword")

        assert "Invalid email or password" in str(exc_info.value)

    async def test_login_empty_password(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test login fails with empty password."""
        service = AuthService(test_db_session)

        with pytest.raises(AuthenticationError):
            await service.login("test@example.com", "")

    async def test_issue_token_creates_valid_token(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test token generation for authenticated user."""
        service = AuthService(test_db_session)

        # Login first
        user = await service.login("test@example.com", "testpassword123")

        # Issue token
        token = service.issue_token(user)

        # Token should be non-empty string
        assert isinstance(token, str)
        assert len(token) > 50  # JWT tokens are typically long

    async def test_issue_token_contains_user_id(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test issued token contains user ID in claims."""
        service = AuthService(test_db_session)

        user = await service.login("test@example.com", "testpassword123")
        token = service.issue_token(user)

        # Decode and verify
        from app.utils.auth import decode_access_token
        from app.core import config

        payload = decode_access_token(
            token,
            config.settings.SECRET_KEY,
            config.settings.JWT_ALGORITHM,
        )

        assert payload["sub"] == str(user.id)

    async def test_get_current_user_with_valid_token(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_user_token: str,
    ):
        """Test retrieving user from valid JWT token."""
        service = AuthService(test_db_session)

        # Get user from token
        user = await service.get_current_user(test_user_token)

        assert user.id == test_user.id
        assert user.email == "test@example.com"

    async def test_get_current_user_with_invalid_token(
        self,
        test_db_session: AsyncSession,
    ):
        """Test that invalid token raises AuthenticationError."""
        service = AuthService(test_db_session)

        with pytest.raises(AuthenticationError) as exc_info:
            await service.get_current_user("invalid.token.here")

        assert "Invalid or expired token" in str(exc_info.value)

    async def test_get_current_user_with_expired_token(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test that expired token raises AuthenticationError."""
        service = AuthService(test_db_session)

        # Create expired token (mock expiry)
        from datetime import datetime, timedelta
        from jose import jwt
        from app.core import config

        expired_payload = {
            "sub": str(test_user.id),
            "exp": datetime.utcnow() - timedelta(hours=1),  # Expired 1 hour ago
            "iat": datetime.utcnow() - timedelta(hours=2),
        }
        expired_token = jwt.encode(
            expired_payload,
            config.settings.SECRET_KEY,
            algorithm=config.settings.JWT_ALGORITHM,
        )

        with pytest.raises(AuthenticationError) as exc_info:
            await service.get_current_user(expired_token)

        assert "Invalid or expired token" in str(exc_info.value)

    async def test_get_current_user_with_malformed_payload(
        self,
        test_db_session: AsyncSession,
    ):
        """Test token without 'sub' claim raises error."""
        service = AuthService(test_db_session)

        from jose import jwt
        from app.core import config
        from datetime import datetime, timedelta

        # Token without 'sub' claim
        malformed_payload = {
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
        }
        malformed_token = jwt.encode(
            malformed_payload,
            config.settings.SECRET_KEY,
            algorithm=config.settings.JWT_ALGORITHM,
        )

        with pytest.raises(AuthenticationError) as exc_info:
            await service.get_current_user(malformed_token)

        assert "Invalid token payload" in str(exc_info.value)

    async def test_get_current_user_nonexistent_user(
        self,
        test_db_session: AsyncSession,
    ):
        """Test token for deleted/non-existent user raises error."""
        from uuid import uuid4
        from jose import jwt
        from app.core import config
        from datetime import datetime, timedelta

        # Token for non-existent user
        fake_user_id = uuid4()
        payload = {
            "sub": str(fake_user_id),
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
        }
        token = jwt.encode(
            payload,
            config.settings.SECRET_KEY,
            algorithm=config.settings.JWT_ALGORITHM,
        )

        service = AuthService(test_db_session)

        with pytest.raises(AuthenticationError) as exc_info:
            await service.get_current_user(token)

        assert "User not found" in str(exc_info.value)

    async def test_service_initialization(self, test_db_session: AsyncSession):
        """Test service initializes correctly."""
        service = AuthService(test_db_session)

        assert service.db is test_db_session

    async def test_login_case_sensitive_email(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test that email matching is case-sensitive in database query."""
        service = AuthService(test_db_session)

        # Attempt login with uppercase email
        with pytest.raises(AuthenticationError):
            await service.login("TEST@EXAMPLE.COM", "testpassword123")
