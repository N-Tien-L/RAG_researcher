"""Tests for cache invalidation utilities."""

from unittest.mock import AsyncMock, patch

import pytest

from app.cache import invalidation


@pytest.mark.asyncio
class TestInvalidateSourceCache:
    """Test source cache invalidation."""

    async def test_invalidate_source_cache_success(self):
        """Test successful source cache invalidation."""
        mock_client = AsyncMock()
        mock_client.clear_pattern = AsyncMock(return_value=5)
        
        with patch("app.cache.invalidation.get_redis_client", return_value=mock_client):
            deleted = await invalidation.invalidate_source_cache("source_123")
            
            assert deleted == 5
            mock_client.clear_pattern.assert_called_once_with("embedding:*:source_123:*")

    async def test_invalidate_source_cache_no_keys(self):
        """Test source cache invalidation when no keys match."""
        mock_client = AsyncMock()
        mock_client.clear_pattern = AsyncMock(return_value=0)
        
        with patch("app.cache.invalidation.get_redis_client", return_value=mock_client):
            deleted = await invalidation.invalidate_source_cache("source_999")
            
            assert deleted == 0


@pytest.mark.asyncio
class TestInvalidateScopeCache:
    """Test scope cache invalidation."""

    async def test_invalidate_scope_cache_success(self):
        """Test successful scope cache invalidation."""
        mock_client = AsyncMock()
        mock_client.clear_pattern = AsyncMock(return_value=12)
        
        with patch("app.cache.invalidation.get_redis_client", return_value=mock_client):
            deleted = await invalidation.invalidate_scope_cache("my_scope")
            
            assert deleted == 12
            mock_client.clear_pattern.assert_called_once_with("*:my_scope:*")

    async def test_invalidate_scope_cache_empty(self):
        """Test scope cache invalidation with no matches."""
        mock_client = AsyncMock()
        mock_client.clear_pattern = AsyncMock(return_value=0)
        
        with patch("app.cache.invalidation.get_redis_client", return_value=mock_client):
            deleted = await invalidation.invalidate_scope_cache("empty_scope")
            
            assert deleted == 0


@pytest.mark.asyncio
class TestInvalidateAllEmbeddings:
    """Test all embeddings cache invalidation."""

    async def test_invalidate_all_embeddings_success(self):
        """Test clearing all embedding caches."""
        mock_client = AsyncMock()
        mock_client.clear_pattern = AsyncMock(return_value=50)
        
        with patch("app.cache.invalidation.get_redis_client", return_value=mock_client):
            deleted = await invalidation.invalidate_all_embeddings()
            
            assert deleted == 50
            mock_client.clear_pattern.assert_called_once_with("embedding:*")


@pytest.mark.asyncio
class TestInvalidateAllLLM:
    """Test all LLM cache invalidation."""

    async def test_invalidate_all_llm_success(self):
        """Test clearing all LLM response caches."""
        mock_client = AsyncMock()
        mock_client.clear_pattern = AsyncMock(return_value=30)
        
        with patch("app.cache.invalidation.get_redis_client", return_value=mock_client):
            deleted = await invalidation.invalidate_all_llm()
            
            assert deleted == 30
            mock_client.clear_pattern.assert_called_once_with("llm:*")


@pytest.mark.asyncio
class TestGetCacheStats:
    """Test cache statistics retrieval."""

    async def test_get_cache_stats_success(self):
        """Test successful cache stats retrieval."""
        mock_client = AsyncMock()
        mock_client.info = AsyncMock(return_value={
            "connected": True,
            "used_memory_human": "2.5M",
            "used_memory_peak_human": "3.0M",
        })
        mock_client._client = AsyncMock()
        
        # Mock scan_iter for embedding and LLM keys
        async def mock_scan_embedding(match, count):
            for i in range(10):
                yield f"test:embedding:key{i}"
        
        async def mock_scan_llm(match, count):
            for i in range(5):
                yield f"test:llm:key{i}"
        
        # Configure scan_iter to return different results based on match parameter
        def scan_iter_side_effect(match, count):
            if "embedding" in match:
                return mock_scan_embedding(match, count)
            else:
                return mock_scan_llm(match, count)
        
        mock_client._client.scan_iter = scan_iter_side_effect
        
        with patch("app.cache.invalidation.get_redis_client", return_value=mock_client):
            with patch("app.cache.invalidation.settings") as mock_settings:
                mock_settings.CACHE_KEY_PREFIX = "test"
                mock_settings.CACHE_TTL_EMBEDDINGS = 3600
                mock_settings.CACHE_TTL_LLM = 1800
                
                stats = await invalidation.get_cache_stats()
                
                assert stats["connected"] is True
                assert stats["used_memory_human"] == "2.5M"
                assert stats["used_memory_peak_human"] == "3.0M"
                assert stats["embedding_keys"] == 10
                assert stats["llm_keys"] == 5
                assert stats["total_cached_keys"] == 15
                assert stats["ttl_embeddings_seconds"] == 3600
                assert stats["ttl_llm_seconds"] == 1800

    async def test_get_cache_stats_not_connected(self):
        """Test cache stats when Redis is not connected."""
        mock_client = AsyncMock()
        mock_client.info = AsyncMock(return_value={
            "connected": False,
        })
        
        with patch("app.cache.invalidation.get_redis_client", return_value=mock_client):
            with patch("app.cache.invalidation.settings") as mock_settings:
                mock_settings.CACHE_TTL_EMBEDDINGS = 3600
                mock_settings.CACHE_TTL_LLM = 1800
                
                stats = await invalidation.get_cache_stats()
                
                assert stats["connected"] is False
                assert stats["used_memory_human"] == "N/A"
                assert stats["embedding_keys"] == 0
                assert stats["llm_keys"] == 0

    async def test_get_cache_stats_scan_error(self):
        """Test cache stats when scan_iter raises error."""
        mock_client = AsyncMock()
        mock_client.info = AsyncMock(return_value={
            "connected": True,
            "used_memory_human": "1.0M",
            "used_memory_peak_human": "1.5M",
        })
        mock_client._client = AsyncMock()
        
        async def mock_scan_error(match, count):
            raise Exception("Scan error")
            yield  # Make it a generator
        
        mock_client._client.scan_iter = mock_scan_error
        
        with patch("app.cache.invalidation.get_redis_client", return_value=mock_client):
            with patch("app.cache.invalidation.settings") as mock_settings:
                mock_settings.CACHE_KEY_PREFIX = "test"
                mock_settings.CACHE_TTL_EMBEDDINGS = 3600
                mock_settings.CACHE_TTL_LLM = 1800
                
                stats = await invalidation.get_cache_stats()
                
                # Should still return stats with zero counts
                assert stats["connected"] is True
                assert stats["embedding_keys"] == 0
                assert stats["llm_keys"] == 0
