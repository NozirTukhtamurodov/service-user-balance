from datetime import datetime
from decimal import Decimal
from typing import Optional

import pydantic
from pydantic import BaseModel, Field, field_validator

from app.types import TransactionType


class Base(BaseModel):
    model_config = pydantic.ConfigDict(from_attributes=True)


# User schemas
class UserCreate(Base):
    name: str = Field(..., min_length=1, max_length=255, description="User name")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()


class UserResponse(Base):
    id: str
    name: str
    balance: Decimal = Field(..., json_schema_extra={"example": "1250.75"})
    created_at: datetime


class UserBalanceResponse(Base):
    balance: Decimal = Field(..., json_schema_extra={"example": "1250.75"})


class BalanceResponse(Base):
    user_id: str
    balance: Decimal = Field(..., json_schema_extra={"example": "1250.75"})


# Transaction schemas
class TransactionCreate(Base):
    amount: Decimal = Field(
        ...,
        gt=0,
        description="Transaction amount (must be positive)",
        json_schema_extra={"example": "100.50"},
    )
    type: TransactionType
    user_id: str = Field(..., description="User ID")

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be positive")
        # Limit to 2 decimal places for currency
        return v.quantize(Decimal("0.01"))


class TransactionResponse(Base):
    uid: str  # This is the actual ID/primary key
    amount: Decimal = Field(..., json_schema_extra={"example": "100.50"})
    type: TransactionType
    user_id: str
    created_at: datetime


class BalanceHistoryRequest(Base):
    user_id: str
    timestamp: Optional[datetime] = None
