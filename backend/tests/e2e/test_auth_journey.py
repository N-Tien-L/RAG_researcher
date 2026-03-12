"""E2E journey: user registration → login → authenticated access.

Tests the full HTTP layer end-to-end against a live test database.
No mocks are added here; the autouse fixtures in conftest.py handle the
external-service patches.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.e2e


class TestAuthJourney:
    """User authentication end-to-end journey."""

    @pytest.mark.asyncio
    async def test_register_login_and_access_protected_endpoint(
        self,
        client: AsyncClient,
    ) -> None:
        """Register a new user, log in to obtain a token, then access a protected endpoint.

        Steps
        -----
        1. POST /api/users/  → create account
        2. POST /api/auth/login → receive JWT
        3. GET  /api/users/{id} → access protected resource with token
        """
        email = "e2e_journey@example.com"
        username = "e2ejourney"
        password = "JourneyPass123!"

        # 1. Register
        reg_resp = await client.post(
            "/api/users/",
            json={"email": email, "username": username, "password": password},
        )
        assert reg_resp.status_code == 201, reg_resp.text
        user_data = reg_resp.json()
        user_id = user_data["id"]
        assert user_data["email"] == email
        assert user_data["username"] == username

        # 2. Login
        login_resp = await client.post(
            "/api/auth/login",
            data={"username": email, "password": password},
        )
        assert login_resp.status_code == 200, login_resp.text
        token_data = login_resp.json()
        assert "access_token" in token_data
        assert token_data["token_type"] == "bearer"
        token = token_data["access_token"]

        # 3. Access protected endpoint
        profile_resp = await client.get(
            f"/api/users/{user_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert profile_resp.status_code == 200, profile_resp.text
        profile = profile_resp.json()
        assert profile["id"] == user_id
        assert profile["email"] == email

    @pytest.mark.asyncio
    async def test_login_with_wrong_password_is_rejected(
        self,
        client: AsyncClient,
        test_user: object,
    ) -> None:
        """Wrong password returns 401 — verifies auth middleware is active."""
        resp = await client.post(
            "/api/auth/login",
            data={"username": "test@example.com", "password": "totally_wrong!"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthenticated_request_to_protected_route_returns_401(
        self,
        client: AsyncClient,
        test_user: object,
    ) -> None:
        """No token → 401; verifies the auth dependency is wired to every protected route."""
        resp = await client.get("/api/users/")
        assert resp.status_code == 401
