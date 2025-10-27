import logging
import typing
from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from typing import Optional
from starlette import status

from app import schemas
from app.api.base import (
    ExistingUser,
    get_transaction_service,
    get_user_service,
)
from app.exceptions import UserExistsError
from app.services.transaction_service import TransactionService
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

ROUTER: typing.Final = APIRouter(prefix="/users", tags=["users"])


@ROUTER.post(
    "", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED
)
async def create_user(
    data: schemas.UserCreate,
    user_service: UserService = Depends(get_user_service),
) -> schemas.UserResponse:
    """Create a new user with zero initial balance.

    Args:
        data: User creation data containing name
        user_service: Injected user service dependency

    Returns:
        UserResponse: Created user with ID and balance
    """
    try:
        user = await user_service.create_user(data)
        logger.info(f"Created user: {user.id}")
        return schemas.UserResponse.model_validate(user)
    except UserExistsError as e:
        logger.warning(f"User creation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@ROUTER.get("/{user_id}", response_model=schemas.UserResponse)
async def get_user(user: ExistingUser) -> schemas.UserResponse:
    """Get user information including current balance.

    Args:
        user: User object (automatically validated by dependency)

    Returns:
        UserResponse: User data with ID, name and balance
    """
    return schemas.UserResponse.model_validate(user)


@ROUTER.get("/{user_id}/balance", response_model=schemas.UserBalanceResponse)
async def get_user_balance(
    user: ExistingUser,
    timestamp: Optional[datetime] = Query(None),
    transaction_service: TransactionService = Depends(get_transaction_service),
) -> schemas.UserBalanceResponse:
    """Get user balance (current or historical).

    Args:
        user: User object (automatically validated by dependency)
        timestamp: Optional datetime for historical balance lookup
        transaction_service: Injected transaction service dependency

    Returns:
        UserBalanceResponse: User balance at specified time or current
    """
    if timestamp is None:
        balance = user.balance
    else:
        balance = await transaction_service.get_user_balance_at_time(user.id, timestamp)

    return schemas.UserBalanceResponse(balance=balance)
