from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app import schemas
from app.api.users import create_user, get_user, get_user_balance
from app.exceptions import UserExistsError


class TestUserAPI:
    async def test_create_user_success(self, sample_user_create, sample_user):
        mock_service = AsyncMock()
        mock_service.create_user.return_value = sample_user

        result = await create_user(sample_user_create, mock_service)

        assert isinstance(result, schemas.UserResponse)
        mock_service.create_user.assert_called_once_with(sample_user_create)

    async def test_create_user_already_exists(self, sample_user_create):
        mock_service = AsyncMock()
        mock_service.create_user.side_effect = UserExistsError("User already exists")

        with pytest.raises(HTTPException) as exc_info:
            await create_user(sample_user_create, mock_service)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "User already exists"

    async def test_get_user_success(self, sample_user):
        result = await get_user(sample_user)
        assert isinstance(result, schemas.UserResponse)

    async def test_get_user_balance_current(self, sample_user):
        mock_service = AsyncMock()

        result = await get_user_balance(sample_user, None, mock_service)

        assert isinstance(result, schemas.UserBalanceResponse)
        assert result.balance == sample_user.balance
        mock_service.get_user_balance_at_time.assert_not_called()

    async def test_get_user_balance_historical(self, sample_user):
        """Test getting historical user balance."""
        # Setup
        mock_service = AsyncMock()
        test_timestamp = datetime.now()
        expected_balance = Decimal("75.00")
        mock_service.get_user_balance_at_time.return_value = expected_balance

        # Execute
        result = await get_user_balance(sample_user, test_timestamp, mock_service)

        # Verify
        assert isinstance(result, schemas.UserBalanceResponse)
        assert result.balance == expected_balance
        mock_service.get_user_balance_at_time.assert_called_once_with(
            sample_user.id, test_timestamp
        )

    async def test_get_user_balance_historical_zero(self, sample_user):
        """Test getting historical balance when no transactions exist."""
        # Setup
        mock_service = AsyncMock()
        test_timestamp = datetime.now()
        mock_service.get_user_balance_at_time.return_value = Decimal("0.00")

        # Execute
        result = await get_user_balance(sample_user, test_timestamp, mock_service)

        # Verify
        assert isinstance(result, schemas.UserBalanceResponse)
        assert result.balance == Decimal("0.00")
        mock_service.get_user_balance_at_time.assert_called_once_with(
            sample_user.id, test_timestamp
        )
