"""Tests for utility functions and classes."""

import pytest
from unittest.mock import AsyncMock, patch

from app.utils import (
    RedisIdempotencyStorage,
    get_idempotency_storage,
)


class TestRedisIdempotencyStorage:
    """Test cases for RedisIdempotencyStorage."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis.get = AsyncMock()
        mock_redis.delete = AsyncMock()
        mock_redis.exists = AsyncMock()
        mock_redis.close = AsyncMock()
        return mock_redis

    @pytest.fixture
    def storage(self, mock_redis):
        """Create Redis storage with mocked Redis client."""
        storage = RedisIdempotencyStorage()
        storage._redis = mock_redis
        return storage

    async def test_set_value(self, storage, mock_redis):
        """Test setting values in Redis."""
        test_key = "test_key"
        test_value = {"message": "test_response"}

        await storage.set(test_key, test_value, ttl_seconds=300)

        mock_redis.setex.assert_called_once_with(
            name="idempotency:test_key", time=300, value='{"message": "test_response"}'
        )

    async def test_get_value(self, storage, mock_redis):
        """Test getting values from Redis."""
        test_key = "test_key"
        mock_redis.get.return_value = '{"message": "test_response"}'

        result = await storage.get(test_key)

        mock_redis.get.assert_called_once_with("idempotency:test_key")
        assert result == {"message": "test_response"}

    async def test_get_nonexistent_value(self, storage, mock_redis):
        """Test getting non-existent values from Redis."""
        mock_redis.get.return_value = None

        result = await storage.get("nonexistent")

        assert result is None

    async def test_delete_value(self, storage, mock_redis):
        """Test deleting values from Redis."""
        test_key = "test_key"
        mock_redis.delete.return_value = 1

        result = await storage.delete(test_key)

        mock_redis.delete.assert_called_once_with("idempotency:test_key")
        assert result is True

    async def test_delete_nonexistent_value(self, storage, mock_redis):
        """Test deleting non-existent values from Redis."""
        mock_redis.delete.return_value = 0

        result = await storage.delete("nonexistent")

        assert result is False

    async def test_exists_true(self, storage, mock_redis):
        """Test checking existence of existing key."""
        mock_redis.exists.return_value = 1

        result = await storage.exists("test_key")

        mock_redis.exists.assert_called_once_with("idempotency:test_key")
        assert result is True

    async def test_exists_false(self, storage, mock_redis):
        """Test checking existence of non-existent key."""
        mock_redis.exists.return_value = 0

        result = await storage.exists("nonexistent")

        assert result is False

    async def test_close(self, storage, mock_redis):
        """Test closing Redis connection."""
        await storage.close()

        mock_redis.aclose.assert_called_once()


class TestGetIdempotencyStorage:
    """Test cases for get_idempotency_storage function."""

    def test_returns_redis_storage(self):
        """Test that Redis storage is returned."""
        storage = get_idempotency_storage("redis://localhost:6379")
        assert isinstance(storage, RedisIdempotencyStorage)

    @patch("app.utils._idempotency_storage", None)
    def test_singleton_behavior(self):
        """Test that the same instance is returned on multiple calls."""
        storage1 = get_idempotency_storage()
        storage2 = get_idempotency_storage()
        assert storage1 is storage2
