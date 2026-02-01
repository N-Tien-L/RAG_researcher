from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from jose import JWTError, jwt


class TokenDecodeError(Exception):
    """Raised when a JWT cannot be decoded or is invalid."""


def create_access_token(
    claims: Dict[str, Any],
    secret_key: str,
    algorithm: str,
    expires_minutes: int,
) -> str:
    """Create a signed JWT with an expiration claim."""
    to_encode = claims.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def decode_access_token(token: str, secret_key: str, algorithm: str) -> Dict[str, Any]:
    """Decode and validate a JWT, raising TokenDecodeError on failure."""
    try:
        return jwt.decode(token, secret_key, algorithms=[algorithm])
    except JWTError as exc:  # pragma: no cover - jose-specific errors map here
        raise TokenDecodeError("Invalid or expired token") from exc
