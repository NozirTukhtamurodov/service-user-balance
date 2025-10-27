"""
Unit tests for TransactionRepository.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.exceptions import PaymentError
from app.models import Transaction, User
from app.repositories.transaction import TransactionRepository
from app.types import TransactionType


class TestTransactionRepository:
    """Test cases for TransactionRepository."""

    @pytest.fixture
    def transaction_repo(self, mock_session_maker):
        """Create TransactionRepository instance with mocked session maker."""
        return TransactionRepository(mock_session_maker)

    async def test_create_transaction_with_balance_calculation_success(
        self,
        transaction_repo,
        mock_session_maker,
        mock_db_session,
        sample_transaction_create,
        sample_user,
        sample_transaction,
    ):
        """Test successful transaction creation with balance calculation."""

        # Setup
        def mock_balance_calculator(balance, tx_type, amount):
            return balance + amount

        # Mock the private methods
        transaction_repo._get_user_with_lock = AsyncMock(return_value=sample_user)
        transaction_repo._calculate_new_balance = AsyncMock(
            return_value=Decimal("150.00")
        )
        transaction_repo._create_transaction_record = AsyncMock(
            return_value=sample_transaction
        )
        transaction_repo._update_user_balance = AsyncMock()

        # Execute
        result = await transaction_repo.create_transaction_with_balance_calculation(
            data=sample_transaction_create,
            balance_calculator_func=mock_balance_calculator,
        )

        # Verify
        assert result == sample_transaction
        transaction_repo._get_user_with_lock.assert_called_once_with(
            mock_db_session, "test-user-123"
        )
        transaction_repo._calculate_new_balance.assert_called_once_with(
            sample_user.balance, sample_transaction_create, mock_balance_calculator
        )
        transaction_repo._create_transaction_record.assert_called_once_with(
            mock_db_session, sample_transaction_create, Decimal("150.00")
        )
        transaction_repo._update_user_balance.assert_called_once_with(
            mock_db_session, "test-user-123", Decimal("150.00")
        )

    async def test_create_transaction_with_balance_calculation_integrity_error(
        self, transaction_repo, sample_transaction_create
    ):
        """Test transaction creation with database integrity error."""

        # Setup
        def mock_balance_calculator(balance, tx_type, amount):
            return balance + amount

        # Mock session to raise IntegrityError
        with patch.object(transaction_repo, "session_maker") as mock_maker:
            mock_session = AsyncMock()

            # Create a proper async context manager for session.begin()
            mock_transaction_context = AsyncMock()
            mock_transaction_context.__aenter__ = AsyncMock(
                return_value=mock_transaction_context
            )
            mock_transaction_context.__aexit__ = AsyncMock(
                side_effect=IntegrityError("", "", "")
            )

            # Mock session.begin() to return the async context manager (not a coroutine)
            mock_session.begin = Mock(return_value=mock_transaction_context)

            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=None)

            # Execute & Verify
            with pytest.raises(
                PaymentError, match="Transaction already exists or user not found"
            ):
                await transaction_repo.create_transaction_with_balance_calculation(
                    data=sample_transaction_create,
                    balance_calculator_func=mock_balance_calculator,
                )

    async def test_calculate_new_balance_success(
        self, transaction_repo, sample_transaction_create
    ):
        """Test successful balance calculation."""

        # Setup
        def mock_calculator(balance, tx_type, amount):
            return balance + amount

        current_balance = Decimal("100.00")

        # Execute
        result = await transaction_repo._calculate_new_balance(
            current_balance, sample_transaction_create, mock_calculator
        )

        # Verify
        assert result == Decimal("150.00")

    async def test_calculate_new_balance_value_error(
        self, transaction_repo, sample_transaction_create
    ):
        """Test balance calculation with value error."""

        # Setup
        def mock_calculator(balance, tx_type, amount):
            raise ValueError("Insufficient funds")

        current_balance = Decimal("100.00")

        # Execute & Verify
        with pytest.raises(PaymentError, match="Insufficient funds"):
            await transaction_repo._calculate_new_balance(
                current_balance, sample_transaction_create, mock_calculator
            )

    async def test_get_user_with_lock_success(
        self, transaction_repo, mock_db_session, sample_user, mock_result
    ):
        """Test successful user retrieval with lock."""
        # Setup
        mock_db_session.execute.return_value = mock_result(sample_user)

        # Execute
        result = await transaction_repo._get_user_with_lock(
            mock_db_session, "test-user-123"
        )

        # Verify
        assert result == sample_user
        mock_db_session.execute.assert_called_once()

    async def test_get_user_with_lock_user_not_found(
        self, transaction_repo, mock_db_session, mock_result
    ):
        """Test user retrieval with lock when user doesn't exist."""
        # Setup
        mock_db_session.execute.return_value = mock_result(None)

        # Execute & Verify
        with pytest.raises(PaymentError, match="User with id test-user-123 not found"):
            await transaction_repo._get_user_with_lock(mock_db_session, "test-user-123")

    async def test_update_user_balance(self, transaction_repo, mock_db_session):
        """Test user balance update."""
        # Execute
        await transaction_repo._update_user_balance(
            mock_db_session, "test-user-123", Decimal("150.00")
        )

        # Verify
        mock_db_session.execute.assert_called_once()

    async def test_create_transaction_record(
        self,
        transaction_repo,
        mock_db_session,
        sample_transaction_create,
        sample_transaction,
    ):
        """Test transaction record creation."""
        # Setup
        balance_after = Decimal("150.00")

        with patch("app.repositories.transaction.Transaction") as MockTransaction:
            MockTransaction.return_value = sample_transaction

            # Execute
            result = await transaction_repo._create_transaction_record(
                mock_db_session, sample_transaction_create, balance_after
            )

            # Verify
            assert result == sample_transaction
            assert hasattr(result, "balance_after")
            assert result.balance_after == balance_after
            mock_db_session.add.assert_called_once_with(sample_transaction)
            mock_db_session.flush.assert_called_once()
            mock_db_session.refresh.assert_called_once_with(sample_transaction)

    async def test_get_transaction_by_uid_found(
        self, transaction_repo, mock_db_session, sample_transaction, mock_result
    ):
        """Test getting transaction by UID when it exists."""
        # Setup
        mock_db_session.execute.return_value = mock_result(sample_transaction)

        # Execute
        result = await transaction_repo.get_transaction_by_uid("test-transaction-123")

        # Verify
        assert result == sample_transaction

    async def test_get_transaction_by_uid_not_found(
        self, transaction_repo, mock_db_session, mock_result
    ):
        """Test getting transaction by UID when it doesn't exist."""
        # Setup
        mock_db_session.execute.return_value = mock_result(None)

        # Execute
        result = await transaction_repo.get_transaction_by_uid(
            "nonexistent-transaction"
        )

        # Verify
        assert result is None

    async def test_get_user_balance_at_time(
        self, transaction_repo, mock_db_session, mock_result
    ):
        """Test getting user balance at specific time."""
        # Setup
        expected_balance = Decimal("250.00")
        mock_db_session.execute.return_value = mock_result(expected_balance)
        test_timestamp = datetime.now()

        # Execute
        result = await transaction_repo.get_user_balance_at_time(
            "test-user-123", test_timestamp
        )

        # Verify
        assert result == expected_balance

    async def test_get_user_balance_at_time_no_transactions(
        self, transaction_repo, mock_db_session, mock_result
    ):
        """Test getting user balance when no transactions exist."""
        # Setup
        mock_db_session.execute.return_value = mock_result(None)
        test_timestamp = datetime.now()

        # Execute
        result = await transaction_repo.get_user_balance_at_time(
            "test-user-123", test_timestamp
        )

        # Verify
        assert result == Decimal("0")
