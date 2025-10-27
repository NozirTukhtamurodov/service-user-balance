"""
Integration tests for API endpoints with real database operations.
"""

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Transaction, User
from app.types import TransactionType


class TestUserAPIIntegration:
    """Integration tests for User API endpoints."""

    async def test_create_user_full_flow(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test complete user creation flow with database persistence."""
        # Create user via API
        user_data = {"name": "Alice Johnson"}
        response = await client.post("/api/users", json=user_data)

        assert response.status_code == 201
        response_data = response.json()

        # Verify response structure
        assert "id" in response_data
        assert response_data["name"] == "Alice Johnson"
        assert response_data["balance"] == "0.00"
        assert "created_at" in response_data

        user_id = response_data["id"]

        # Verify user was actually created in database
        user = await db_session.get(User, user_id)
        assert user is not None
        assert user.name == "Alice Johnson"
        assert user.balance == Decimal("0.00")

    async def test_get_user_with_real_data(
        self, client: AsyncClient, sample_user: User
    ):
        """Test getting user data from real database."""
        response = await client.get(f"/api/users/{sample_user.id}")

        assert response.status_code == 200
        response_data = response.json()

        assert response_data["id"] == sample_user.id
        assert response_data["name"] == sample_user.name
        assert response_data["balance"] == str(sample_user.balance)

    async def test_get_nonexistent_user(self, client: AsyncClient):
        """Test getting a user that doesn't exist."""
        fake_id = "non-existent-user-id"
        response = await client.get(f"/api/users/{fake_id}")

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    async def test_user_balance_endpoint(self, client: AsyncClient, sample_user: User):
        """Test getting user balance via API."""
        response = await client.get(f"/api/users/{sample_user.id}/balance")

        assert response.status_code == 200
        response_data = response.json()

        assert response_data["balance"] == str(sample_user.balance)

    async def test_create_duplicate_user_name_allowed(self, client: AsyncClient):
        """Test that duplicate user names are allowed (business requirement)."""
        user_data = {"name": "Duplicate User"}

        # Create first user
        response1 = await client.post("/api/users", json=user_data)
        assert response1.status_code == 201

        # Create second user with same name
        response2 = await client.post("/api/users", json=user_data)
        assert response2.status_code == 201

        # Verify they have different IDs
        user1_id = response1.json()["id"]
        user2_id = response2.json()["id"]
        assert user1_id != user2_id


class TestTransactionAPIIntegration:
    """Integration tests for Transaction API endpoints."""

    async def test_create_deposit_transaction_full_flow(
        self, client: AsyncClient, db_session: AsyncSession, sample_user: User
    ):
        """Test complete deposit transaction flow."""
        initial_balance = sample_user.balance
        transaction_data = {
            "type": "DEPOSIT",
            "amount": 50.00,
            "user_id": sample_user.id,
        }

        response = await client.post("/api/transactions", json=transaction_data)

        assert response.status_code == 201
        response_data = response.json()

        # Verify transaction response
        assert "uid" in response_data
        assert response_data["amount"] == "50.00"
        assert response_data["type"] == "DEPOSIT"
        assert response_data["user_id"] == sample_user.id
        assert "created_at" in response_data

        # Verify transaction was created in database
        await db_session.refresh(sample_user)
        assert sample_user.balance == initial_balance + Decimal("50.00")

    async def test_create_withdrawal_transaction_sufficient_funds(
        self, client: AsyncClient, db_session: AsyncSession, sample_user: User
    ):
        """Test withdrawal with sufficient funds."""
        # Ensure user has enough balance
        sample_user.balance = Decimal("200.00")
        await db_session.commit()

        transaction_data = {
            "type": "WITHDRAW",
            "amount": 75.00,
            "user_id": sample_user.id,
        }

        response = await client.post("/api/transactions", json=transaction_data)

        assert response.status_code == 201
        response_data = response.json()

        # Verify transaction
        assert response_data["amount"] == "75.00"
        assert response_data["type"] == "WITHDRAW"

        # Verify balance was updated
        await db_session.refresh(sample_user)
        assert sample_user.balance == Decimal("125.00")

    async def test_create_withdrawal_insufficient_funds(
        self, client: AsyncClient, sample_user: User
    ):
        """Test withdrawal with insufficient funds."""
        transaction_data = {
            "type": "WITHDRAW",
            "amount": 500.00,  # More than user's balance
            "user_id": sample_user.id,
        }

        response = await client.post("/api/transactions", json=transaction_data)

        assert response.status_code == 400
        assert "Insufficient funds" in response.json()["detail"]

    async def test_create_transaction_nonexistent_user(self, client: AsyncClient):
        """Test creating transaction for non-existent user."""
        transaction_data = {
            "type": "DEPOSIT",
            "amount": 50.00,
            "user_id": "non-existent-user-id",
        }

        response = await client.post("/api/transactions", json=transaction_data)

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    async def test_get_transaction_by_uid(
        self, client: AsyncClient, sample_transaction: Transaction
    ):
        """Test getting transaction by UID."""
        response = await client.get(f"/api/transactions/{sample_transaction.uid}")

        assert response.status_code == 200
        response_data = response.json()

        assert response_data["uid"] == sample_transaction.uid
        assert response_data["amount"] == str(sample_transaction.amount)
        assert response_data["type"] == sample_transaction.type.value
        assert response_data["user_id"] == sample_transaction.user_id

    async def test_get_nonexistent_transaction(self, client: AsyncClient):
        """Test getting a transaction that doesn't exist."""
        fake_uid = "non-existent-transaction-uid"
        response = await client.get(f"/api/transactions/{fake_uid}")

        assert response.status_code == 404
        assert "Transaction not found" in response.json()["detail"]


class TestDataConsistencyIntegration:
    """Integration tests for data consistency across operations."""

    async def test_balance_consistency_multiple_transactions(
        self, client: AsyncClient, db_session: AsyncSession, sample_user: User
    ):
        """Test that balance remains consistent across multiple transactions."""
        # Set initial balance
        sample_user.balance = Decimal("1000.00")
        await db_session.commit()

        transactions = [
            {"type": "DEPOSIT", "amount": 100.00},
            {"type": "WITHDRAW", "amount": 50.00},
            {"type": "DEPOSIT", "amount": 25.00},
            {"type": "WITHDRAW", "amount": 75.00},
        ]

        expected_balance = Decimal("1000.00")

        for transaction_data in transactions:
            transaction_data["user_id"] = sample_user.id
            response = await client.post("/api/transactions", json=transaction_data)
            assert response.status_code == 201

            # Update expected balance
            if transaction_data["type"] == "DEPOSIT":
                expected_balance += Decimal(str(transaction_data["amount"]))
            else:
                expected_balance -= Decimal(str(transaction_data["amount"]))

        # Verify final balance
        await db_session.refresh(sample_user)
        assert sample_user.balance == expected_balance

    async def test_transaction_atomicity(
        self, client: AsyncClient, db_session: AsyncSession, sample_user: User
    ):
        """Test that failed transactions don't affect user balance."""
        initial_balance = sample_user.balance

        # Attempt withdrawal with insufficient funds
        transaction_data = {
            "type": "WITHDRAW",
            "amount": 9999.00,  # Much more than available
            "user_id": sample_user.id,
        }

        response = await client.post("/api/transactions", json=transaction_data)
        assert response.status_code == 400

        # Verify balance unchanged
        await db_session.refresh(sample_user)
        assert sample_user.balance == initial_balance

    async def test_user_balance_endpoint_accuracy(
        self, client: AsyncClient, db_session: AsyncSession, sample_user: User
    ):
        """Test that balance endpoint returns accurate data after transactions."""
        # Perform some transactions
        await client.post(
            "/api/transactions",
            json={"type": "DEPOSIT", "amount": 200.00, "user_id": sample_user.id},
        )

        await client.post(
            "/api/transactions",
            json={"type": "WITHDRAW", "amount": 50.00, "user_id": sample_user.id},
        )

        # Check balance via API
        response = await client.get(f"/api/users/{sample_user.id}/balance")
        api_balance = Decimal(response.json()["balance"])

        # Check balance in database
        await db_session.refresh(sample_user)
        db_balance = sample_user.balance

        # They should match
        assert api_balance == db_balance
