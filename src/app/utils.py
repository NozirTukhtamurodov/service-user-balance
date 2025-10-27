"""
Utility classes and functions for the application.
"""

import json
import logging
from enum import Enum
from typing import Optional, Any, Dict
from uuid import uuid4
from datetime import datetime, timezone

import redis.asyncio as redis
from pydantic import BaseModel, Field, ConfigDict

logger = logging.getLogger(__name__)


class IdempotencyStatus(Enum):
    """Status of idempotency request processing."""

    IN_PROCESS = "in_process"
    SUCCESS = "success"
    FAILURE = "failure"


class IdempotencyRecord(BaseModel):
    """Pydantic model for idempotency record."""

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    idempotency_key: str = Field(..., description="Unique idempotency key")
    status: IdempotencyStatus = Field(
        default=IdempotencyStatus.IN_PROCESS, description="Status of the operation"
    )
    response_data: Optional[str] = Field(
        default=None, description="Cached response data (JSON string)"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Record creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Record last update timestamp",
    )
    ttl: int = Field(default=3600, description="Time to live in seconds")


class RedisIdempotencyStorage:
    """Redis-based storage for idempotency keys with TTL support."""

    def __init__(
        self, redis_url: str = "redis://localhost:6379", default_ttl_seconds: int = 3600
    ):
        """Initialize Redis storage.

        Args:
            redis_url: Redis connection URL
            default_ttl_seconds: Default TTL for stored items in seconds
        """
        self.redis_url = redis_url
        self.default_ttl_seconds = default_ttl_seconds
        self._redis: Optional[redis.Redis] = None

    async def _get_redis(self) -> redis.Redis:
        """Get or create Redis connection.

        Returns:
            redis.Redis: Redis connection instance
        """
        if self._redis is None:
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def set(
        self, key: str, value: Any, ttl_seconds: Optional[int] = None
    ) -> None:
        """Store a value with TTL.

        Args:
            key: Storage key
            value: Value to store (will be JSON serialized)
            ttl_seconds: TTL in seconds, uses default if None
        """
        ttl = ttl_seconds or self.default_ttl_seconds
        redis_client = await self._get_redis()

        # Serialize value to JSON
        serialized_value = json.dumps(value, default=str)

        await redis_client.setex(
            name=f"idempotency:{key}", time=ttl, value=serialized_value
        )

    async def get(self, key: str) -> Optional[Any]:
        """Get a value by key.

        Args:
            key: Storage key

        Returns:
            Stored value if exists, None otherwise
        """
        redis_client = await self._get_redis()

        serialized_value = await redis_client.get(f"idempotency:{key}")
        if serialized_value is None:
            return None

        try:
            return json.loads(serialized_value)
        except json.JSONDecodeError:
            logger.warning(f"Failed to deserialize value for key {key}")
            return None

    async def delete(self, key: str) -> bool:
        """Delete a key from storage.

        Args:
            key: Storage key

        Returns:
            True if key was deleted, False if key didn't exist
        """
        redis_client = await self._get_redis()
        deleted_count = await redis_client.delete(f"idempotency:{key}")
        return deleted_count > 0

    async def exists(self, key: str) -> bool:
        """Check if key exists.

        Args:
            key: Storage key

        Returns:
            True if key exists, False otherwise
        """
        redis_client = await self._get_redis()
        return await redis_client.exists(f"idempotency:{key}") > 0

    async def close(self) -> None:
        """Close Redis connection. Call during application shutdown."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def start_idempotent_operation(
        self, key: str, ttl_seconds: Optional[int] = None
    ) -> bool:
        """Start an idempotent operation by setting IN_PROCESS status.

        Args:
            key: Idempotency key
            ttl_seconds: TTL in seconds, uses default if None

        Returns:
            bool: True if operation started (key didn't exist),
                  False if already exists (duplicate request)
        """
        ttl = ttl_seconds or self.default_ttl_seconds
        redis_client = await self._get_redis()

        # Create initial record with IN_PROCESS status
        record = IdempotencyRecord(
            idempotency_key=key, status=IdempotencyStatus.IN_PROCESS
        )
        serialized_record = record.model_dump_json()

        # Use Redis SET with NX (only if not exists) to prevent race conditions
        result = await redis_client.set(
            f"idempotency:{key}",
            serialized_record,
            ex=ttl,
            nx=True,  # Only set if key doesn't exist
        )

        return (
            result is not None
        )  # Returns True if key was set, False if already exists

    async def get_idempotency_record(self, key: str) -> Optional[IdempotencyRecord]:
        """Get idempotency record with full status information.

        Args:
            key: Idempotency key

        Returns:
            IdempotencyRecord: Record if exists, None otherwise
        """
        redis_client = await self._get_redis()

        serialized_record = await redis_client.get(f"idempotency:{key}")
        if serialized_record is None:
            return None

        try:
            return IdempotencyRecord.model_validate_json(serialized_record)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(
                f"Failed to deserialize idempotency record for key {key}: {e}"
            )
            return None

    async def complete_idempotent_operation(
        self,
        key: str,
        success: bool,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """Complete an idempotent operation with success or failure status.

        Args:
            key: Idempotency key
            success: True for success, False for failure
            data: Response data for successful operations
            error: Error message for failed operations
            ttl_seconds: TTL in seconds, uses default if None

        Returns:
            bool: True if operation was completed, False if key didn't exist
        """
        ttl = ttl_seconds or self.default_ttl_seconds
        redis_client = await self._get_redis()

        # Get existing record to preserve created_at
        serialized_existing = await redis_client.get(f"idempotency:{key}")
        if serialized_existing is None:
            logger.warning(
                f"Attempted to complete non-existent idempotency operation: {key}"
            )
            return False

        try:
            existing_record = IdempotencyRecord.model_validate_json(serialized_existing)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to deserialize existing record for key {key}: {e}")
            return False

        # Update record with completion status
        status = IdempotencyStatus.SUCCESS if success else IdempotencyStatus.FAILURE

        # Prepare response data with Decimal handling
        if success:
            response_data = json.dumps(data, default=str) if data else None
        else:
            response_data = json.dumps({"error": error}, default=str) if error else None

        completed_record = IdempotencyRecord(
            idempotency_key=key,
            status=status,
            response_data=response_data,
            created_at=existing_record.created_at,
        )

        serialized_record = completed_record.model_dump_json()

        # Update the record
        await redis_client.setex(f"idempotency:{key}", ttl, serialized_record)

        return True


# Global storage instance
_idempotency_storage: Optional[RedisIdempotencyStorage] = None


def get_idempotency_storage(
    redis_url: str = "redis://localhost:6379",
) -> RedisIdempotencyStorage:
    """Get the global idempotency storage instance.

    Args:
        redis_url: Redis connection URL

    Returns:
        RedisIdempotencyStorage: Redis storage instance
    """
    global _idempotency_storage

    if _idempotency_storage is None:
        _idempotency_storage = RedisIdempotencyStorage(redis_url)
        logger.info("Using Redis for idempotency storage")

    return _idempotency_storage


def reset_idempotency_storage() -> None:
    """Reset the global idempotency storage instance.

    This is useful for testing to ensure clean state between tests.
    """
    global _idempotency_storage
    _idempotency_storage = None


def set_test_idempotency_storage(storage: RedisIdempotencyStorage) -> None:
    """Set a test idempotency storage instance.

    This allows tests to override the global storage with a test instance.

    Args:
        storage: Test storage instance
    """
    global _idempotency_storage
    _idempotency_storage = storage
