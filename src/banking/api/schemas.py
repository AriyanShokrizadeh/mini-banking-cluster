"""Validated request and response models for the public v1 API."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StrictInt

from banking.domain.models import MAX_TRANSACTION_AMOUNT, BankingAction

AccountID = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
PositiveAmount = Annotated[StrictInt, Field(gt=0, le=MAX_TRANSACTION_AMOUNT)]


class TransactionIn(BaseModel):
    request_id: UUID
    action: BankingAction
    account: AccountID
    amount: PositiveAmount


class TransactionOut(BaseModel):
    status: Literal["success"] = "success"
    request_id: str
    account: str
    balance: int
    replayed: bool = False


class BalanceOut(BaseModel):
    status: Literal["success"] = "success"
    account: str
    balance: int
