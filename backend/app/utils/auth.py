"""JWT creation and validation utilities.

Provides :func:`create_access_token` and :func:`decode_access_token` for
produce and consuming signed JWT Bearer tokens.  Both functions are thin
wrappers over ``python-jose`` so the algorithm and secret key are
configurable at call sites (consumed by ``AuthService``).
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from jose import JWTError, jwt


class TokenDecodeError(Exception):
    """Raised when a JWT cannot be decoded, has expired, or fails signature
    verification.

    Caught by ``AuthService`` and re-raised as
    :class:`~app.services.exceptions.AuthenticationError` for the API layer.
    """


def create_access_token(
    claims: Dict[str, Any],
    secret_key: str,
    algorithm: str,
    expires_minutes: int,
) -> str:
    """Sign and return a JWT containing the provided claims plus an expiry.

    Args:
        claims: Arbitrary claims to embed (e.g. ``{"sub": user_id}``).
        secret_key: HMAC secret or RSA private key used for signing.
        algorithm: Jose algorithm identifier (e.g. ``"HS256"``).
        expires_minutes: Token lifetime in minutes from now.

    Returns:
        str: Signed compact JWT string.
    """
    to_encode = claims.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def decode_access_token(token: str, secret_key: str, algorithm: str) -> Dict[str, Any]:
    """Decode and validate a JWT, returning its payload claims.

    Args:
        token: Compact JWT string from the ``Authorization: Bearer`` header.
        secret_key: HMAC secret or RSA public key for signature verification.
        algorithm: Jose algorithm identifier (e.g. ``"HS256"``).

    Returns:
        dict: Decoded claims payload.

    Raises:
        TokenDecodeError: If the token is malformed, expired, or the
            signature is invalid.
    """
    try:
        return jwt.decode(token, secret_key, algorithms=[algorithm])
    except JWTError as exc:  # pragma: no cover - jose-specific errors map here
        raise TokenDecodeError("Invalid or expired token") from exc
