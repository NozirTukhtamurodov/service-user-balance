"""
Common test fixtures and configuration for pytest.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, Mock
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app import schemas
from app.models import User, Transaction
from app.types import TransactionType


@pytest.fixture
def mock_db_session():
    """Mock database session for testing."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.begin = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock()

    # Mock begin() context manager - must be callable that returns an async context manager
    begin_mock = AsyncMock()
    begin_mock.__aenter__ = AsyncMock(
        return_value=None
    )  # begin() doesn't return anything on __aenter__
    begin_mock.__aexit__ = AsyncMock(return_value=None)
    session.begin = Mock(return_value=begin_mock)  # Use regular Mock, not AsyncMock

    return session


@pytest.fixture
def mock_session_maker(mock_db_session):
    """Mock session maker that returns mocked session with proper async context manager."""
    session_maker = MagicMock(spec=async_sessionmaker)

    # Create an async context manager that returns the mock session
    async_context = AsyncMock()
    async_context.__aenter__ = AsyncMock(return_value=mock_db_session)
    async_context.__aexit__ = AsyncMock()

    # Make session_maker() return the async context manager
    session_maker.return_value = async_context

    return session_maker


@pytest.fixture
def sample_user():
    """Sample user instance for testing."""
    return User(
        id="test-user-123",
        name="John Doe",
        balance=Decimal("100.00"),
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_transaction():
    """Sample transaction instance for testing."""
    transaction = Transaction(
        uid="test-transaction-123",
        type=TransactionType.DEPOSIT,
        amount=Decimal("50.00"),
        user_id="test-user-123",
        created_at=datetime.now(timezone.utc),
    )
    # Add balance_after as runtime attribute
    transaction.balance_after = Decimal("150.00")
    return transaction


@pytest.fixture
def sample_user_create():
    """Sample user creation data."""
    return schemas.UserCreate(name="John Doe")


@pytest.fixture
def sample_transaction_create():
    """Sample transaction creation data."""
    return schemas.TransactionCreate(
        type=TransactionType.DEPOSIT, amount=Decimal("50.00"), user_id="test-user-123"
    )


@pytest.fixture
def sample_withdrawal_create():
    """Sample withdrawal transaction creation data."""
    return schemas.TransactionCreate(
        type=TransactionType.WITHDRAW, amount=Decimal("25.00"), user_id="test-user-123"
    )


class MockSQLAlchemyResult:
    """Mock SQLAlchemy result object."""

    def __init__(self, return_value=None):
        self.return_value = return_value

    def scalar_one_or_none(self):
        return self.return_value

    def scalar(self):
        return self.return_value


@pytest.fixture
def mock_result():
    """Factory for creating mock SQLAlchemy results."""
    return MockSQLAlchemyResult
