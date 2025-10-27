"""Tests for idempotency service."""

import json
import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from app.services.idempotency_service import (
    IdempotencyService,
    IdempotencyConflictError,
    IdempotencyFailureError,
)
from app.utils import IdempotencyRecord, IdempotencyStatus


class TestIdempotencyService:
    """Test cases for IdempotencyService."""

    @pytest.fixture
    def mock_storage(self):
        """Create mock Redis storage."""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_storage):
        """Create IdempotencyService with mock storage."""
        return IdempotencyService(mock_storage)

    def test_generate_key(self, service):
        """Test key generation."""
        key = service.generate_key()
        assert isinstance(key, str)
        assert len(key) == 36  # UUID format

    def test_get_or_generate_key_with_provided(self, service):
        """Test key retrieval when key is provided."""
        provided_key = "test-key-123"
        result = service.get_or_generate_key(provided_key)
        assert result == provided_key

    def test_get_or_generate_key_without_provided(self, service):
        """Test key generation when no key is provided."""
        result = service.get_or_generate_key(None)
        assert isinstance(result, str)
        assert len(result) == 36  # UUID format

    def test_extract_error_message_with_valid_json(self):
        """Test error message extraction from valid JSON."""
        response_data = '{"error": "Custom error message"}'
        result = IdempotencyService._extract_error_message(response_data)
        assert result == "Custom error message"

    def test_extract_error_message_with_invalid_json(self):
        """Test error message extraction from invalid JSON."""
        response_data = "invalid json"
        result = IdempotencyService._extract_error_message(response_data)
        assert result == "Operation failed"

    def test_extract_error_message_with_none(self):
        """Test error message extraction from None."""
        result = IdempotencyService._extract_error_message(None)
        assert result == "Operation failed"

    async def test_complete_failure(self, service, mock_storage):
        """Test completing operation with failure."""
        key = "test-key"
        error_message = "Payment failed"

        await service.complete_failure(key, error_message)

        mock_storage.complete_idempotent_operation.assert_called_once_with(
            key=key, success=False, error=error_message, ttl_seconds=None
        )

    async def test_execute_idempotent_operation_success_new(
        self, service, mock_storage
    ):
        """Test executing new operation successfully."""
        key = "test-key"
        expected_result = {"transaction_id": "123"}

        # Mock no existing record
        mock_storage.get_idempotency_record.return_value = None
        # Mock successful operation start
        mock_storage.start_idempotent_operation.return_value = True

        # Mock operation
        mock_result = Mock()
        mock_result.model_dump = Mock(return_value=expected_result)

        async def mock_operation():
            return mock_result

        result = await service.execute_idempotent_operation(key, mock_operation)

        # Verify operation was executed and completed successfully
        mock_storage.complete_idempotent_operation.assert_called_once_with(
            key=key, success=True, data=expected_result, ttl_seconds=None
        )

    async def test_execute_idempotent_operation_cached_success(
        self, service, mock_storage
    ):
        """Test returning cached successful result."""
        key = "test-key"
        cached_data = {"transaction_id": "cached-123"}

        # Mock existing successful record
        mock_record = IdempotencyRecord(
            idempotency_key=key,
            status=IdempotencyStatus.SUCCESS,
            response_data=json.dumps(cached_data),
        )
        mock_storage.get_idempotency_record.return_value = mock_record

        async def mock_operation():
            # This should not be called
            raise AssertionError("Operation should not be executed for cached result")

        result = await service.execute_idempotent_operation(key, mock_operation)

        assert result == cached_data
        # Verify storage methods were not called for new operation
        mock_storage.start_idempotent_operation.assert_not_called()
        mock_storage.complete_idempotent_operation.assert_not_called()

    async def test_execute_idempotent_operation_cached_failure(
        self, service, mock_storage
    ):
        """Test returning cached failure result."""
        key = "test-key"
        error_message = "Cached payment error"

        # Mock existing failure record
        mock_record = IdempotencyRecord(
            idempotency_key=key,
            status=IdempotencyStatus.FAILURE,
            response_data=json.dumps({"error": error_message}),
        )
        mock_storage.get_idempotency_record.return_value = mock_record

        async def mock_operation():
            # This should not be called
            raise AssertionError("Operation should not be executed for cached failure")

        with pytest.raises(IdempotencyFailureError, match=error_message):
            await service.execute_idempotent_operation(key, mock_operation)

    async def test_execute_idempotent_operation_in_progress(
        self, service, mock_storage
    ):
        """Test handling operation already in progress."""
        key = "test-key"

        # Mock existing in-progress record
        mock_record = IdempotencyRecord(
            idempotency_key=key, status=IdempotencyStatus.IN_PROCESS
        )
        mock_storage.get_idempotency_record.return_value = mock_record

        async def mock_operation():
            return {"result": "test"}

        with pytest.raises(IdempotencyConflictError):
            await service.execute_idempotent_operation(key, mock_operation)

    async def test_execute_idempotent_operation_start_conflict(
        self, service, mock_storage
    ):
        """Test handling race condition when starting operation."""
        key = "test-key"

        # Mock no existing record initially
        mock_storage.get_idempotency_record.return_value = None
        # Mock failed operation start (race condition)
        mock_storage.start_idempotent_operation.return_value = False

        async def mock_operation():
            return {"result": "test"}

        with pytest.raises(IdempotencyConflictError):
            await service.execute_idempotent_operation(key, mock_operation)

    async def test_execute_idempotent_operation_handles_exceptions(
        self, service, mock_storage
    ):
        """Test proper exception handling during operation execution."""
        key = "test-key"
        error_message = "Test operation error"

        # Mock no existing record
        mock_storage.get_idempotency_record.return_value = None
        # Mock successful operation start
        mock_storage.start_idempotent_operation.return_value = True

        # Mock operation that raises exception
        async def failing_operation():
            raise ValueError(error_message)

        with pytest.raises(ValueError, match=error_message):
            await service.execute_idempotent_operation(key, failing_operation)

        # Verify failure was recorded
        mock_storage.complete_idempotent_operation.assert_called_once_with(
            key=key, success=False, error=error_message, ttl_seconds=None
        )
