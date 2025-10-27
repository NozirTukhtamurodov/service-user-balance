"""
Integration test configuration and fixtures.
"""

import asyncio
import os
import pytest
import pytest_asyncio
from decimal import Decimal
from typing import AsyncGenerator
from httpx import AsyncClient
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from fastapi import FastAPI
import redis.asyncio as redis

from app.application import AppBuilder
from app.api.base import get_db, get_settings
from app.models import Base, User, Transaction
from app.settings import Settings
from app.types import TransactionType
from app.utils import RedisIdempotencyStorage, get_idempotency_storage


# Test database configuration - use environment variable or fallback
TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://test_user:test_password@localhost:5432/test_db",
)


class TestSettings(Settings):
    """Test-specific settings."""

    database_url: str = TEST_DATABASE_URL
    debug: bool = True
    # Use test Redis host from environment or default
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = 6379
    redis_db: int = 1  # Use different Redis DB for tests


@pytest_asyncio.fixture
async def test_redis_client() -> AsyncGenerator[redis.Redis, None]:
    """Create a test Redis client that's properly managed for each test."""
    # Use test Redis configuration
    redis_url = f"redis://{os.getenv('REDIS_HOST', 'localhost')}:6379/1"

    redis_client = redis.from_url(redis_url, decode_responses=True)

    try:
        # Test connection
        await redis_client.ping()

        # Clear any existing data in test Redis DB
        await redis_client.flushdb()

        yield redis_client

    finally:
        # Clean up: clear test data and close connection
        await redis_client.flushdb()
        await redis_client.aclose()


@pytest_asyncio.fixture
async def test_idempotency_storage(
    test_redis_client: redis.Redis,
) -> RedisIdempotencyStorage:
    """Create a test idempotency storage that uses the test Redis client."""
    # Create a mock storage that uses the test Redis client directly
    storage = RedisIdempotencyStorage(redis_url="redis://test")  # URL not used
    storage._redis = test_redis_client  # Override with test client
    return storage


@pytest_asyncio.fixture
async def test_engine():
    """Create test database engine for each test."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,  # Set to True for SQL debugging
        pool_pre_ping=True,
    )
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Clean up: Drop all tables and dispose engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a database session for testing."""
    session_maker = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_maker() as session:
        yield session
        # Clean up any remaining transactions
        await session.rollback()


@pytest_asyncio.fixture
async def app(
    test_engine, test_idempotency_storage: RedisIdempotencyStorage
) -> AsyncGenerator[FastAPI, None]:
    """Create FastAPI application for testing."""
    # Import here to avoid circular imports
    from app.utils import set_test_idempotency_storage, reset_idempotency_storage

    # Set the global test storage
    set_test_idempotency_storage(test_idempotency_storage)

    # Create app builder and get app
    app_builder = AppBuilder()
    app = app_builder.app

    # Create test settings
    test_settings = TestSettings()

    # Override dependency to return test session maker
    def get_test_session_maker():
        return async_sessionmaker(
            test_engine, class_=AsyncSession, expire_on_commit=False
        )

    # Override settings dependency
    def get_test_settings():
        return test_settings

    app.dependency_overrides[get_db] = get_test_session_maker
    app.dependency_overrides[get_settings] = get_test_settings

    yield app

    # Clean up: reset global storage
    reset_idempotency_storage()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Create HTTP client for API testing."""
    from httpx import ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest_asyncio.fixture
async def sample_user(db_session: AsyncSession) -> User:
    """Create a sample user in the database."""
    user = User(name="John Doe", balance=Decimal("100.00"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def multiple_users(db_session: AsyncSession) -> list[User]:
    """Create multiple users for testing."""
    users = []
    for i in range(3):
        user = User(name=f"User {i+1}", balance=Decimal("1000.00"))
        db_session.add(user)
        users.append(user)

    await db_session.commit()

    for user in users:
        await db_session.refresh(user)

    return users


@pytest_asyncio.fixture
async def sample_transaction(
    db_session: AsyncSession, sample_user: User
) -> Transaction:
    """Create a sample transaction in the database."""
    transaction = Transaction(
        type=TransactionType.DEPOSIT, amount=Decimal("50.00"), user_id=sample_user.id
    )
    db_session.add(transaction)
    await db_session.commit()
    await db_session.refresh(transaction)
    return transaction


# Helper functions for integration tests
async def create_test_user(
    session: AsyncSession, name: str, balance: Decimal = Decimal("0.00")
) -> User:
    """Helper to create a user in tests."""
    user = User(name=name, balance=balance)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def create_test_transaction(
    session: AsyncSession,
    user_id: str,
    transaction_type: TransactionType,
    amount: Decimal,
) -> Transaction:
    """Helper to create a transaction in tests."""
    transaction = Transaction(type=transaction_type, amount=amount, user_id=user_id)
    session.add(transaction)
    await session.commit()
    await session.refresh(transaction)
    return transaction
