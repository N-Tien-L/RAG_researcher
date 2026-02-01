from typing import List
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import models, schemas
from app.utils.password import hash_password
from app.services.exceptions import ResourceConflict, ResourceNotFound


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_user(self, user_in: schemas.UserCreate) -> schemas.UserRead:
        user = models.User(
            email=user_in.email,
            username=user_in.username,
            password_hash=hash_password(user_in.password)
        )
        self.db.add(user)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ResourceConflict("User with this email or username already exists") from exc
        self.db.refresh(user)
        return schemas.UserRead.model_validate(user)
    
    def get_user(self, user_id: UUID) -> schemas.UserRead:
        user = self.db.get(models.User ,user_id)
        if not user:
            raise ResourceNotFound("User not found")
        return schemas.UserRead.model_validate(user)
    
    def list_user(self, skip: int = 0, limit: int = 100) -> List[schemas.UserRead]:
        users = self.db.query(models.User).offset(skip).limit(limit).all()
        return [schemas.UserRead.model_validate(user) for user in users]
    
    def update_user(self, user_id: UUID, user_update: schemas.UserUpdate) -> schemas.UserRead:
        user = self.db.get(models.User, user_id)
        if not user:
            raise ResourceNotFound("User not found")
        
        if user_update.email:
            user.email = user_update.email
        if user_update.username:
            user.username = user_update.username

        try:
            self.db.commit()
            self.db.refresh(user)
        except IntegrityError as exc:
            self.db.rollback()
            raise ResourceConflict("Update failed: Email/User conflict") from exc
        
        return schemas.UserRead.model_validate(user)
    
    def delete_user(self, user_id: UUID) -> None:
        user = self.db.get(models.User, user_id)
        if not user:
            raise ResourceNotFound("User not found")
        
        self.db.delete(user)
        self.db.commit()