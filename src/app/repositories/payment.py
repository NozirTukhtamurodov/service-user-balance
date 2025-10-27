import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession as AsyncSessionType
import sqlalchemy as sa

from app import models, schemas
from app.exceptions import UserExistsError, PaymentError
from app.models import User, Transaction
from app.types import TransactionType

logger = logging.getLogger(__name__)


class PaymentRepository:
    """Repository for payment operations with reduced session nesting."""

    def __init__(self, session: AsyncSessionType):
        self.session = session

    async def create_user(self, data: schemas.UserCreate) -> User:
        """Create a new user with zero balance.

        Args:
            data: User creation data containing name

        Returns:
            User: Created user object

        Raises:
            UserExistsError: If user creation fails due to constraints
        """
        try:
            user = User(
                name=data.name,
                balance=Decimal("0.00"),
            )
            self.session.add(user)
            await self.session.flush()
            await self.session.refresh(user)
            return user
        except IntegrityError as e:
            logger.error(f"Failed to create user: {e}")
            raise UserExistsError(f"User with name '{data.name}' might already exist")

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID.

        Args:
            user_id: User identifier

        Returns:
            Optional[User]: User object if found, None otherwise
        """
        result = await self.session.execute(sa.select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_user_balance(
        self, user_id: str, ts: Optional[datetime] = None
    ) -> Optional[Decimal]:
        """Get user balance at current time or specific timestamp.

        Args:
            user_id: User identifier
            ts: Optional timestamp for historical balance calculation

        Returns:
            Optional[Decimal]: User balance if user exists, None otherwise
        """
        if ts is None:
            result = await self.session.execute(
                sa.select(User.balance).where(User.id == user_id)
            )
            balance = result.scalar_one_or_none()
            return balance
        else:
            result = await self.session.execute(
                sa.select(
                    sa.func.coalesce(
                        sa.func.sum(
                            sa.case(
                                (
                                    Transaction.type == TransactionType.DEPOSIT,
                                    Transaction.amount,
                                ),
                                (
                                    Transaction.type == TransactionType.WITHDRAW,
                                    -Transaction.amount,
                                ),
                                else_=Decimal("0"),
                            )
                        ),
                        Decimal("0"),
                    )
                ).where(
                    sa.and_(
                        Transaction.user_id == user_id,
                        Transaction.created_at <= ts,
                    )
                )
            )
            return result.scalar()

    async def add_transaction(self, data: schemas.TransactionCreate) -> Transaction:
        """Add a new transaction with proper balance validation and idempotency"""
        try:
            return await self._add_transaction_atomic(data)
        except IntegrityError as e:
            logger.error(f"Transaction integrity error: {e}")
            raise PaymentError("Transaction already exists or user not found")

    async def _add_transaction_atomic(
        self, data: schemas.TransactionCreate
    ) -> Transaction:
        """Atomically process transaction with balance update.

        Args:
            data: Transaction creation data

        Returns:
            Transaction: Created transaction object

        Raises:
            PaymentError: If user not found or insufficient funds
        """
        user_result = await self.session.execute(
            sa.select(User).with_for_update().where(User.id == data.user_id)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            raise PaymentError(f"User with id {data.user_id} not found")

        if data.type == TransactionType.DEPOSIT:
            new_balance = user.balance + data.amount
        else:  # WITHDRAW
            new_balance = user.balance - data.amount
            if new_balance < 0:
                raise PaymentError("Insufficient funds")

        transaction = Transaction(
            type=data.type,
            amount=data.amount,
            user_id=data.user_id,
        )
        self.session.add(transaction)

        await self.session.execute(
            sa.update(User).where(User.id == data.user_id).values(balance=new_balance)
        )

        await self.session.flush()
        await self.session.refresh(transaction)

        return transaction

    async def get_transaction(self, transaction_uid: str) -> Optional[Transaction]:
        """Get transaction by UID.

        Args:
            transaction_uid: Transaction unique identifier

        Returns:
            Optional[Transaction]: Transaction object if found, None otherwise
        """
        result = await self.session.execute(
            sa.select(Transaction).where(Transaction.uid == transaction_uid)
        )
        return result.scalar_one_or_none()
