from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api import deps
from app.db import schemas
from app.services.auth_service import AuthService
from app.services.exceptions import AuthenticationError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.Token)
def login(
    credentials: OAuth2PasswordRequestForm = Depends(),
    service: AuthService = Depends(deps.auth_service),
) -> schemas.Token:
    try:
        user = service.login(credentials.username, credentials.password) # username holds the email
        access_token = service.issue_token(user)
        return schemas.Token(access_token=access_token)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        ) from exc


@router.get("/me", response_model=schemas.UserRead)
def read_current_user(current_user: schemas.UserRead = Depends(deps.current_user)) -> schemas.UserRead:
    return current_user
