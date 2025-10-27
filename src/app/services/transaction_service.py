from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession as AsyncSessionType
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import schemas
from app.models import Transaction
from app.repositories.transaction import TransactionRepository
from app.types import TransactionType


class TransactionService:

    def __init__(self, session_maker: async_sessionmaker[AsyncSessionType]):
        self.transaction_repo = TransactionRepository(session_maker=session_maker)

    async def create_transaction(
        self, transaction_data: schemas.TransactionCreate
    ) -> schemas.TransactionResponse:
        """Create new transaction with balance calculation.

        Args:
            transaction_data: Transaction creation data with user_id, amount, type

        Returns:
            TransactionResponse: Created transaction with UID and details
        """
        transaction = (
            await self.transaction_repo.create_transaction_with_balance_calculation(
                data=transaction_data, balance_calculator_func=self._calculate_balance
            )
        )
        return self._build_transaction_response(transaction)

    def _calculate_balance(
        self,
        current_balance: Decimal,
        transaction_type: TransactionType,
        amount: Decimal,
    ) -> Decimal:
        """Calculate new balance based on transaction type.

        Args:
            current_balance: User's current balance
            transaction_type: DEPOSIT or WITHDRAW
            amount: Transaction amount (positive)

        Returns:
            Decimal: New calculated balance

        Raises:
            ValueError: For insufficient funds or unknown transaction type
        """
        if transaction_type == TransactionType.DEPOSIT:
            return current_balance + amount

        if transaction_type == TransactionType.WITHDRAW:
            return self._calculate_withdrawal_balance(current_balance, amount)

        raise ValueError(f"Unknown transaction type: {transaction_type}")

    def _calculate_withdrawal_balance(
        self, current_balance: Decimal, amount: Decimal
    ) -> Decimal:
        """Calculate balance for withdrawal with validation.

        Args:
            current_balance: User's current balance
            amount: Withdrawal amount

        Returns:
            Decimal: New balance after withdrawal

        Raises:
            ValueError: If insufficient funds
        """
        new_balance = current_balance - amount
        if new_balance < 0:
            raise ValueError("Insufficient funds for withdrawal")
        return new_balance

    async def get_transaction(self, transaction_id: str) -> schemas.TransactionResponse:
        """Get transaction by UID.

        Args:
            transaction_id: Transaction UID string

        Returns:
            TransactionResponse: Transaction details

        Raises:
            HTTPException: 404 if transaction not found
        """
        transaction = await self.transaction_repo.get_transaction_by_uid(transaction_id)
        if not transaction:
            raise HTTPException(status_code=404, detail="Transaction not found")
        return self._build_transaction_response(transaction)

    def _build_transaction_response(
        self, transaction: Transaction
    ) -> schemas.TransactionResponse:
        """Build transaction response from model.

        Args:
            transaction: Transaction model instance

        Returns:
            TransactionResponse: Formatted transaction response
        """
        return schemas.TransactionResponse(
            uid=transaction.uid,
            amount=transaction.amount,
            type=transaction.type,
            user_id=transaction.user_id,
            created_at=transaction.created_at,
        )

    async def get_user_balance_at_time(
        self, user_id: str, timestamp: datetime
    ) -> Decimal:
        """Calculate user balance at specific timestamp.

        Args:
            user_id: User UUID string
            timestamp: Target datetime for balance calculation

        Returns:
            Decimal: User balance at specified time
        """
        return await self.transaction_repo.get_user_balance_at_time(user_id, timestamp)
