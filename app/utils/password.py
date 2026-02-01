import bcrypt


def hash_password(pw: str) -> str:
    """Hash a plaintext password to a UTF-8 string."""
    hashed: bytes = bcrypt.hashpw(pw.encode("utf-8"), salt=bcrypt.gensalt())
    return hashed.decode("utf-8")


def check_password(raw: str, hashed: str) -> bool:
    """Verify a plaintext password against a stored hash."""
    return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))