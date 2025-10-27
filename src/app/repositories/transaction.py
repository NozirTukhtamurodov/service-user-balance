import logging
from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    AsyncSession as AsyncSessionType,
)
import sqlalchemy as sa

from app import schemas
from app.exceptions import PaymentError
from app.models import Transaction, User
from app.types import TransactionType

logger = logging.getLogger(__name__)


class TransactionRepository:
    def __init__(self, session_maker: async_sessionmaker[AsyncSessionType]):
        self.session_maker = session_maker

    async def create_transaction_with_balance_calculation(
        self,
        data: schemas.TransactionCreate,
        balance_calculator_func: Callable[[Decimal, TransactionType, Decimal], Decimal],
    ) -> Transaction:
        """Create transaction and update user balance atomically.

        Args:
            data: Transaction creation data
            balance_calculator_func: Function to calculate new balance

        Returns:
            Transaction: Created transaction with balance_after attribute

        Raises:
            PaymentError: If transaction fails or user not found
        """
        try:
            async with self.session_maker() as session:
                async with session.begin():
                    user = await self._get_user_with_lock(session, data.user_id)
                    new_balance = await self._calculate_new_balance(
                        user.balance, data, balance_calculator_func
                    )
                    transaction = await self._create_transaction_record(
                        session, data, new_balance
                    )
                    await self._update_user_balance(session, data.user_id, new_balance)
                    await session.flush()
                    return transaction
        except IntegrityError as e:
            logger.error(f"Transaction integrity error: {e}")
            raise PaymentError("Transaction already exists or user not found")

    async def _calculate_new_balance(
        self,
        current_balance: Decimal,
        data: schemas.TransactionCreate,
        balance_calculator_func: Callable[[Decimal, TransactionType, Decimal], Decimal],
    ) -> Decimal:
        """Calculate new balance using provided calculator function.

        Args:
            current_balance: User's current balance
            data: Transaction data
            balance_calculator_func: Business logic function for balance calculation

        Returns:
            Decimal: New calculated balance

        Raises:
            PaymentError: If balance calculation fails
        """
        try:
            return balance_calculator_func(current_balance, data.type, data.amount)
        except ValueError as e:
            raise PaymentError(str(e))

    async def get_transaction_by_id(self, transaction_id: str) -> Optional[Transaction]:
        """Get transaction by internal ID.

        Args:
            transaction_id: Internal transaction ID

        Returns:
            Optional[Transaction]: Transaction if found, None otherwise
        """
        async with self.session_maker() as session:
            result = await session.execute(
                sa.select(Transaction).where(Transaction.id == transaction_id)
            )
            return result.scalar_one_or_none()

    async def get_transaction_by_uid(
        self, transaction_uid: str
    ) -> Optional[Transaction]:
        """Get transaction by UID.

        Args:
            transaction_uid: Transaction UID string

        Returns:
            Optional[Transaction]: Transaction if found, None otherwise
        """
        async with self.session_maker() as session:
            result = await session.execute(
                sa.select(Transaction).where(Transaction.uid == transaction_uid)
            )
            return result.scalar_one_or_none()

    async def calculate_balance_at_time(
        self, user_id: str, timestamp: datetime
    ) -> Decimal:
        """Calculate user balance at specific timestamp.

        Args:
            user_id: User UUID string
            timestamp: Target datetime for balance calculation

        Returns:
            Decimal: User balance at specified time
        """
        return await self.get_user_balance_at_time(user_id, timestamp)

    async def _get_user_with_lock(
        self, session: AsyncSessionType, user_id: str
    ) -> User:
        """Get user with row lock for concurrent transaction safety.

        Args:
            session: Active database session
            user_id: User UUID string

        Returns:
            User: User instance with exclusive lock

        Raises:
            PaymentError: If user not found
        """
        result = await session.execute(
            sa.select(User).with_for_update().where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise PaymentError(f"User with id {user_id} not found")

        return user

    async def _update_user_balance(
        self, session: AsyncSessionType, user_id: str, new_balance: Decimal
    ) -> None:
        """Update user balance within existing transaction session.

        Args:
            session: Active database session
            user_id: User UUID string
            new_balance: New balance to set
        """
        await session.execute(
            sa.update(User).where(User.id == user_id).values(balance=new_balance)
        )

    async def _create_transaction_record(
        self,
        session: AsyncSessionType,
        data: schemas.TransactionCreate,
        balance_after: Decimal,
    ) -> Transaction:
        """Create and persist transaction record.

        Args:
            session: Active database session
            data: Transaction creation data
            balance_after: User balance after transaction

        Returns:
            Transaction: Created transaction with balance_after attribute
        """
        transaction = Transaction(
            type=data.type,
            amount=data.amount,
            user_id=data.user_id,
        )
        # Store balance_after as a runtime attribute (not persisted to DB)
        transaction.balance_after = balance_after
        session.add(transaction)
        await session.flush()
        await session.refresh(transaction)
        # Re-set the balance_after since it won't be loaded from DB
        transaction.balance_after = balance_after
        return transaction

    async def get_transaction_by_uid(
        self, transaction_uid: str
    ) -> Optional[Transaction]:
        """Get transaction by UID.

        Args:
            transaction_uid: Transaction UID string

        Returns:
            Optional[Transaction]: Transaction if found, None otherwise
        """
        async with self.session_maker() as session:
            return await self._get_transaction_by_uid(session, transaction_uid)

    async def _get_transaction_by_uid(
        self, session: AsyncSessionType, transaction_uid: str
    ) -> Optional[Transaction]:
        """Get transaction by UID within provided session.

        Args:
            session: Active database session
            transaction_uid: Transaction UID string

        Returns:
            Optional[Transaction]: Transaction if found, None otherwise
        """
        result = await session.execute(
            sa.select(Transaction).where(Transaction.uid == transaction_uid)
        )
        return result.scalar_one_or_none()

    async def get_user_balance_at_time(
        self, user_id: str, timestamp: datetime
    ) -> Decimal:
        """Calculate user balance up to specific timestamp.

        Args:
            user_id: User UUID string
            timestamp: Target datetime for balance calculation

        Returns:
            Decimal: Calculated balance at specified time
        """
        async with self.session_maker() as session:
            query = self._build_balance_history_query(user_id, timestamp)
            result = await session.execute(query)
            return result.scalar() or Decimal("0")

    def _build_balance_history_query(self, user_id: str, timestamp: datetime):
        """Build SQL query for calculating historical balance.

        Args:
            user_id: User UUID string
            timestamp: Target datetime

        Returns:
            SQLAlchemy select query for balance calculation
        """
        return sa.select(
            sa.func.coalesce(
                sa.func.sum(self._get_transaction_amount_expression()), Decimal("0")
            )
        ).where(
            sa.and_(
                Transaction.user_id == user_id,
                Transaction.created_at <= timestamp,
            )
        )

    def _get_transaction_amount_expression(self):
        """Get SQL expression for transaction amount calculation.

        Returns:
            SQLAlchemy case expression for signed transaction amounts
        """
        return sa.case(
            (Transaction.type == TransactionType.DEPOSIT, Transaction.amount),
            (Transaction.type == TransactionType.WITHDRAW, -Transaction.amount),
            else_=Decimal("0"),
        )
