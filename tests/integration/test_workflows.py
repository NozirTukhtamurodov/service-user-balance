"""
Integration tests for complete end-to-end user workflows.
"""

import pytest
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Transaction


class TestCompleteUserWorkflows:
    """End-to-end workflow tests simulating real user scenarios."""

    async def test_new_user_complete_journey(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test complete journey of a new user from creation to multiple transactions."""

        # Step 1: Create new user
        user_response = await client.post("/api/users", json={"name": "Alice Smith"})
        assert user_response.status_code == 201
        user_data = user_response.json()
        user_id = user_data["id"]

        # Verify initial state
        assert user_data["balance"] == "0.00"
        assert user_data["name"] == "Alice Smith"

        # Step 2: Check initial balance via API
        balance_response = await client.get(f"/api/users/{user_id}/balance")
        assert balance_response.status_code == 200
        assert balance_response.json()["balance"] == "0.00"

        # Step 3: Make first deposit
        first_deposit = await client.post(
            "/api/transactions",
            json={"type": "DEPOSIT", "amount": 500.00, "user_id": user_id},
        )
        assert first_deposit.status_code == 201
        assert first_deposit.json()["amount"] == "500.00"

        # Step 4: Verify balance after deposit
        balance_response = await client.get(f"/api/users/{user_id}/balance")
        assert balance_response.json()["balance"] == "500.00"

        # Step 5: Make a withdrawal
        withdrawal = await client.post(
            "/api/transactions",
            json={"type": "WITHDRAW", "amount": 150.00, "user_id": user_id},
        )
        assert withdrawal.status_code == 201

        # Step 6: Make another deposit
        second_deposit = await client.post(
            "/api/transactions",
            json={"type": "DEPOSIT", "amount": 200.00, "user_id": user_id},
        )
        assert second_deposit.status_code == 201

        # Step 7: Verify final balance
        final_balance_response = await client.get(f"/api/users/{user_id}/balance")
        expected_balance = "550.00"  # 500 - 150 + 200
        assert final_balance_response.json()["balance"] == expected_balance

        # Step 8: Verify user details still correct
        user_details = await client.get(f"/api/users/{user_id}")
        assert user_details.status_code == 200
        user_details_data = user_details.json()
        assert user_details_data["name"] == "Alice Smith"
        assert user_details_data["balance"] == expected_balance

    async def test_multi_user_banking_scenario(self, client: AsyncClient):
        """Test scenario with multiple users performing various operations."""

        # Create three users
        users = []
        user_names = ["John", "Jane", "Bob"]

        for name in user_names:
            response = await client.post("/api/users", json={"name": name})
            assert response.status_code == 201
            users.append(response.json())

        # Each user makes initial deposits
        initial_deposits = [1000.00, 2000.00, 1500.00]

        for i, (user, amount) in enumerate(zip(users, initial_deposits)):
            response = await client.post(
                "/api/transactions",
                json={"type": "DEPOSIT", "amount": amount, "user_id": user["id"]},
            )
            assert response.status_code == 201

        # Verify all balances
        for i, user in enumerate(users):
            balance_response = await client.get(f"/api/users/{user['id']}/balance")
            expected_balance = f"{Decimal(str(initial_deposits[i])):.2f}"
            assert balance_response.json()["balance"] == expected_balance

        # John withdraws money
        john_withdrawal = await client.post(
            "/api/transactions",
            json={
                "type": "WITHDRAW",
                "amount": 300.00,
                "user_id": users[0]["id"],  # John
            },
        )
        assert john_withdrawal.status_code == 201

        # Jane makes another deposit
        jane_deposit = await client.post(
            "/api/transactions",
            json={
                "type": "DEPOSIT",
                "amount": 500.00,
                "user_id": users[1]["id"],  # Jane
            },
        )
        assert jane_deposit.status_code == 201

        # Bob tries to withdraw more than he has (should fail)
        bob_large_withdrawal = await client.post(
            "/api/transactions",
            json={
                "type": "WITHDRAW",
                "amount": 2000.00,  # More than his 1500 balance
                "user_id": users[2]["id"],  # Bob
            },
        )
        assert bob_large_withdrawal.status_code == 400

        # Verify final balances
        expected_balances = ["700.00", "2500.00", "1500.00"]  # John, Jane, Bob

        for i, (user, expected) in enumerate(zip(users, expected_balances)):
            balance_response = await client.get(f"/api/users/{user['id']}/balance")
            assert balance_response.json()["balance"] == expected

    async def test_transaction_history_workflow(self, client: AsyncClient):
        """Test workflow involving transaction retrieval and history."""

        # Create user
        user_response = await client.post(
            "/api/users", json={"name": "Transaction History User"}
        )
        user_id = user_response.json()["id"]

        # Perform several transactions and collect their UIDs
        transactions_made = []

        # Make deposits and withdrawals
        transaction_data = [
            {"type": "DEPOSIT", "amount": 1000.00},
            {"type": "WITHDRAW", "amount": 200.00},
            {"type": "DEPOSIT", "amount": 300.00},
            {"type": "WITHDRAW", "amount": 150.00},
        ]

        for tx_data in transaction_data:
            tx_data["user_id"] = user_id
            response = await client.post("/api/transactions", json=tx_data)
            assert response.status_code == 201
            transactions_made.append(response.json())

        # Verify we can retrieve each transaction by UID
        for tx in transactions_made:
            tx_response = await client.get(f"/api/transactions/{tx['uid']}")
            assert tx_response.status_code == 200

            retrieved_tx = tx_response.json()
            assert retrieved_tx["uid"] == tx["uid"]
            assert retrieved_tx["amount"] == tx["amount"]
            assert retrieved_tx["type"] == tx["type"]
            assert retrieved_tx["user_id"] == user_id

    async def test_edge_case_workflow(self, client: AsyncClient):
        """Test workflow with edge cases and boundary conditions."""

        # Create user
        user_response = await client.post("/api/users", json={"name": "Edge Case User"})
        user_id = user_response.json()["id"]

        # Test very small amounts
        small_deposit = await client.post(
            "/api/transactions",
            json={
                "type": "DEPOSIT",
                "amount": 0.01,  # Smallest possible amount
                "user_id": user_id,
            },
        )
        assert small_deposit.status_code == 201
        assert small_deposit.json()["amount"] == "0.01"

        # Test precision handling
        precise_deposit = await client.post(
            "/api/transactions",
            json={"type": "DEPOSIT", "amount": 99.99, "user_id": user_id},
        )
        assert precise_deposit.status_code == 201

        # Verify balance is exactly 100.00
        balance_response = await client.get(f"/api/users/{user_id}/balance")
        assert balance_response.json()["balance"] == "100.00"

        # Test withdrawal of exact balance
        exact_withdrawal = await client.post(
            "/api/transactions",
            json={"type": "WITHDRAW", "amount": 100.00, "user_id": user_id},
        )
        assert exact_withdrawal.status_code == 201

        # Balance should be exactly zero
        final_balance = await client.get(f"/api/users/{user_id}/balance")
        assert final_balance.json()["balance"] == "0.00"

        # Try to withdraw from zero balance (should fail)
        zero_withdrawal = await client.post(
            "/api/transactions",
            json={"type": "WITHDRAW", "amount": 0.01, "user_id": user_id},
        )
        assert zero_withdrawal.status_code == 400

    async def test_large_transaction_workflow(self, client: AsyncClient):
        """Test workflow with large transaction amounts."""

        # Create user for large transactions
        user_response = await client.post(
            "/api/users", json={"name": "High Value User"}
        )
        user_id = user_response.json()["id"]

        # Make large deposit
        large_amount = 999999.99
        large_deposit = await client.post(
            "/api/transactions",
            json={"type": "DEPOSIT", "amount": large_amount, "user_id": user_id},
        )
        assert large_deposit.status_code == 201
        assert large_deposit.json()["amount"] == f"{Decimal(str(large_amount)):.2f}"

        # Verify balance
        balance_response = await client.get(f"/api/users/{user_id}/balance")
        assert balance_response.json()["balance"] == f"{Decimal(str(large_amount)):.2f}"

        # Make large withdrawal
        withdrawal_amount = 500000.00
        large_withdrawal = await client.post(
            "/api/transactions",
            json={"type": "WITHDRAW", "amount": withdrawal_amount, "user_id": user_id},
        )
        assert large_withdrawal.status_code == 201

        # Verify final balance
        expected_final = Decimal(str(large_amount)) - Decimal(str(withdrawal_amount))
        final_balance = await client.get(f"/api/users/{user_id}/balance")
        assert final_balance.json()["balance"] == str(expected_final)

    async def test_error_recovery_workflow(self, client: AsyncClient):
        """Test system behavior and recovery from various error conditions."""

        # Create user
        user_response = await client.post(
            "/api/users", json={"name": "Error Test User"}
        )
        user_id = user_response.json()["id"]

        # Make successful deposit
        success_deposit = await client.post(
            "/api/transactions",
            json={"type": "DEPOSIT", "amount": 100.00, "user_id": user_id},
        )
        assert success_deposit.status_code == 201

        # Try invalid transaction (negative amount) - should fail
        invalid_tx = await client.post(
            "/api/transactions",
            json={"type": "DEPOSIT", "amount": -50.00, "user_id": user_id},
        )
        assert invalid_tx.status_code == 422  # Validation error

        # Verify balance unchanged after failed transaction
        balance_after_error = await client.get(f"/api/users/{user_id}/balance")
        assert balance_after_error.json()["balance"] == "100.00"

        # Try insufficient funds withdrawal
        insufficient_withdrawal = await client.post(
            "/api/transactions",
            json={"type": "WITHDRAW", "amount": 200.00, "user_id": user_id},
        )
        assert insufficient_withdrawal.status_code == 400

        # Verify balance still unchanged
        balance_still_same = await client.get(f"/api/users/{user_id}/balance")
        assert balance_still_same.json()["balance"] == "100.00"

        # Make valid withdrawal after errors
        valid_withdrawal = await client.post(
            "/api/transactions",
            json={"type": "WITHDRAW", "amount": 30.00, "user_id": user_id},
        )
        assert valid_withdrawal.status_code == 201

        # Verify system recovered and processed valid transaction
        final_balance = await client.get(f"/api/users/{user_id}/balance")
        assert final_balance.json()["balance"] == "70.00"
