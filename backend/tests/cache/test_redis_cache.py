"""Tests for Redis cache client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.cache.redis_cache import RedisCacheClient, compute_cache_key, get_redis_client


@pytest.mark.asyncio
class TestRedisCacheClient:
    """Test suite for RedisCacheClient."""

    async def test_connect_success(self):
        """Test successful Redis connection."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock()
            mock_from_url.return_value = mock_redis
            
            await client.connect()
            
            assert client._client is not None
            mock_from_url.assert_called_once_with(
                "redis://localhost:6379",
                decode_responses=True,
                socket_connect_timeout=5,
            )
            mock_redis.ping.assert_called_once()

    async def test_connect_failure(self):
        """Test Redis connection failure."""
        client = RedisCacheClient("redis://invalid:6379", "test")
        
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_from_url.side_effect = Exception("Connection failed")
            
            await client.connect()
            
            assert client._client is None

    async def test_disconnect_success(self):
        """Test successful disconnection."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        mock_client = AsyncMock()
        mock_client.aclose = AsyncMock()
        client._client = mock_client
        
        await client.disconnect()
        
        mock_client.aclose.assert_called_once()
        assert client._client is None

    async def test_disconnect_with_error(self):
        """Test disconnection with error."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        client._client = AsyncMock()
        client._client.aclose = AsyncMock(side_effect=Exception("Close error"))
        
        await client.disconnect()
        
        assert client._client is None

    async def test_get_success(self):
        """Test successful get operation."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value="cached_value")
        
        result = await client.get("my_key")
        
        assert result == "cached_value"
        client._client.get.assert_called_once_with("test:my_key")

    async def test_get_when_not_connected(self):
        """Test get when Redis is not connected."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        client._client = None
        
        result = await client.get("my_key")
        
        assert result is None

    async def test_get_with_error(self):
        """Test get with Redis error."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        client._client = AsyncMock()
        client._client.get = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await client.get("my_key")
        
        assert result is None

    async def test_set_success(self):
        """Test successful set operation."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        client._client = AsyncMock()
        client._client.set = AsyncMock()
        
        await client.set("my_key", "my_value", ttl=60)
        
        client._client.set.assert_called_once_with("test:my_key", "my_value", ex=60)

    async def test_set_when_not_connected(self):
        """Test set when Redis is not connected."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        client._client = None
        
        # Should not raise exception
        await client.set("my_key", "my_value", ttl=60)

    async def test_set_with_error(self):
        """Test set with Redis error."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        client._client = AsyncMock()
        client._client.set = AsyncMock(side_effect=Exception("Redis error"))
        
        # Should not raise exception
        await client.set("my_key", "my_value", ttl=60)

    async def test_delete_success(self):
        """Test successful delete operation."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        client._client = AsyncMock()
        client._client.delete = AsyncMock()
        
        await client.delete("my_key")
        
        client._client.delete.assert_called_once_with("test:my_key")

    async def test_delete_when_not_connected(self):
        """Test delete when Redis is not connected."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        client._client = None
        
        # Should not raise exception
        await client.delete("my_key")

    async def test_exists_returns_true(self):
        """Test exists returns True when key exists."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        client._client = AsyncMock()
        client._client.exists = AsyncMock(return_value=1)
        
        result = await client.exists("my_key")
        
        assert result is True
        client._client.exists.assert_called_once_with("test:my_key")

    async def test_exists_returns_false(self):
        """Test exists returns False when key does not exist."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        client._client = AsyncMock()
        client._client.exists = AsyncMock(return_value=0)
        
        result = await client.exists("my_key")
        
        assert result is False

    async def test_exists_when_not_connected(self):
        """Test exists when Redis is not connected."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        client._client = None
        
        result = await client.exists("my_key")
        
        assert result is False

    async def test_exists_with_error(self):
        """Test exists with Redis error."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        client._client = AsyncMock()
        client._client.exists = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await client.exists("my_key")
        
        assert result is False

    async def test_clear_pattern_success(self):
        """Test clearing keys matching a pattern."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        client._client = AsyncMock()
        
        # Mock scan_iter to return some keys
        async def mock_scan_iter(match, count):
            for key in ["test:pattern:key1", "test:pattern:key2", "test:pattern:key3"]:
                yield key
        
        client._client.scan_iter = mock_scan_iter
        client._client.delete = AsyncMock()
        
        deleted = await client.clear_pattern("pattern:*")
        
        assert deleted == 3
        assert client._client.delete.call_count == 3

    async def test_clear_pattern_when_not_connected(self):
        """Test clear_pattern when Redis is not connected."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        client._client = None
        
        deleted = await client.clear_pattern("pattern:*")
        
        assert deleted == 0

    async def test_clear_pattern_with_error(self):
        """Test clear_pattern with Redis error."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        client._client = AsyncMock()
        
        async def mock_scan_iter_error(match, count):
            raise Exception("Scan error")
            yield  # Make it a generator
        
        client._client.scan_iter = mock_scan_iter_error
        
        deleted = await client.clear_pattern("pattern:*")
        
        assert deleted == 0

    async def test_info_success(self):
        """Test getting Redis info."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        client._client = AsyncMock()
        client._client.info = AsyncMock(side_effect=[
            {"used_memory_human": "1.5M", "used_memory_peak_human": "2.0M"},
            {"db0": "keys=100"}
        ])
        
        info = await client.info()
        
        assert info["used_memory_human"] == "1.5M"
        assert info["used_memory_peak_human"] == "2.0M"
        assert info["keyspace"] == {"db0": "keys=100"}
        assert info["connected"] is True

    async def test_info_when_not_connected(self):
        """Test info when Redis is not connected."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        client._client = None
        
        info = await client.info()
        
        assert info == {}

    async def test_info_with_error(self):
        """Test info with Redis error."""
        client = RedisCacheClient("redis://localhost:6379", "test")
        client._client = AsyncMock()
        client._client.info = AsyncMock(side_effect=Exception("Info error"))
        
        info = await client.info()
        
        assert info == {"connected": False}

    async def test_make_key(self):
        """Test key prefix prepending."""
        client = RedisCacheClient("redis://localhost:6379", "my_prefix")
        
        key = client._make_key("test_key")
        
        assert key == "my_prefix:test_key"


class TestComputeCacheKey:
    """Test cache key generation."""

    def test_compute_cache_key_args_only(self):
        """Test cache key generation with args only."""
        key1 = compute_cache_key("arg1", "arg2", 123)
        key2 = compute_cache_key("arg1", "arg2", 123)
        key3 = compute_cache_key("arg1", "arg2", 456)
        
        assert key1 == key2  # Same inputs produce same key
        assert key1 != key3  # Different inputs produce different keys
        assert len(key1) == 64  # SHA-256 produces 64-char hex string

    def test_compute_cache_key_kwargs_only(self):
        """Test cache key generation with kwargs only."""
        key1 = compute_cache_key(user="alice", action="login")
        key2 = compute_cache_key(user="alice", action="login")
        key3 = compute_cache_key(user="bob", action="login")
        
        assert key1 == key2
        assert key1 != key3

    def test_compute_cache_key_mixed(self):
        """Test cache key generation with mixed args and kwargs."""
        key1 = compute_cache_key("arg1", 123, user="alice", active=True)
        key2 = compute_cache_key("arg1", 123, user="alice", active=True)
        
        assert key1 == key2

    def test_compute_cache_key_order_independence(self):
        """Test that kwarg order doesn't affect the key."""
        key1 = compute_cache_key(a=1, b=2, c=3)
        key2 = compute_cache_key(c=3, a=1, b=2)
        
        assert key1 == key2

    def test_compute_cache_key_with_complex_types(self):
        """Test cache key with complex types."""
        key = compute_cache_key(
            {"name": "Alice", "age": 30},
            ["item1", "item2"],
            status=True,
        )
        
        assert isinstance(key, str)
        assert len(key) == 64


@pytest.mark.asyncio
class TestGetRedisClient:
    """Test singleton client retrieval."""

    async def test_get_redis_client_singleton(self):
        """Test that get_redis_client returns the same instance."""
        with patch("app.cache.redis_cache.settings") as mock_settings:
            mock_settings.REDIS_CONNECTION_URL = "redis://localhost:6379"
            mock_settings.CACHE_KEY_PREFIX = "test_app"
            
            # Clear the module-level singleton
            import app.cache.redis_cache
            app.cache.redis_cache._redis_client = None
            
            client1 = await get_redis_client()
            client2 = await get_redis_client()
            
            assert client1 is client2
            assert client1._redis_url == "redis://localhost:6379"
            assert client1._key_prefix == "test_app"
