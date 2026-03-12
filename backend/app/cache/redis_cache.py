"""Async Redis cache client for embedding and LLM response caching."""

import hashlib
import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Module-level singleton
_redis_client: "RedisCacheClient | None" = None


class RedisCacheClient:
    """Async Redis client wrapper with namespace isolation and graceful failure.

    All public methods catch Redis errors and return safe defaults
    so the application continues to work when Redis is unavailable.
    """

    def __init__(self, redis_url: str, key_prefix: str) -> None:
        """Initialize cache client.

        Args:
            redis_url: Redis connection URL.
            key_prefix: Prefix prepended to every key for namespace isolation.
        """
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._client: aioredis.Redis | None = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Establish Redis connection and verify with ping."""
        try:
            self._client = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            await self._client.ping()
            logger.info(
                "redis_connected",
                url=self._redis_url,
                prefix=self._key_prefix,
            )
        except Exception as exc:
            logger.error("redis_connection_failed", error=str(exc))
            self._client = None

    async def disconnect(self) -> None:
        """Close Redis connection gracefully."""
        if self._client is not None:
            try:
                await self._client.aclose()
                logger.info("redis_disconnected")
            except Exception as exc:
                logger.error("redis_disconnect_error", error=str(exc))
            finally:
                self._client = None

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    async def get(self, key: str) -> str | None:
        """Retrieve value by key.

        Args:
            key: Cache key (prefix is added automatically).

        Returns:
            Cached string value or ``None`` on miss / error.
        """
        if self._client is None:
            return None
        try:
            return await self._client.get(self._make_key(key))
        except Exception as exc:
            logger.error("redis_get_error", key=key, error=str(exc))
            return None

    async def set(self, key: str, value: str, ttl: int) -> None:
        """Store value with TTL expiration.

        Args:
            key: Cache key (prefix is added automatically).
            value: String value to store.
            ttl: Time-to-live in seconds.
        """
        if self._client is None:
            return
        try:
            await self._client.set(self._make_key(key), value, ex=ttl)
        except Exception as exc:
            logger.error("redis_set_error", key=key, error=str(exc))

    async def delete(self, key: str) -> None:
        """Delete a specific key.

        Args:
            key: Cache key (prefix is added automatically).
        """
        if self._client is None:
            return
        try:
            await self._client.delete(self._make_key(key))
        except Exception as exc:
            logger.error("redis_delete_error", key=key, error=str(exc))

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache.

        Args:
            key: Cache key (prefix is added automatically).

        Returns:
            ``True`` if the key exists, ``False`` otherwise or on error.
        """
        if self._client is None:
            return False
        try:
            return bool(await self._client.exists(self._make_key(key)))
        except Exception as exc:
            logger.error("redis_exists_error", key=key, error=str(exc))
            return False

    async def clear_pattern(self, pattern: str) -> int:
        """Delete all keys matching *pattern* (uses SCAN for safety).

        Args:
            pattern: Glob-style pattern **without** the key prefix.

        Returns:
            Number of keys deleted, ``0`` on error.
        """
        if self._client is None:
            return 0
        full_pattern = self._make_key(pattern)
        deleted = 0
        try:
            async for key in self._client.scan_iter(match=full_pattern, count=200):
                await self._client.delete(key)
                deleted += 1
        except Exception as exc:
            logger.error("redis_clear_pattern_error", pattern=full_pattern, error=str(exc))
        return deleted

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_key(self, key: str) -> str:
        """Prepend key prefix for namespace isolation."""
        return f"{self._key_prefix}:{key}"

    # ------------------------------------------------------------------
    # Info / stats
    # ------------------------------------------------------------------

    async def info(self) -> dict[str, Any]:
        """Return basic Redis server info.

        Returns:
            Dictionary with memory usage and key count, or empty dict on error.
        """
        if self._client is None:
            return {}
        try:
            raw = await self._client.info(section="memory")
            keyspace = await self._client.info(section="keyspace")
            return {
                "used_memory_human": raw.get("used_memory_human", "N/A"),
                "used_memory_peak_human": raw.get("used_memory_peak_human", "N/A"),
                "keyspace": keyspace,
                "connected": True,
            }
        except Exception as exc:
            logger.error("redis_info_error", error=str(exc))
            return {"connected": False}


# ------------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------------


def compute_cache_key(*args: Any, **kwargs: Any) -> str:
    """Generate a deterministic SHA-256 hash from arbitrary arguments.

    Args:
        *args: Positional values to include in the hash.
        **kwargs: Keyword values to include in the hash.

    Returns:
        Hex-encoded SHA-256 digest string.
    """
    payload = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


async def get_redis_client() -> RedisCacheClient:
    """Return the module-level singleton :class:`RedisCacheClient`.

    A new instance is created on first call using values from
    :pydata:`app.core.config.settings`.

    Returns:
        Shared ``RedisCacheClient`` instance.
    """
    global _redis_client  # noqa: PLW0603
    if _redis_client is None:
        _redis_client = RedisCacheClient(
            redis_url=settings.REDIS_CONNECTION_URL,
            key_prefix=settings.CACHE_KEY_PREFIX,
        )
    return _redis_client
