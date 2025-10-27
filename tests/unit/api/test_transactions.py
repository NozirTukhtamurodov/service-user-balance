"""
Unit tests for transaction API endpoints with IdempotencyService.
"""

import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app import schemas
from app.api.transactions import create_transaction, get_transaction
from app.exceptions import PaymentError
from app.services.idempotency_service import (
    IdempotencyConflictError,
    IdempotencyFailureError,
    IdempotencyService,
)
from app.services.transaction_service import TransactionService
from app.types import TransactionType
from app.utils import IdempotencyRecord, IdempotencyStatus


class TestTransactionAPI:
    """Test cases for transaction API endpoints."""

    @pytest.fixture
    def sample_transaction_create(self):
        """Sample transaction creation data."""
        return schemas.TransactionCreate(
            user_id="1", amount=Decimal("100.50"), type=TransactionType.DEPOSIT
        )

    @pytest.fixture
    def sample_transaction_response(self):
        """Sample transaction response."""
        return schemas.TransactionResponse(
            uid="test-uuid-123",
            user_id="1",
            amount=Decimal("100.50"),
            type=TransactionType.DEPOSIT,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def mock_transaction_service(self):
        """Mock transaction service."""
        return AsyncMock(spec=TransactionService)

    @pytest.fixture
    def mock_idempotency_service(self):
        """Mock idempotency service."""
        return AsyncMock(spec=IdempotencyService)

    async def test_create_transaction_success_new_operation(
        self,
        sample_transaction_create,
        sample_transaction_response,
        mock_transaction_service,
        mock_idempotency_service,
    ):
        """Test successful transaction creation with new idempotency operation."""
        # Setup mocks
        idempotency_key = "test-key-123"
        mock_idempotency_service.get_or_generate_key.return_value = idempotency_key
        mock_idempotency_service.execute_idempotent_operation.return_value = (
            sample_transaction_response
        )

        # Execute
        result = await create_transaction(
            data=sample_transaction_create,
            idempotency_key=idempotency_key,
            transaction_service=mock_transaction_service,
            idempotency_service=mock_idempotency_service,
        )

        # Verify
        assert result == sample_transaction_response
        mock_idempotency_service.get_or_generate_key.assert_called_once_with(
            idempotency_key
        )
        mock_idempotency_service.execute_idempotent_operation.assert_called_once()

        # Check that the operation was called with correct parameters
        call_args = mock_idempotency_service.execute_idempotent_operation.call_args
        assert call_args.kwargs["key"] == idempotency_key
        assert call_args.kwargs["ttl_seconds"] == 3600
        assert callable(
            call_args.kwargs["operation"]
        )  # Should be the operation function

    async def test_create_transaction_cached_success(
        self,
        sample_transaction_create,
        sample_transaction_response,
        mock_transaction_service,
        mock_idempotency_service,
    ):
        """Test returning cached successful transaction result."""
        # Setup mocks for cached response
        idempotency_key = "test-key-123"
        mock_idempotency_service.get_or_generate_key.return_value = idempotency_key
        mock_idempotency_service.execute_idempotent_operation.return_value = (
            sample_transaction_response
        )

        # Execute
        result = await create_transaction(
            data=sample_transaction_create,
            idempotency_key=idempotency_key,
            transaction_service=mock_transaction_service,
            idempotency_service=mock_idempotency_service,
        )

        # Verify
        assert result == sample_transaction_response
        mock_idempotency_service.execute_idempotent_operation.assert_called_once()

    async def test_create_transaction_idempotency_conflict(
        self,
        sample_transaction_create,
        mock_transaction_service,
        mock_idempotency_service,
    ):
        """Test handling idempotency conflict (operation in progress)."""
        # Setup mocks
        idempotency_key = "test-key-123"
        mock_idempotency_service.get_or_generate_key.return_value = idempotency_key
        mock_idempotency_service.execute_idempotent_operation.side_effect = (
            IdempotencyConflictError("Operation in progress")
        )

        # Execute & Verify
        with pytest.raises(HTTPException) as exc_info:
            await create_transaction(
                data=sample_transaction_create,
                idempotency_key=idempotency_key,
                transaction_service=mock_transaction_service,
                idempotency_service=mock_idempotency_service,
            )

        assert exc_info.value.status_code == 409
        assert "Request is currently being processed" in str(exc_info.value.detail)

    async def test_create_transaction_idempotency_failure(
        self,
        sample_transaction_create,
        mock_transaction_service,
        mock_idempotency_service,
    ):
        """Test handling cached failure result."""
        # Setup mocks
        idempotency_key = "test-key-123"
        mock_idempotency_service.get_or_generate_key.return_value = idempotency_key
        mock_idempotency_service.execute_idempotent_operation.side_effect = (
            IdempotencyFailureError("Insufficient funds")
        )

        # Execute & Verify
        with pytest.raises(HTTPException) as exc_info:
            await create_transaction(
                data=sample_transaction_create,
                idempotency_key=idempotency_key,
                transaction_service=mock_transaction_service,
                idempotency_service=mock_idempotency_service,
            )

        assert exc_info.value.status_code == 400
        assert "Insufficient funds" in str(exc_info.value.detail)

    async def test_create_transaction_payment_error(
        self,
        sample_transaction_create,
        mock_transaction_service,
        mock_idempotency_service,
    ):
        """Test handling payment error during transaction creation."""
        # Setup mocks
        idempotency_key = "test-key-123"
        mock_idempotency_service.get_or_generate_key.return_value = idempotency_key

        # Configure the idempotency service to execute the operation and let it fail
        async def mock_execute_operation(key, operation, ttl_seconds=None):
            # This will call the actual operation function which should raise PaymentError
            return await operation()

        mock_idempotency_service.execute_idempotent_operation.side_effect = (
            mock_execute_operation
        )

        # Mock transaction service to raise PaymentError
        mock_transaction_service.create_transaction.side_effect = PaymentError(
            "Insufficient funds"
        )

        # Execute & Verify
        with pytest.raises(HTTPException) as exc_info:
            await create_transaction(
                data=sample_transaction_create,
                idempotency_key=idempotency_key,
                transaction_service=mock_transaction_service,
                idempotency_service=mock_idempotency_service,
            )

        assert exc_info.value.status_code == 400

    async def test_get_transaction_success(
        self, sample_transaction_response, mock_transaction_service
    ):
        """Test successful transaction retrieval."""
        # Setup
        transaction_uid = "test-uuid-123"
        mock_transaction_service.get_transaction.return_value = (
            sample_transaction_response
        )

        # Execute
        result = await get_transaction(transaction_uid, mock_transaction_service)

        # Verify
        assert result == sample_transaction_response
        mock_transaction_service.get_transaction.assert_called_once_with(
            transaction_uid
        )

    async def test_get_transaction_not_found(self, mock_transaction_service):
        """Test transaction not found error."""
        # Setup
        transaction_uid = "nonexistent-uuid"
        mock_transaction_service.get_transaction.side_effect = HTTPException(
            status_code=404, detail="Transaction not found"
        )

        # Execute & Verify
        with pytest.raises(HTTPException) as exc_info:
            await get_transaction(transaction_uid, mock_transaction_service)

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail).lower()
