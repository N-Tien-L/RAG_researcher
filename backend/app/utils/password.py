"""Password hashing and verification using bcrypt.

Uses ``bcrypt.gensalt()`` with default work factor so that security
parameters follow bcrypt library defaults and can be updated by
upgrading the ``bcrypt`` package without code changes.
"""
import bcrypt


def hash_password(pw: str) -> str:
    """Hash a plaintext password with bcrypt and return a UTF-8 string.

    Args:
        pw: Plaintext password to hash.

    Returns:
        str: bcrypt-hashed password encoded as a UTF-8 string, suitable
        for storage in the ``User.password_hash`` column.
    """
    hashed: bytes = bcrypt.hashpw(pw.encode("utf-8"), salt=bcrypt.gensalt())
    return hashed.decode("utf-8")


def check_password(raw: str, hashed: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash.

    Args:
        raw: Plaintext password supplied by the user at login.
        hashed: bcrypt hash string retrieved from ``User.password_hash``.

    Returns:
        bool: ``True`` if the password matches, ``False`` otherwise.
    """
    return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))