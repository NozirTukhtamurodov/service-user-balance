"""
Integration tests for concurrent transactions and race condition handling.
"""

import asyncio
import pytest
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from tests.integration.conftest import create_test_user


class TestConcurrentTransactions:
    """Tests for concurrent transaction handling and race conditions."""

    async def test_concurrent_deposits_no_race_condition(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test that concurrent deposits don't create race conditions."""
        # Create user with initial balance
        user = await create_test_user(db_session, "Concurrent User", Decimal("0.00"))

        # Define concurrent transactions
        async def make_deposit(amount: float):
            return await client.post(
                "/api/transactions",
                json={"type": "DEPOSIT", "amount": amount, "user_id": user.id},
            )

        # Execute multiple deposits concurrently
        deposit_amounts = [100.00, 150.00, 75.00, 200.00, 50.00]
        tasks = [make_deposit(amount) for amount in deposit_amounts]

        responses = await asyncio.gather(*tasks)

        # Verify all deposits succeeded
        for response in responses:
            assert response.status_code == 201

        # Verify final balance is correct
        await db_session.refresh(user)
        expected_balance = sum(Decimal(str(amount)) for amount in deposit_amounts)
        assert user.balance == expected_balance

    async def test_concurrent_withdrawals_with_sufficient_funds(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test concurrent withdrawals when there are sufficient funds."""
        # Create user with sufficient balance
        initial_balance = Decimal("1000.00")
        user = await create_test_user(db_session, "Rich User", initial_balance)

        async def make_withdrawal(amount: float):
            return await client.post(
                "/api/transactions",
                json={"type": "WITHDRAW", "amount": amount, "user_id": user.id},
            )

        # Execute withdrawals that total less than balance
        withdrawal_amounts = [50.00, 75.00, 100.00, 25.00]  # Total: 250.00
        tasks = [make_withdrawal(amount) for amount in withdrawal_amounts]

        responses = await asyncio.gather(*tasks)

        # All withdrawals should succeed
        for response in responses:
            assert response.status_code == 201

        # Verify final balance
        await db_session.refresh(user)
        expected_balance = initial_balance - sum(
            Decimal(str(amount)) for amount in withdrawal_amounts
        )
        assert user.balance == expected_balance

    async def test_concurrent_withdrawals_insufficient_funds_handling(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test handling of concurrent withdrawals when funds become insufficient."""
        # Create user with limited balance
        initial_balance = Decimal("100.00")
        user = await create_test_user(db_session, "Limited User", initial_balance)

        async def make_withdrawal(amount: float):
            return await client.post(
                "/api/transactions",
                json={"type": "WITHDRAW", "amount": amount, "user_id": user.id},
            )

        # Execute withdrawals that together exceed balance
        withdrawal_amounts = [60.00, 70.00, 80.00]  # Total exceeds 100.00
        tasks = [make_withdrawal(amount) for amount in withdrawal_amounts]

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Some withdrawals should succeed, others should fail
        successful_withdrawals = []
        failed_withdrawals = []

        for i, response in enumerate(responses):
            if hasattr(response, "status_code"):
                if response.status_code == 201:
                    successful_withdrawals.append(withdrawal_amounts[i])
                elif response.status_code == 400:
                    failed_withdrawals.append(withdrawal_amounts[i])

        # At least one should fail due to insufficient funds
        assert len(failed_withdrawals) > 0

        # Verify balance is not negative
        await db_session.refresh(user)
        assert user.balance >= Decimal("0.00")

        # Verify balance consistency
        total_withdrawn = sum(Decimal(str(amount)) for amount in successful_withdrawals)
        expected_balance = initial_balance - total_withdrawn
        assert user.balance == expected_balance

    async def test_mixed_concurrent_transactions(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test mixed deposits and withdrawals happening concurrently."""
        # Create user with moderate balance
        initial_balance = Decimal("500.00")
        user = await create_test_user(db_session, "Active User", initial_balance)

        async def make_transaction(tx_type: str, amount: float):
            return await client.post(
                "/api/transactions",
                json={"type": tx_type, "amount": amount, "user_id": user.id},
            )

        # Mix of deposits and withdrawals
        transactions = [
            ("DEPOSIT", 100.00),
            ("WITHDRAW", 50.00),
            ("DEPOSIT", 75.00),
            ("WITHDRAW", 25.00),
            ("DEPOSIT", 200.00),
            ("WITHDRAW", 100.00),
        ]

        tasks = [make_transaction(tx_type, amount) for tx_type, amount in transactions]
        responses = await asyncio.gather(*tasks)

        # Calculate expected balance
        expected_balance = initial_balance
        successful_transactions = []

        for i, response in enumerate(responses):
            if response.status_code == 201:
                tx_type, amount = transactions[i]
                successful_transactions.append((tx_type, amount))
                if tx_type == "DEPOSIT":
                    expected_balance += Decimal(str(amount))
                else:
                    expected_balance -= Decimal(str(amount))

        # Verify final balance
        await db_session.refresh(user)
        assert user.balance == expected_balance
        assert user.balance >= Decimal("0.00")  # Should never go negative

    async def test_concurrent_transactions_multiple_users(
        self, client: AsyncClient, multiple_users: list[User]
    ):
        """Test concurrent transactions across multiple users."""

        async def user_transaction_sequence(user: User):
            """Execute a sequence of transactions for a single user."""
            transactions = [
                await client.post(
                    "/api/transactions",
                    json={"type": "DEPOSIT", "amount": 200.00, "user_id": user.id},
                ),
                await client.post(
                    "/api/transactions",
                    json={"type": "WITHDRAW", "amount": 50.00, "user_id": user.id},
                ),
                await client.post(
                    "/api/transactions",
                    json={"type": "DEPOSIT", "amount": 100.00, "user_id": user.id},
                ),
            ]
            return transactions

        # Execute transactions for all users concurrently
        tasks = [user_transaction_sequence(user) for user in multiple_users]
        all_responses = await asyncio.gather(*tasks)

        # Verify all transactions succeeded
        for user_responses in all_responses:
            for response in user_responses:
                assert response.status_code == 201

        # Verify each user's final balance
        # Each user: 1000.00 (initial) + 200.00 - 50.00 + 100.00 = 1250.00
        for user in multiple_users:
            balance_response = await client.get(f"/api/users/{user.id}/balance")
            assert balance_response.status_code == 200
            assert balance_response.json()["balance"] == "1250.00"


class TestDatabaseConsistency:
    """Tests for database consistency and constraint enforcement."""

    async def test_foreign_key_constraint_enforcement(self, client: AsyncClient):
        """Test that foreign key constraints are properly enforced."""
        # Try to create transaction with non-existent user
        response = await client.post(
            "/api/transactions",
            json={
                "type": "DEPOSIT",
                "amount": 100.00,
                "user_id": "completely-fake-user-id",
            },
        )

        # Should fail due to foreign key constraint via validation
        assert response.status_code == 404

    async def test_balance_never_negative_constraint(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test that user balance can never go negative through the application."""
        # Create user with small balance
        user = await create_test_user(db_session, "Poor User", Decimal("10.00"))

        # Try to withdraw more than available
        response = await client.post(
            "/api/transactions",
            json={"type": "WITHDRAW", "amount": 50.00, "user_id": user.id},
        )

        assert response.status_code == 400
        assert "Insufficient funds" in response.json()["detail"]

        # Verify balance unchanged
        await db_session.refresh(user)
        assert user.balance == Decimal("10.00")

    async def test_transaction_amount_positive_constraint(
        self, client: AsyncClient, sample_user: User
    ):
        """Test that transaction amounts must be positive."""
        # Try negative amount
        response = await client.post(
            "/api/transactions",
            json={"type": "DEPOSIT", "amount": -50.00, "user_id": sample_user.id},
        )

        assert response.status_code == 422  # Validation error

        # Try zero amount
        response = await client.post(
            "/api/transactions",
            json={"type": "DEPOSIT", "amount": 0.00, "user_id": sample_user.id},
        )

        assert response.status_code == 422  # Validation error

    async def test_decimal_precision_handling(
        self, client: AsyncClient, db_session: AsyncSession, sample_user: User
    ):
        """Test that decimal precision is handled correctly."""
        # Test with various decimal precisions
        test_amounts = [10.1, 10.12, 10.123, 10.1234, 10.99999]

        for amount in test_amounts:
            response = await client.post(
                "/api/transactions",
                json={"type": "DEPOSIT", "amount": amount, "user_id": sample_user.id},
            )

            assert response.status_code == 201

            # Verify amount is properly rounded to 2 decimal places
            response_amount = Decimal(response.json()["amount"])
            expected_amount = Decimal(str(amount)).quantize(Decimal("0.01"))
            assert response_amount == expected_amount
