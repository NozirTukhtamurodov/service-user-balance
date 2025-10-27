import enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.utils import RedisIdempotencyStorage


class TransactionType(enum.Enum):
    WITHDRAW = "WITHDRAW"
    DEPOSIT = "DEPOSIT"


# Type alias for idempotency storage
IdempotencyStorage = "RedisIdempotencyStorage"
