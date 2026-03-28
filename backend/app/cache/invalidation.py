"""Cache invalidation utilities for targeted and bulk cache clearing."""

from typing import Any

from app.cache.redis_cache import get_redis_client
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def invalidate_source_cache(source_id: str) -> int:
    """Clear all embeddings cached for a specific source.

    Args:
        source_id: Identifier of the source to invalidate.

    Returns:
        Number of keys deleted.
    """
    redis_client = await get_redis_client()
    pattern = f"embedding:*:{source_id}:*"
    deleted = await redis_client.clear_pattern(pattern)
    logger.info("cache_invalidated", scope="source", source_id=source_id, keys_deleted=deleted)
    return deleted


async def invalidate_scope_cache(scope_key: str) -> int:
    """Clear all cached data associated with a logical retrieval scope.

    Args:
        scope_key: Scope identifier to invalidate.

    Returns:
        Number of keys deleted.
    """
    redis_client = await get_redis_client()
    pattern = f"*:{scope_key}:*"
    deleted = await redis_client.clear_pattern(pattern)
    logger.info(
        "cache_invalidated",
        scope="retrieval_scope",
        scope_key=scope_key,
        keys_deleted=deleted,
    )
    return deleted


async def invalidate_all_embeddings() -> int:
    """Clear all embedding caches.

    Returns:
        Number of keys deleted.
    """
    redis_client = await get_redis_client()
    deleted = await redis_client.clear_pattern("embedding:*")
    logger.info("cache_invalidated", scope="all_embeddings", keys_deleted=deleted)
    return deleted


async def invalidate_all_llm() -> int:
    """Clear all LLM response caches.

    Returns:
        Number of keys deleted.
    """
    redis_client = await get_redis_client()
    deleted = await redis_client.clear_pattern("llm:*")
    logger.info("cache_invalidated", scope="all_llm", keys_deleted=deleted)
    return deleted


async def get_cache_stats() -> dict[str, Any]:
    """Return cache statistics including key counts and memory usage.

    Returns:
        Dictionary with cache statistics.
    """
    redis_client = await get_redis_client()
    info = await redis_client.info()

    # Count keys by type using SCAN
    embedding_keys = 0
    llm_keys = 0

    if info.get("connected"):
        # Count embedding keys
        prefix = settings.CACHE_KEY_PREFIX
        if redis_client._client is not None:
            try:
                async for _ in redis_client._client.scan_iter(
                    match=f"{prefix}:embedding:*", count=200
                ):
                    embedding_keys += 1
                async for _ in redis_client._client.scan_iter(
                    match=f"{prefix}:llm:*", count=200
                ):
                    llm_keys += 1
            except Exception as exc:
                logger.error("cache_stats_scan_error", error=str(exc))

    return {
        "connected": info.get("connected", False),
        "used_memory_human": info.get("used_memory_human", "N/A"),
        "used_memory_peak_human": info.get("used_memory_peak_human", "N/A"),
        "embedding_keys": embedding_keys,
        "llm_keys": llm_keys,
        "total_cached_keys": embedding_keys + llm_keys,
        "ttl_embeddings_seconds": settings.CACHE_TTL_EMBEDDINGS,
        "ttl_llm_seconds": settings.CACHE_TTL_LLM,
    }
