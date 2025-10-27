import datetime
import logging
import typing
import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.types import TransactionType

logger = logging.getLogger(__name__)


METADATA: typing.Final = sa.MetaData()


class Base(DeclarativeBase):
    metadata = METADATA


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        sa.String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    balance: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=20, scale=2), nullable=False, default=Decimal("0.00")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    # Relationship
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="user", cascade="all, delete-orphan"
    )


class Transaction(Base):
    __tablename__ = "transactions"

    uid: Mapped[str] = mapped_column(
        sa.String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    type: Mapped[TransactionType] = mapped_column(
        sa.Enum(TransactionType), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=20, scale=2), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    user_id: Mapped[str] = mapped_column(
        sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="transactions")

    # Indexes for performance
    __table_args__ = (
        sa.Index("ix_transactions_user_id", "user_id"),
        sa.Index("ix_transactions_created_at", "created_at"),
        sa.Index("ix_transactions_user_created", "user_id", "created_at"),
        sa.CheckConstraint("amount > 0", name="check_positive_amount"),
    )
