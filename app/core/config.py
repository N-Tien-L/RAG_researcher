"""Configuration helpers."""

import os
from typing import List, Optional

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Fetch environment variable with optional default."""
    return os.getenv(key, default)

class Settings:
    # -------------------------
    # App
    # -------------------------
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "Rag Researcher API")
    VERSION: str = os.getenv("VERSION", "0.1.0")
    API_PREFIX: str = os.getenv("API_PREFIX", "/api")

    # -------------------------
    # CORS
    # -------------------------
    CORS_ORIGINS: List[str] = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173"
    ).split(",")

    # -------------------------
    # VECTOR DB
    # -------------------------
    VECTOR_BACKEND: str = os.getenv("VECTOR_BACKEND", "pgvector")

    # -------------------------
    # POSTGRES DB URL
    # -------------------------
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "changeme")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")

    DATABASE_URL = (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )

    # -------------------------
    # AI / Models
    # -------------------------
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "http://localhost:8080")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "1024"))

    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gemma3:1b")
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_TEMPERATURE: str = os.getenv("OLLAMA_TEMPERATURE", 0.2)

    # -------------------------
    # Auth
    # -------------------------
    SECRET_KEY: str = os.getenv("SECRET_KEY")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")


settings = Settings()
