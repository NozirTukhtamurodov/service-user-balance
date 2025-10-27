"""
Unit tests for TransactionService.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from app import schemas
from app.services.transaction_service import TransactionService
from app.types import TransactionType


class TestTransactionService:
    """Test cases for TransactionService."""

    @pytest.fixture
    def transaction_service(self, mock_session_maker):
        """Create TransactionService instance with mocked repository."""
        with patch(
            "app.services.transaction_service.TransactionRepository"
        ) as MockRepo:
            mock_repo = Mock()
            MockRepo.return_value = mock_repo
            service = TransactionService(mock_session_maker)
            service.transaction_repo = mock_repo
            return service

    async def test_create_transaction_success(
        self, transaction_service, sample_transaction_create, sample_transaction
    ):
        """Test successful transaction creation."""
        # Setup
        transaction_service.transaction_repo.create_transaction_with_balance_calculation = AsyncMock(
            return_value=sample_transaction
        )

        # Execute
        result = await transaction_service.create_transaction(sample_transaction_create)

        # Verify
        assert isinstance(result, schemas.TransactionResponse)
        assert result.uid == sample_transaction.uid
        assert result.amount == sample_transaction.amount
        assert result.type == sample_transaction.type
        assert result.user_id == sample_transaction.user_id
        assert result.created_at == sample_transaction.created_at

        transaction_service.transaction_repo.create_transaction_with_balance_calculation.assert_called_once_with(
            data=sample_transaction_create,
            balance_calculator_func=transaction_service._calculate_balance,
        )

    async def test_get_transaction_success(
        self, transaction_service, sample_transaction
    ):
        """Test successful transaction retrieval."""
        # Setup
        transaction_service.transaction_repo.get_transaction_by_uid = AsyncMock(
            return_value=sample_transaction
        )

        # Execute
        result = await transaction_service.get_transaction("test-transaction-123")

        # Verify
        assert isinstance(result, schemas.TransactionResponse)
        assert result.uid == sample_transaction.uid
        transaction_service.transaction_repo.get_transaction_by_uid.assert_called_once_with(
            "test-transaction-123"
        )

    async def test_get_transaction_not_found(self, transaction_service):
        """Test transaction retrieval when transaction doesn't exist."""
        # Setup
        transaction_service.transaction_repo.get_transaction_by_uid = AsyncMock(
            return_value=None
        )

        # Execute & Verify
        with pytest.raises(HTTPException) as exc_info:
            await transaction_service.get_transaction("nonexistent-transaction")

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Transaction not found"

    def test_calculate_balance_deposit(self, transaction_service):
        """Test balance calculation for deposit transaction."""
        # Setup
        current_balance = Decimal("100.00")
        amount = Decimal("50.00")

        # Execute
        result = transaction_service._calculate_balance(
            current_balance, TransactionType.DEPOSIT, amount
        )

        # Verify
        assert result == Decimal("150.00")

    def test_calculate_balance_withdraw_success(self, transaction_service):
        """Test balance calculation for successful withdrawal."""
        # Setup
        current_balance = Decimal("100.00")
        amount = Decimal("50.00")

        # Execute
        result = transaction_service._calculate_balance(
            current_balance, TransactionType.WITHDRAW, amount
        )

        # Verify
        assert result == Decimal("50.00")

    def test_calculate_balance_withdraw_insufficient_funds(self, transaction_service):
        """Test balance calculation for withdrawal with insufficient funds."""
        # Setup
        current_balance = Decimal("100.00")
        amount = Decimal("150.00")

        # Execute & Verify
        with pytest.raises(ValueError, match="Insufficient funds for withdrawal"):
            transaction_service._calculate_balance(
                current_balance, TransactionType.WITHDRAW, amount
            )

    def test_calculate_balance_unknown_type(self, transaction_service):
        """Test balance calculation with unknown transaction type."""
        # Setup
        current_balance = Decimal("100.00")
        amount = Decimal("50.00")

        # Execute & Verify
        with pytest.raises(ValueError, match="Unknown transaction type"):
            transaction_service._calculate_balance(
                current_balance, "INVALID_TYPE", amount  # Invalid transaction type
            )

    def test_calculate_withdrawal_balance_success(self, transaction_service):
        """Test withdrawal balance calculation with sufficient funds."""
        # Setup
        current_balance = Decimal("100.00")
        amount = Decimal("30.00")

        # Execute
        result = transaction_service._calculate_withdrawal_balance(
            current_balance, amount
        )

        # Verify
        assert result == Decimal("70.00")

    def test_calculate_withdrawal_balance_insufficient_funds(self, transaction_service):
        """Test withdrawal balance calculation with insufficient funds."""
        # Setup
        current_balance = Decimal("50.00")
        amount = Decimal("100.00")

        # Execute & Verify
        with pytest.raises(ValueError, match="Insufficient funds for withdrawal"):
            transaction_service._calculate_withdrawal_balance(current_balance, amount)

    def test_calculate_withdrawal_balance_exact_amount(self, transaction_service):
        """Test withdrawal balance calculation with exact balance amount."""
        # Setup
        current_balance = Decimal("100.00")
        amount = Decimal("100.00")

        # Execute
        result = transaction_service._calculate_withdrawal_balance(
            current_balance, amount
        )

        # Verify
        assert result == Decimal("0.00")

    def test_build_transaction_response(self, transaction_service, sample_transaction):
        """Test building transaction response from transaction model."""
        # Execute
        result = transaction_service._build_transaction_response(sample_transaction)

        # Verify
        assert isinstance(result, schemas.TransactionResponse)
        assert result.uid == sample_transaction.uid
        assert result.amount == sample_transaction.amount
        assert result.type == sample_transaction.type
        assert result.user_id == sample_transaction.user_id
        assert result.created_at == sample_transaction.created_at

    async def test_get_user_balance_at_time(self, transaction_service):
        """Test getting user balance at specific time."""
        # Setup
        from datetime import datetime

        test_timestamp = datetime.now()
        expected_balance = Decimal("250.00")

        transaction_service.transaction_repo.get_user_balance_at_time = AsyncMock(
            return_value=expected_balance
        )

        # Execute
        result = await transaction_service.get_user_balance_at_time(
            "test-user-123", test_timestamp
        )

        # Verify
        assert result == expected_balance
        transaction_service.transaction_repo.get_user_balance_at_time.assert_called_once_with(
            "test-user-123", test_timestamp
        )
