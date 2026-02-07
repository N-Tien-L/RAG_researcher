"""Configuration management using Pydantic BaseSettings."""

import os
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------
    # App
    # -------------------------
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "RAG Researcher API")
    VERSION: str = os.getenv("VERSION", "0.1.0")
    API_PREFIX: str = os.getenv("API_PREFIX", "/api")

    # -------------------------
    # CORS
    # -------------------------
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")

    @field_validator("CORS_ORIGINS")
    @classmethod
    def parse_cors_origins(cls, v: str) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in v.split(",")]

    # -------------------------
    # Database
    # -------------------------
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "changeme")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "my_rag_db")

    # Connection pool settings
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "20"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))

    @property
    def DATABASE_URL(self) -> str:
        """Construct async database URL with asyncpg driver."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # -------------------------
    # Vector DB
    # -------------------------
    VECTOR_BACKEND: str = os.getenv("VECTOR_BACKEND", "pgvector")

    # -------------------------
    # Embeddings
    # -------------------------
    TEI_URL: str = os.getenv("TEI_URL", "http://localhost:8080")
    TEI_MAX_BATCH: int = int(os.getenv("TEI_MAX_BATCH", "8"))
    TEI_MODE: str = os.getenv("TEI_MODE", "passage")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "384"))

    # -------------------------
    # LLM / Models
    # -------------------------
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gemma3:1b")
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_TEMPERATURE: float = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "30"))
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "3"))

    # -------------------------
    # Auth
    # -------------------------
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")

    # -------------------------
    # Rate Limiting
    # -------------------------
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    RATE_LIMIT_CLEANUP_INTERVAL: int = int(os.getenv("RATE_LIMIT_CLEANUP_INTERVAL", "300"))

    # -------------------------
    # Redis Cache
    # -------------------------
    REDIS_ENABLED: bool = os.getenv("REDIS_ENABLED", "true").lower() == "true"
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD", None)
    CACHE_TTL_EMBEDDINGS: int = int(os.getenv("CACHE_TTL_EMBEDDINGS", "3600"))
    CACHE_TTL_LLM: int = int(os.getenv("CACHE_TTL_LLM", "1800"))
    CACHE_KEY_PREFIX: str = os.getenv("CACHE_KEY_PREFIX", "rag_cache")

    @property
    def REDIS_CONNECTION_URL(self) -> str:
        """Return the Redis connection URL.

        Prefers the explicit ``REDIS_URL`` env var when it has been set to a
        non-default value.  Otherwise falls back to constructing the URL from
        individual host/port/db/password components.
        """
        default_url = "redis://localhost:6379/0"
        if self.REDIS_URL and self.REDIS_URL != default_url:
            return self.REDIS_URL
        if self.REDIS_PASSWORD:
            return (
                f"redis://:{self.REDIS_PASSWORD}"
                f"@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
            )
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # -------------------------
    # File uploads
    # -------------------------
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")

    @field_validator("UPLOAD_DIR")
    @classmethod
    def create_upload_dir(cls, v: str) -> Path:
        """Ensure upload directory exists."""
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return path


# Global settings instance
settings = Settings()


def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Legacy helper for backwards compatibility.
    
    Deprecated: Use settings object directly instead.
    """
    return os.getenv(key, default)
