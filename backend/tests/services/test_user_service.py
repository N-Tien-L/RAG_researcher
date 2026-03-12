"""Tests for UserService - user management operations."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import schemas
from app.db.models import User
from app.services.exceptions import ResourceConflict, ResourceNotFound
from app.services.user_service import UserService


@pytest.mark.asyncio
class TestUserService:
    """Test suite for UserService."""

    async def test_create_user_success(self, test_db_session: AsyncSession):
        """Test successful user creation."""
        service = UserService(test_db_session)

        user_in = schemas.UserCreate(
            email="newuser@example.com",
            username="newuser",
            password="securepassword123",
        )

        user = await service.create_user(user_in)

        assert user.email == "newuser@example.com"
        assert user.username == "newuser"
        assert user.id is not None
        assert user.created_at is not None

    async def test_create_user_without_username(self, test_db_session: AsyncSession):
        """Test creating user without username (optional field)."""
        service = UserService(test_db_session)

        user_in = schemas.UserCreate(
            email="noname@example.com",
            username=None,
            password="password123",
        )

        user = await service.create_user(user_in)

        assert user.email == "noname@example.com"
        assert user.username is None

    async def test_create_user_duplicate_email(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test that duplicate email raises ResourceConflict."""
        service = UserService(test_db_session)

        # Try to create user with existing email
        user_in = schemas.UserCreate(
            email="test@example.com",  # Already exists
            username="anotheruser",
            password="password123",
        )

        with pytest.raises(ResourceConflict) as exc_info:
            await service.create_user(user_in)

        assert "already exists" in str(exc_info.value).lower()

    async def test_create_user_hashes_password(self, test_db_session: AsyncSession):
        """Test that password is hashed on creation."""
        service = UserService(test_db_session)

        plain_password = "myplainpassword"
        user_in = schemas.UserCreate(
            email="hashtest@example.com",
            username="hashtest",
            password=plain_password,
        )

        user = await service.create_user(user_in)

        # Retrieve from DB to check hash
        from sqlalchemy import select
        from app.db.models import User as UserModel

        stmt = select(UserModel).where(UserModel.id == user.id)
        result = await test_db_session.execute(stmt)
        db_user = result.scalar_one()

        # Password should be hashed (not equal to plain)
        assert db_user.password_hash != plain_password
        assert db_user.password_hash.startswith("$2b$")  # bcrypt hash

    async def test_get_user_success(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test getting user by ID."""
        service = UserService(test_db_session)

        user = await service.get_user(test_user.id)

        assert user.id == test_user.id
        assert user.email == test_user.email
        assert user.username == test_user.username

    async def test_get_user_not_found(self, test_db_session: AsyncSession):
        """Test getting non-existent user raises ResourceNotFound."""
        service = UserService(test_db_session)

        fake_id = uuid4()

        with pytest.raises(ResourceNotFound) as exc_info:
            await service.get_user(fake_id)

        assert "User not found" in str(exc_info.value)

    async def test_list_users_empty(self, test_db_session: AsyncSession):
        """Test listing users when database is empty (except setup users)."""
        service = UserService(test_db_session)

        users = await service.list_users()

        # Should return at least empty list or test_user
        assert isinstance(users, list)

    async def test_list_users_with_pagination(
        self,
        test_db_session: AsyncSession,
        user_factory,
    ):
        """Test listing users with skip and limit."""
        # Create multiple users
        for i in range(5):
            await user_factory(email=f"user{i}@example.com", username=f"user{i}")

        service = UserService(test_db_session)

        # Get first 2 users
        users_page1 = await service.list_users(skip=0, limit=2)
        assert len(users_page1) == 2

        # Get next 2 users
        users_page2 = await service.list_users(skip=2, limit=2)
        assert len(users_page2) == 2

        # Different users on each page
        assert users_page1[0].id != users_page2[0].id

    async def test_list_users_respects_limit(
        self,
        test_db_session: AsyncSession,
        user_factory,
    ):
        """Test that limit parameter is respected."""
        # Create 10 users
        for i in range(10):
            await user_factory(email=f"limit{i}@example.com")

        service = UserService(test_db_session)

        users = await service.list_users(skip=0, limit=5)

        assert len(users) == 5

    async def test_update_user_email(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test updating user email."""
        service = UserService(test_db_session)

        update_data = schemas.UserUpdate(
            email="newemail@example.com",
            username=None,
        )

        updated_user = await service.update_user(test_user.id, update_data)

        assert updated_user.email == "newemail@example.com"
        assert updated_user.username == test_user.username  # Unchanged

    async def test_update_user_username(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test updating user username."""
        service = UserService(test_db_session)

        update_data = schemas.UserUpdate(
            email=None,
            username="newusername",
        )

        updated_user = await service.update_user(test_user.id, update_data)

        assert updated_user.username == "newusername"
        assert updated_user.email == test_user.email  # Unchanged

    async def test_update_user_both_fields(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test updating both email and username."""
        service = UserService(test_db_session)

        update_data = schemas.UserUpdate(
            email="updatedboth@example.com",
            username="updatedboth",
        )

        updated_user = await service.update_user(test_user.id, update_data)

        assert updated_user.email == "updatedboth@example.com"
        assert updated_user.username == "updatedboth"

    async def test_update_user_not_found(self, test_db_session: AsyncSession):
        """Test updating non-existent user raises ResourceNotFound."""
        service = UserService(test_db_session)

        fake_id = uuid4()
        update_data = schemas.UserUpdate(email="test@test.com")

        with pytest.raises(ResourceNotFound) as exc_info:
            await service.update_user(fake_id, update_data)

        assert "User not found" in str(exc_info.value)

    async def test_update_user_duplicate_email_conflict(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        user_factory,
    ):
        """Test updating to existing email raises ResourceConflict."""
        # Create another user
        other_user = await user_factory(email="other@example.com")

        service = UserService(test_db_session)

        # Try to update test_user to other_user's email
        update_data = schemas.UserUpdate(email="other@example.com")

        with pytest.raises(ResourceConflict) as exc_info:
            await service.update_user(test_user.id, update_data)

        assert "conflict" in str(exc_info.value).lower()

    async def test_delete_user_success(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test successful user deletion."""
        service = UserService(test_db_session)

        # Delete user
        await service.delete_user(test_user.id)

        # Verify user is deleted
        deleted_user = await test_db_session.get(User, test_user.id)
        assert deleted_user is None

    async def test_delete_user_not_found(self, test_db_session: AsyncSession):
        """Test deleting non-existent user raises ResourceNotFound."""
        service = UserService(test_db_session)

        fake_id = uuid4()

        with pytest.raises(ResourceNotFound) as exc_info:
            await service.delete_user(fake_id)

        assert "User not found" in str(exc_info.value)

    async def test_delete_user_is_permanent(
        self,
        test_db_session: AsyncSession,
        user_factory,
    ):
        """Test that deleted user cannot be retrieved."""
        user = await user_factory(email="delete@example.com")
        service = UserService(test_db_session)

        # Delete
        await service.delete_user(user.id)

        # Try to get - should raise ResourceNotFound
        with pytest.raises(ResourceNotFound):
            await service.get_user(user.id)

    async def test_service_initialization(self, test_db_session: AsyncSession):
        """Test service initializes correctly."""
        service = UserService(test_db_session)

        assert service.db is test_db_session

    async def test_update_user_with_no_changes(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ):
        """Test update with no fields changed."""
        service = UserService(test_db_session)

        # Update with None values (no changes)
        update_data = schemas.UserUpdate(email=None, username=None)

        updated_user = await service.update_user(test_user.id, update_data)

        # Should return user with original values
        assert updated_user.email == test_user.email
        assert updated_user.username == test_user.username
