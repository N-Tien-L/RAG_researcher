"""E2E journey: user registration → update profile → re-login → delete.

Exercises the full auth + user CRUD flow with a real DB, verifying that
mutations are durable and immediately reflected in subsequent requests.
"""

from __future__ import annotations

import pytest
from faker import Faker
from httpx import AsyncClient

pytestmark = pytest.mark.e2e

fake = Faker()


class TestUserCRUDJourney:
    """User CRUD end-to-end journey tests."""

    @pytest.mark.asyncio
    async def test_update_email_then_login_with_new_email(
        self,
        client: AsyncClient,
    ) -> None:
        """PATCH /users/{id} with a new email allows logging in using that email.

        Steps
        -----
        1. Register a new user.
        2. Login with original email → obtain token.
        3. PATCH email to a new address.
        4. Login again with the new email → 200 + access_token returned.
        """
        email = fake.email()
        password = "SecurePass123!"
        new_email = f"updated_{fake.email()}"

        # 1. Register
        reg_resp = await client.post(
            "/api/users/",
            json={"email": email, "username": fake.user_name(), "password": password},
        )
        assert reg_resp.status_code == 201, reg_resp.text
        user_id = reg_resp.json()["id"]

        # 2. Login
        login_resp = await client.post(
            "/api/auth/login",
            data={"username": email, "password": password},
        )
        assert login_resp.status_code == 200, login_resp.text
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Update email
        patch_resp = await client.patch(
            f"/api/users/{user_id}",
            json={"email": new_email},
            headers=headers,
        )
        assert patch_resp.status_code == 200, patch_resp.text
        assert patch_resp.json()["email"] == new_email

        # 4. Re-login with new email
        new_login_resp = await client.post(
            "/api/auth/login",
            data={"username": new_email, "password": password},
        )
        assert new_login_resp.status_code == 200, new_login_resp.text
        assert "access_token" in new_login_resp.json()

    @pytest.mark.asyncio
    async def test_delete_user_then_login_fails(
        self,
        client: AsyncClient,
    ) -> None:
        """DELETE /users/{id} removes the user; subsequent login returns 401.

        Steps
        -----
        1. Register and login.
        2. DELETE the user.
        3. Attempt login with the same credentials → 401.
        """
        email = fake.email()
        password = "DeleteMe123!"

        # 1. Register
        reg_resp = await client.post(
            "/api/users/",
            json={"email": email, "username": fake.user_name(), "password": password},
        )
        assert reg_resp.status_code == 201, reg_resp.text
        user_id = reg_resp.json()["id"]

        # Login
        login_resp = await client.post(
            "/api/auth/login",
            data={"username": email, "password": password},
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Delete
        del_resp = await client.delete(f"/api/users/{user_id}", headers=headers)
        assert del_resp.status_code == 204

        # 3. Login should now fail
        retry_resp = await client.post(
            "/api/auth/login",
            data={"username": email, "password": password},
        )
        assert retry_resp.status_code == 401

    @pytest.mark.asyncio
    async def test_update_username_is_reflected_in_me(
        self,
        client: AsyncClient,
    ) -> None:
        """GET /auth/me returns the updated username after PATCH /users/{id}.

        Steps
        -----
        1. Register and login.
        2. PATCH username to a new value.
        3. GET /auth/me with the same token → returns new username.
        """
        email = fake.email()
        password = "UsernamePass123!"
        new_username = fake.user_name()

        # 1. Register
        reg_resp = await client.post(
            "/api/users/",
            json={"email": email, "username": fake.user_name(), "password": password},
        )
        assert reg_resp.status_code == 201, reg_resp.text
        user_id = reg_resp.json()["id"]

        # Login
        login_resp = await client.post(
            "/api/auth/login",
            data={"username": email, "password": password},
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Update username
        patch_resp = await client.patch(
            f"/api/users/{user_id}",
            json={"username": new_username},
            headers=headers,
        )
        assert patch_resp.status_code == 200, patch_resp.text
        assert patch_resp.json()["username"] == new_username

        # 3. Verify via /auth/me
        me_resp = await client.get("/api/auth/me", headers=headers)
        assert me_resp.status_code == 200, me_resp.text
        assert me_resp.json()["username"] == new_username
