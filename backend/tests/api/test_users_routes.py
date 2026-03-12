"""Tests for users API routes."""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.db.models import User


@pytest.mark.asyncio
class TestUsersRoutes:
    """Test suite for /api/users routes."""

    async def test_create_user_success(self, client: AsyncClient):
        """Test POST /api/users/ creates new user."""
        response = await client.post(
            "/api/users/",
            json={
                "email": "newuser@example.com",
                "username": "newuser",
                "password": "securepass123",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["username"] == "newuser"
        assert "id" in data
        assert "created_at" in data
        assert "password" not in data  # Password should not be returned

    async def test_create_user_duplicate_email(
        self,
        client: AsyncClient,
        test_user: User,
    ):
        """Test creating user with duplicate email returns 409."""
        response = await client.post(
            "/api/users/",
            json={
                "email": "test@example.com",  # Already exists
                "username": "differentuser",
                "password": "password123",
            },
        )

        assert response.status_code == 409

    async def test_create_user_invalid_email(self, client: AsyncClient):
        """Test creating user with invalid email returns 422."""
        response = await client.post(
            "/api/users/",
            json={
                "email": "notanemail",
                "username": "user",
                "password": "pass",
            },
        )

        assert response.status_code == 422

    async def test_create_user_missing_password(self, client: AsyncClient):
        """Test creating user without password returns 422."""
        response = await client.post(
            "/api/users/",
            json={
                "email": "user@example.com",
                "username": "user",
            },
        )

        assert response.status_code == 422

    async def test_get_user_success(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ):
        """Test GET /api/users/{user_id} returns user details."""
        response = await authenticated_client.get(f"/api/users/{test_user.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_user.id)
        assert data["email"] == test_user.email
        assert data["username"] == test_user.username

    async def test_get_user_not_found(self, authenticated_client: AsyncClient):
        """Test GET /api/users/{user_id} with non-existent ID returns 404."""
        fake_id = uuid4()
        response = await authenticated_client.get(f"/api/users/{fake_id}")

        assert response.status_code == 404

    async def test_get_user_requires_authentication(
        self,
        client: AsyncClient,
        test_user: User,
    ):
        """Test GET /api/users/{user_id} without auth returns 401."""
        response = await client.get(f"/api/users/{test_user.id}")

        assert response.status_code == 401

    async def test_list_users_success(
        self,
        authenticated_client: AsyncClient,
        user_factory,
    ):
        """Test GET /api/users/ returns list of users."""
        # Create a few users
        await user_factory(email="user1@example.com")
        await user_factory(email="user2@example.com")

        response = await authenticated_client.get("/api/users/")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2  # At least the created users

    async def test_list_users_with_pagination(
        self,
        authenticated_client: AsyncClient,
        user_factory,
    ):
        """Test GET /api/users/ with skip and limit parameters."""
        # Create users
        for i in range(5):
            await user_factory(email=f"paginate{i}@example.com")

        # Get first page
        response = await authenticated_client.get("/api/users/?skip=0&limit=2")
        assert response.status_code == 200
        page1 = response.json()
        assert len(page1) == 2

        # Get second page
        response = await authenticated_client.get("/api/users/?skip=2&limit=2")
        assert response.status_code == 200
        page2 = response.json()
        assert len(page2) == 2

        # Pages should have different users
        assert page1[0]["id"] != page2[0]["id"]

    async def test_list_users_requires_authentication(self, client: AsyncClient):
        """Test GET /api/users/ without auth returns 401."""
        response = await client.get("/api/users/")

        assert response.status_code == 401

    async def test_update_user_email(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ):
        """Test PATCH /api/users/{user_id} updates email."""
        response = await authenticated_client.patch(
            f"/api/users/{test_user.id}",
            json={"email": "updated@example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "updated@example.com"
        assert data["id"] == str(test_user.id)

    async def test_update_user_username(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ):
        """Test PATCH /api/users/{user_id} updates username."""
        response = await authenticated_client.patch(
            f"/api/users/{test_user.id}",
            json={"username": "newusername"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "newusername"

    async def test_update_user_not_found(self, authenticated_client: AsyncClient):
        """Test PATCH /api/users/{user_id} with non-existent ID returns 404."""
        fake_id = uuid4()
        response = await authenticated_client.patch(
            f"/api/users/{fake_id}",
            json={"email": "new@example.com"},
        )

        assert response.status_code == 404

    async def test_update_user_requires_authentication(
        self,
        client: AsyncClient,
        test_user: User,
    ):
        """Test PATCH /api/users/{user_id} without auth returns 401."""
        response = await client.patch(
            f"/api/users/{test_user.id}",
            json={"email": "new@example.com"},
        )

        assert response.status_code == 401

    async def test_update_user_invalid_email(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ):
        """Test PATCH /api/users/{user_id} with invalid email returns 422."""
        response = await authenticated_client.patch(
            f"/api/users/{test_user.id}",
            json={"email": "notanemail"},
        )

        assert response.status_code == 422

    async def test_delete_user_success(
        self,
        authenticated_client: AsyncClient,
        user_factory,
    ):
        """Test DELETE /api/users/{user_id} deletes user."""
        # Create user to delete
        user = await user_factory(email="todelete@example.com")

        response = await authenticated_client.delete(f"/api/users/{user.id}")

        assert response.status_code == 204

        # Verify deleted - should return 404
        get_response = await authenticated_client.get(f"/api/users/{user.id}")
        assert get_response.status_code == 404

    async def test_delete_user_not_found(self, authenticated_client: AsyncClient):
        """Test DELETE /api/users/{user_id} with non-existent ID returns 404."""
        fake_id = uuid4()
        response = await authenticated_client.delete(f"/api/users/{fake_id}")

        assert response.status_code == 404

    async def test_delete_user_requires_authentication(
        self,
        client: AsyncClient,
        test_user: User,
    ):
        """Test DELETE /api/users/{user_id} without auth returns 401."""
        response = await client.delete(f"/api/users/{test_user.id}")

        assert response.status_code == 401

    async def test_create_user_without_username(self, client: AsyncClient):
        """Test creating user without username (optional field) succeeds."""
        response = await client.post(
            "/api/users/",
            json={
                "email": "nouser@example.com",
                "password": "password123",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "nouser@example.com"
        assert data["username"] is None

    async def test_update_user_partial(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ):
        """Test partial update (only one field) leaves other fields unchanged."""
        # Update only email
        response = await authenticated_client.patch(
            f"/api/users/{test_user.id}",
            json={"email": "partialemail@example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "partialemail@example.com"
        # Username should remain unchanged
        assert data["username"] == test_user.username

    async def test_list_users_default_pagination(
        self,
        authenticated_client: AsyncClient,
        user_factory,
    ):
        """Test that default skip=0 and limit=100 work correctly."""
        response = await authenticated_client.get("/api/users/")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should not exceed 100 users (default limit)
        assert len(data) <= 100
