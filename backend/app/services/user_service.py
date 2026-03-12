"""Business logic for user account management.

Provides :class:`UserService` which handles creating, reading, updating,
and deleting ``User`` records.  Raises :exc:`~services.exceptions.ResourceConflict`
on unique-constraint violations and :exc:`~services.exceptions.ResourceNotFound`
when a user does not exist.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models, schemas
from app.services.exceptions import ResourceConflict, ResourceNotFound
from app.utils.password import hash_password


class UserService:
    """Service layer for user operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_user(self, user_in: schemas.UserCreate) -> schemas.UserRead:
        """Create a new user.
        
        Args:
            user_in: User creation data.
            
        Returns:
            Created user data.
            
        Raises:
            ResourceConflict: If email or username already exists.
        """
        user = models.User(
            email=user_in.email,
            username=user_in.username,
            password_hash=hash_password(user_in.password),
        )
        self.db.add(user)

        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ResourceConflict("User with this email or username already exists") from exc
        
        await self.db.refresh(user)
        return schemas.UserRead.model_validate(user)

    async def get_user(self, user_id: UUID) -> schemas.UserRead:
        """Get user by ID.
        
        Args:
            user_id: UUID of the user.
            
        Returns:
            User data.
            
        Raises:
            ResourceNotFound: If user does not exist.
        """
        user = await self.db.get(models.User, user_id)
        if not user:
            raise ResourceNotFound("User not found")
        return schemas.UserRead.model_validate(user)

    async def list_users(self, skip: int = 0, limit: int = 100) -> list[schemas.UserRead]:
        """List users with pagination.
        
        Args:
            skip: Number of records to skip.
            limit: Maximum number of records to return.
            
        Returns:
            List of users.
        """
        stmt = select(models.User).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        users = result.scalars().all()
        return [schemas.UserRead.model_validate(user) for user in users]

    async def update_user(self, user_id: UUID, user_update: schemas.UserUpdate) -> schemas.UserRead:
        """Update user information.
        
        Args:
            user_id: UUID of the user to update.
            user_update: Updated user data.
            
        Returns:
            Updated user data.
            
        Raises:
            ResourceNotFound: If user does not exist.
            ResourceConflict: If email or username conflicts.
        """
        user = await self.db.get(models.User, user_id)
        if not user:
            raise ResourceNotFound("User not found")

        if user_update.email is not None:
            user.email = user_update.email
        if user_update.username is not None:
            user.username = user_update.username

        try:
            await self.db.commit()
            await self.db.refresh(user)
        except IntegrityError as exc:
            await self.db.rollback()
            raise ResourceConflict("Update failed: Email/User conflict") from exc

        return schemas.UserRead.model_validate(user)

    async def delete_user(self, user_id: UUID) -> None:
        """Delete a user.
        
        Args:
            user_id: UUID of the user to delete.
            
        Raises:
            ResourceNotFound: If user does not exist.
        """
        user = await self.db.get(models.User, user_id)
        if not user:
            raise ResourceNotFound("User not found")

        await self.db.delete(user)
        await self.db.commit()