"""Configuration helpers."""

import os
from pathlib import Path
from typing import Optional

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())


def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Fetch environment variable with optional default."""
    return os.getenv(key, default)


def get_db_path(default_name: str = "chroma_db") -> Path:
    """Return Chroma persistence directory path."""
    env_path = get_env("DB_PATH")
    if env_path:
        return Path(env_path)
    return Path.cwd() / default_name
