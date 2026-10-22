"""Domain value objects independent of HTTP and persistence."""

from dataclasses import dataclass
from typing import Literal

BankingAction = Literal["deposit", "withdraw"]
MAX_TRANSACTION_AMOUNT = 10**15


@dataclass(frozen=True)
class TransactionResult:
    request_id: str
    account: str
    action: BankingAction
    balance: int
    replayed: bool = False
