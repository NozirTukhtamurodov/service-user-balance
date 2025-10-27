import pytest
from decimal import Decimal
from datetime import datetime
from pydantic import ValidationError

from app import schemas
from app.types import TransactionType


class TestUserSchemas:
    def test_user_create_valid(self):
        data = {"name": "John Doe"}
        user = schemas.UserCreate.model_validate(data)
        assert user.name == "John Doe"

    def test_user_create_strips_whitespace(self):
        data = {"name": "  John Doe  "}
        user = schemas.UserCreate.model_validate(data)
        assert user.name == "John Doe"

    def test_user_create_empty_name(self):
        with pytest.raises(ValidationError) as exc_info:
            schemas.UserCreate.model_validate({"name": ""})
        assert "String should have at least 1 character" in str(exc_info.value)

    def test_user_create_whitespace_only_name(self):
        with pytest.raises(ValidationError) as exc_info:
            schemas.UserCreate.model_validate({"name": "   "})

        assert "Name cannot be empty" in str(exc_info.value)

    def test_user_create_name_too_long(self):
        """Test UserCreate with name exceeding max length."""
        long_name = "x" * 256  # Exceeds 255 character limit

        with pytest.raises(ValidationError) as exc_info:
            schemas.UserCreate.model_validate({"name": long_name})

        assert "String should have at most 255 characters" in str(exc_info.value)

    def test_user_response_valid(self):
        """Test UserResponse with valid data."""
        data = {
            "id": "test-123",
            "name": "John Doe",
            "balance": Decimal("100.50"),
            "created_at": datetime.now(),
        }
        user = schemas.UserResponse.model_validate(data)

        assert user.id == "test-123"
        assert user.name == "John Doe"
        assert user.balance == Decimal("100.50")

    def test_user_balance_response(self):
        """Test UserBalanceResponse."""
        data = {"balance": Decimal("250.75")}
        response = schemas.UserBalanceResponse.model_validate(data)

        assert response.balance == Decimal("250.75")


class TestTransactionSchemas:
    """Test cases for Transaction-related schemas."""

    def test_transaction_create_valid_deposit(self):
        """Test TransactionCreate with valid deposit data."""
        data = {
            "type": TransactionType.DEPOSIT,
            "amount": Decimal("50.00"),
            "user_id": "test-user-123",
        }
        transaction = schemas.TransactionCreate.model_validate(data)

        assert transaction.type == TransactionType.DEPOSIT
        assert transaction.amount == Decimal("50.00")
        assert transaction.user_id == "test-user-123"

    def test_transaction_create_valid_withdrawal(self):
        """Test TransactionCreate with valid withdrawal data."""
        data = {
            "type": TransactionType.WITHDRAW,
            "amount": Decimal("25.00"),
            "user_id": "test-user-123",
        }
        transaction = schemas.TransactionCreate.model_validate(data)

        assert transaction.type == TransactionType.WITHDRAW
        assert transaction.amount == Decimal("25.00")

    def test_transaction_create_zero_amount(self):
        """Test TransactionCreate with zero amount."""
        data = {
            "type": TransactionType.DEPOSIT,
            "amount": Decimal("0.00"),
            "user_id": "test-user-123",
        }

        with pytest.raises(ValidationError) as exc_info:
            schemas.TransactionCreate.model_validate(data)

        assert "Input should be greater than 0" in str(exc_info.value)

    def test_transaction_create_negative_amount(self):
        """Test TransactionCreate with negative amount."""
        data = {
            "type": TransactionType.DEPOSIT,
            "amount": Decimal("-10.00"),
            "user_id": "test-user-123",
        }

        with pytest.raises(ValidationError) as exc_info:
            schemas.TransactionCreate.model_validate(data)

        assert "Input should be greater than 0" in str(exc_info.value)

    def test_transaction_create_amount_precision(self):
        """Test TransactionCreate amount precision handling."""
        data = {
            "type": TransactionType.DEPOSIT,
            "amount": Decimal("50.123"),  # 3 decimal places
            "user_id": "test-user-123",
        }
        transaction = schemas.TransactionCreate.model_validate(data)

        # Should be rounded to 2 decimal places
        assert transaction.amount == Decimal("50.12")

    def test_transaction_response_valid(self):
        """Test TransactionResponse with valid data."""
        data = {
            "uid": "test-transaction-123",
            "amount": Decimal("75.00"),
            "type": TransactionType.DEPOSIT,
            "user_id": "test-user-123",
            "created_at": datetime.now(),
        }
        response = schemas.TransactionResponse.model_validate(data)

        assert response.uid == "test-transaction-123"
        assert response.amount == Decimal("75.00")
        assert response.type == TransactionType.DEPOSIT
        assert response.user_id == "test-user-123"

    def test_balance_history_request_valid(self):
        """Test BalanceHistoryRequest with valid data."""
        data = {"user_id": "test-user-123", "timestamp": datetime.now()}
        request = schemas.BalanceHistoryRequest.model_validate(data)

        assert request.user_id == "test-user-123"
        assert isinstance(request.timestamp, datetime)

    def test_balance_history_request_no_timestamp(self):
        """Test BalanceHistoryRequest without timestamp."""
        data = {"user_id": "test-user-123"}
        request = schemas.BalanceHistoryRequest.model_validate(data)

        assert request.user_id == "test-user-123"
        assert request.timestamp is None

    def test_balance_response_valid(self):
        """Test BalanceResponse with valid data."""
        data = {"user_id": "test-user-123", "balance": Decimal("150.75")}
        response = schemas.BalanceResponse.model_validate(data)

        assert response.user_id == "test-user-123"
        assert response.balance == Decimal("150.75")
