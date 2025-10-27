"""
Idempotency service for handling duplicate request prevention.
"""

import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar
from uuid import uuid4

from app.utils import (
    IdempotencyRecord,
    IdempotencyStatus,
    RedisIdempotencyStorage,
    get_idempotency_storage,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class IdempotencyService:
    """Service for managing idempotent operations with Redis storage."""

    def __init__(self, storage: RedisIdempotencyStorage):
        """Initialize idempotency service.

        Args:
            storage: Redis storage instance for idempotency records
        """
        self.storage = storage

    @staticmethod
    def generate_key() -> str:
        """Generate a new idempotency key.

        Returns:
            str: UUID-based idempotency key
        """
        return str(uuid4())

    def get_or_generate_key(self, provided_key: Optional[str] = None) -> str:
        """Get provided key or generate new one.

        Args:
            provided_key: Optional key from request header

        Returns:
            str: Idempotency key to use
        """
        return provided_key or self.generate_key()

    async def complete_failure(
        self, key: str, error_message: str, ttl_seconds: Optional[int] = None
    ) -> None:
        """Mark operation as failed.

        Args:
            key: Idempotency key
            error_message: Error message to cache
            ttl_seconds: TTL for the cached error
        """
        await self.storage.complete_idempotent_operation(
            key=key, success=False, error=error_message, ttl_seconds=ttl_seconds
        )

    async def execute_idempotent_operation(
        self,
        key: str,
        operation: Callable[[], Awaitable[T]],
        ttl_seconds: Optional[int] = None,
    ) -> T:
        """Execute an operation with full idempotency support.

        This is a high-level method that handles the entire idempotency workflow:
        1. Check for existing operation and return cached result if completed
        2. Start new operation if not exists
        3. Execute the operation and cache the result

        Args:
            key: Idempotency key
            operation: Async function to execute
            ttl_seconds: TTL for cached results (defaults to storage default)

        Returns:
            T: Result of the operation (either fresh or from cache)

        Raises:
            IdempotencyConflictError: If operation is already in progress
            IdempotencyFailureError: If operation previously failed
            Exception: Any exception from the underlying operation
        """
        # Check for existing operation
        existing_record = await self.storage.get_idempotency_record(key)

        if existing_record:
            return await self._handle_existing_record(existing_record, key)

        # Start new operation
        operation_started = await self.storage.start_idempotent_operation(
            key, ttl_seconds
        )
        if not operation_started:
            raise IdempotencyConflictError(
                "Operation is currently being processed by another instance"
            )

        return await self._execute_and_cache(key, operation, ttl_seconds)

    async def _handle_existing_record(self, record: IdempotencyRecord, key: str) -> T:
        """Handle existing idempotency record."""
        if record.status == IdempotencyStatus.SUCCESS:
            logger.info(f"Returning cached successful response for key: {key}")
            if record.response_data:
                # Parse JSON back to the original structure
                data = json.loads(record.response_data)
                # If the data has the structure of a Pydantic model, try to reconstruct it
                if isinstance(data, dict) and all(
                    field in data
                    for field in ["uid", "amount", "type", "user_id", "created_at"]
                ):
                    # This looks like a TransactionResponse
                    from app.schemas import TransactionResponse

                    return TransactionResponse.model_validate(data)
                else:
                    # Return the raw data for other types
                    return data
            return None

        elif record.status == IdempotencyStatus.FAILURE:
            logger.info(f"Operation previously failed for key: {key}")
            error_message = self._extract_error_message(record.response_data)
            raise IdempotencyFailureError(error_message)

        else:  # IN_PROCESS
            logger.warning(f"Operation already in progress for key: {key}")
            raise IdempotencyConflictError("Operation is currently being processed")

    async def _execute_and_cache(
        self,
        key: str,
        operation: Callable[[], Awaitable[T]],
        ttl_seconds: Optional[int],
    ) -> T:
        """Execute operation and cache the result."""
        try:
            result = await operation()

            # Serialize response for caching with proper enum handling
            if hasattr(result, "model_dump"):
                # Use mode='json' to ensure enums are serialized as their values, not string representations
                response_data = result.model_dump(mode="json")
            else:
                response_data = result

            # Cache successful result
            await self.storage.complete_idempotent_operation(
                key=key, success=True, data=response_data, ttl_seconds=ttl_seconds
            )

            return result

        except Exception as e:
            # Cache failure
            await self.storage.complete_idempotent_operation(
                key=key, success=False, error=str(e), ttl_seconds=ttl_seconds
            )
            raise

    @staticmethod
    def _extract_error_message(response_data: Optional[str]) -> str:
        """Extract error message from cached response data."""
        if not response_data:
            return "Operation failed"

        try:
            error_data = json.loads(response_data)
            return error_data.get("error", "Operation failed")
        except json.JSONDecodeError:
            return "Operation failed"


class IdempotencyConflictError(Exception):
    """Raised when an idempotent operation is already in progress."""

    pass


class IdempotencyFailureError(Exception):
    """Raised when returning a cached failure result."""

    pass
