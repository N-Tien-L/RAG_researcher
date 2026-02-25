"""Tests for authentication routes."""

import pytest
from httpx import AsyncClient

from app.db.models import User


class TestLogin:
    """Test cases for POST /api/auth/login endpoint."""
    
    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, test_user: User):
        """Valid credentials return access token."""
        response = await client.post(
            "/api/auth/login",
            data={
                "username": test_user.email,
                "password": "testpassword123",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 0
    
    @pytest.mark.asyncio
    async def test_login_invalid_email(self, client: AsyncClient):
        """Non-existent email returns 401."""
        response = await client.post(
            "/api/auth/login",
            data={
                "username": "nonexistent@example.com",
                "password": "testpassword123",
            },
        )
        
        assert response.status_code == 401
        assert "detail" in response.json()
    
    @pytest.mark.asyncio
    async def test_login_invalid_password(self, client: AsyncClient, test_user: User):
        """Wrong password returns 401."""
        response = await client.post(
            "/api/auth/login",
            data={
                "username": test_user.email,
                "password": "wrongpassword",
            },
        )
        
        assert response.status_code == 401
        assert "detail" in response.json()
    
    @pytest.mark.asyncio
    async def test_login_missing_credentials(self, client: AsyncClient):
        """Missing fields return 422."""
        response = await client.post(
            "/api/auth/login",
            data={},
        )
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_login_token_structure(self, client: AsyncClient, test_user: User):
        """Token response has correct structure."""
        response = await client.post(
            "/api/auth/login",
            data={
                "username": test_user.email,
                "password": "testpassword123",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert set(data.keys()) == {"access_token", "token_type"}
        assert data["token_type"] == "bearer"
        
        # Verify token is a non-empty string
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 50  # JWT tokens are long


class TestGetCurrentUser:
    """Test cases for GET /api/auth/me endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_current_user_success(self, authenticated_client: AsyncClient, test_user: User):
        """Valid token returns user info."""
        response = await authenticated_client.get("/api/auth/me")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == str(test_user.id)
        assert data["email"] == test_user.email
        assert data["username"] == test_user.username
        assert "password_hash" not in data  # Should not expose password
    
    @pytest.mark.asyncio
    async def test_get_current_user_no_token(self, client: AsyncClient):
        """Missing token returns 401."""
        response = await client.get("/api/auth/me")
        
        assert response.status_code == 401
        assert "detail" in response.json()
    
    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, client: AsyncClient):
        """Invalid token returns 401."""
        client.headers["Authorization"] = "Bearer invalid_token_here"
        response = await client.get("/api/auth/me")
        
        assert response.status_code == 401
        assert "detail" in response.json()
    
    @pytest.mark.asyncio
    async def test_get_current_user_expired_token(self, client: AsyncClient, test_settings, test_user: User):
        """Expired token returns 401."""
        from jose import jwt
        from datetime import datetime, timedelta
        
        # Create expired token
        payload = {
            "sub": str(test_user.id),
            "exp": datetime.utcnow() - timedelta(minutes=1),  # Expired 1 minute ago
            "iat": datetime.utcnow() - timedelta(minutes=31),
        }
        expired_token = jwt.encode(payload, test_settings.SECRET_KEY, algorithm="HS256")
        
        client.headers["Authorization"] = f"Bearer {expired_token}"
        response = await client.get("/api/auth/me")
        
        assert response.status_code == 401
        assert "detail" in response.json()
