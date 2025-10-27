from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    AsyncSession as AsyncSessionType,
)

from app import schemas
from app.models import User
from app.services.transaction_service import TransactionService
from app.services.user_service import UserService
from app.services.idempotency_service import IdempotencyService
from app.settings import Settings
from app.utils import get_idempotency_storage, IdempotencyRecord, IdempotencyStatus
from app.utils import RedisIdempotencyStorage
from uuid import uuid4


def get_settings() -> Settings:
    raise NotImplementedError


def get_db() -> async_sessionmaker[AsyncSessionType]:
    """Database session maker dependency."""
    raise NotImplementedError


def get_user_service(
    db: async_sessionmaker[AsyncSessionType] = Depends(get_db),
) -> UserService:
    return UserService(session_maker=db)


def get_transaction_service(
    db: async_sessionmaker[AsyncSessionType] = Depends(get_db),
) -> TransactionService:
    return TransactionService(session_maker=db)


def get_idempotency_service(
    settings: Settings = Depends(get_settings),
) -> IdempotencyService:
    """Get idempotency service dependency.

    Args:
        settings: Application settings

    Returns:
        IdempotencyService: Service for managing idempotent operations
    """
    from app.services.idempotency_service import IdempotencyService
    from app.utils import get_idempotency_storage

    storage = get_idempotency_storage(settings.redis_url)
    return IdempotencyService(storage)


async def get_existing_user(
    user_id: str,
    user_service: UserService = Depends(get_user_service),
) -> User:
    """Validate user existence and return user object.

    Args:
        user_id: User UUID string
        user_service: Injected user service dependency

    Returns:
        User: Validated user model instance

    Raises:
        HTTPException: 404 if user not found
    """
    user = await user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


async def validate_transaction_user(
    transaction_data: schemas.TransactionCreate,
    user_service: UserService = Depends(get_user_service),
) -> schemas.TransactionCreate:
    """Validate user exists for transaction creation.

    Args:
        transaction_data: Transaction creation data with user_id
        user_service: Injected user service dependency

    Returns:
        TransactionCreate: Validated transaction data

    Raises:
        HTTPException: 404 if user not found
    """
    user = await user_service.get_user_by_id(transaction_data.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return transaction_data


async def get_idempotency_key(
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
) -> str:
    """Get or generate idempotency key for request deduplication.

    Args:
        idempotency_key: Optional idempotency key from header

    Returns:
        str: Idempotency key (provided or generated)
    """
    if idempotency_key:
        return idempotency_key

    # Generate new key if not provided
    return str(uuid4())


def get_storage(settings: Settings = Depends(get_settings)) -> RedisIdempotencyStorage:
    """Get idempotency storage dependency.

    Args:
        settings: Application settings

    Returns:
        RedisIdempotencyStorage: Redis storage instance for idempotency
    """
    return get_idempotency_storage(settings.redis_url)


async def check_idempotency(
    idempotency_key: str = Depends(get_idempotency_key),
    storage: RedisIdempotencyStorage = Depends(get_storage),
) -> Optional[IdempotencyRecord]:
    """Check if request with this idempotency key was already processed.

    Args:
        idempotency_key: Request idempotency key
        storage: Storage instance

    Returns:
        IdempotencyRecord: Existing record if found, None if new request

    Raises:
        HTTPException: 409 if request is currently in process (retry scenario)
    """
    record = await storage.get_idempotency_record(idempotency_key)

    if record is None:
        return None

    # If request is in process, return 409 Conflict to indicate retry later
    if record.status == IdempotencyStatus.IN_PROCESS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Request is currently being processed. Please retry later.",
        )

    return record


async def start_idempotent_operation(
    idempotency_key: str,
    storage: RedisIdempotencyStorage = Depends(get_storage),
) -> bool:
    """Start an idempotent operation by setting IN_PROCESS status.

    Args:
        idempotency_key: Request idempotency key
        storage: Storage instance

    Returns:
        bool: True if operation started successfully, False if duplicate
    """
    return await storage.start_idempotent_operation(idempotency_key, ttl_seconds=3600)


async def complete_idempotent_operation(
    idempotency_key: str,
    success: bool,
    response_data: Optional[dict] = None,
    error: Optional[str] = None,
    storage: RedisIdempotencyStorage = Depends(get_storage),
) -> None:
    """Complete an idempotent operation with success or failure status.

    Args:
        idempotency_key: Request idempotency key
        success: True for success, False for failure
        response_data: Response data for successful operations
        error: Error message for failed operations
        storage: Storage instance
    """
    await storage.complete_idempotent_operation(
        idempotency_key,
        success=success,
        data=response_data,
        error=error,
        ttl_seconds=3600,
    )


# Type aliases for cleaner code
ExistingUser = Annotated[User, Depends(get_existing_user)]
ValidatedTransaction = Annotated[
    schemas.TransactionCreate, Depends(validate_transaction_user)
]
IdempotencyKey = Annotated[str, Depends(get_idempotency_key)]
IdempotentRecord = Annotated[Optional[IdempotencyRecord], Depends(check_idempotency)]
