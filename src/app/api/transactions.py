import logging
import typing

from fastapi import APIRouter, Depends, HTTPException, Header
from starlette import status

from app import schemas
from app.exceptions import PaymentError
from app.services.transaction_service import TransactionService
from app.api.base import (
    get_transaction_service,
    get_idempotency_service,
    ValidatedTransaction,
)
from app.services.idempotency_service import (
    IdempotencyService,
    IdempotencyConflictError,
    IdempotencyFailureError,
)

logger = logging.getLogger(__name__)

ROUTER: typing.Final = APIRouter(prefix="/transactions", tags=["transactions"])


async def _create_transaction(
    transaction_service: TransactionService, data: ValidatedTransaction
) -> schemas.TransactionResponse:
    """Create transaction with logging - extracted for better testability."""
    transaction = await transaction_service.create_transaction(data)
    logger.info(f"Created transaction: {transaction.uid} for user {data.user_id}")
    return transaction


@ROUTER.post(
    "", response_model=schemas.TransactionResponse, status_code=status.HTTP_201_CREATED
)
async def create_transaction(
    data: ValidatedTransaction,
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
    transaction_service: TransactionService = Depends(get_transaction_service),
    idempotency_service: IdempotencyService = Depends(get_idempotency_service),
) -> schemas.TransactionResponse:
    """Create a deposit or withdrawal transaction with idempotency support.

    Args:
        data: Validated transaction data with user existence check
        idempotency_key: Optional idempotency key from header
        transaction_service: Injected transaction service dependency
        idempotency_service: Idempotency service for duplicate prevention

    Returns:
        TransactionResponse: Created transaction with UID and updated balance
    """
    key = idempotency_service.get_or_generate_key(idempotency_key)

    try:
        result = await idempotency_service.execute_idempotent_operation(
            key=key,
            operation=lambda: _create_transaction(transaction_service, data),
            ttl_seconds=3600,
        )

        # Handle both fresh results and cached dictionary responses
        return (
            result
            if isinstance(result, schemas.TransactionResponse)
            else schemas.TransactionResponse(**result)
        )

    except IdempotencyConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Request is currently being processed. Please try again later.",
        )
    except IdempotencyFailureError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PaymentError as e:
        logger.warning(f"Transaction failed: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during transaction processing: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@ROUTER.get("/{transaction_uid}", response_model=schemas.TransactionResponse)
async def get_transaction(
    transaction_uid: str,
    transaction_service: TransactionService = Depends(get_transaction_service),
) -> schemas.TransactionResponse:
    """Get transaction details by UID.

    Args:
        transaction_uid: Unique transaction identifier
        transaction_service: Injected transaction service dependency

    Returns:
        TransactionResponse: Transaction data including amount and balance
    """
    return await transaction_service.get_transaction(transaction_uid)
