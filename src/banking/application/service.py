"""Atomic balance changes with durable idempotency receipts."""

import hashlib
import json
from typing import cast
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from banking.domain.exceptions import (
    BankingError,
    IdempotencyConflict,
    InsufficientFunds,
    InvalidAmount,
    UnknownAccount,
    UnsupportedAction,
)
from banking.domain.models import (
    MAX_TRANSACTION_AMOUNT,
    BankingAction,
    TransactionResult,
)
from banking.infrastructure.models import (
    Account,
    LedgerEntry,
    Operation,
    RequestReceipt,
)


def request_hash(action: str, account: str, amount: int) -> str:
    """Preserve the fingerprint format used by existing database receipts."""
    payload = json.dumps(
        {"action": action, "account": account, "amount": amount},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class BankingService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_balance(self, account: str) -> int:
        balance = self.session.scalar(
            select(Account.balance_minor).where(Account.account_id == account)
        )
        if balance is None:
            raise UnknownAccount("Account does not exist")
        return balance

    def _replay(
        self, record: RequestReceipt | Operation, fingerprint: str
    ) -> TransactionResult | BankingError:
        if record.request_hash != fingerprint:
            return IdempotencyConflict("Request ID was already used with different data")
        if record.action not in ("deposit", "withdraw"):
            raise RuntimeError("Unrecognized stored banking action")

        if isinstance(record, RequestReceipt) and record.status == "error":
            match record.error_code:
                case "ACCOUNT_NOT_FOUND":
                    return UnknownAccount("Account does not exist")
                case "INSUFFICIENT_FUNDS":
                    return InsufficientFunds("Insufficient account balance")
                case _:
                    raise RuntimeError("Unrecognized stored business error")

        if isinstance(record, RequestReceipt) and record.status != "success":
            raise RuntimeError("Non-terminal receipt became visible")

        balance = record.result_balance_minor
        if balance is None:
            raise RuntimeError("Stored transaction is missing its balance")
        return TransactionResult(
            request_id=record.request_id,
            account=record.account_id,
            action=cast(BankingAction, record.action),
            balance=balance,
            replayed=True,
        )

    def _update_balance(self, account: str, delta: int) -> int | None:
        """Adjust the balance atomically, rejecting overdrafts in SQL."""
        statement = (
            update(Account)
            .where(Account.account_id == account)
            .values(balance_minor=Account.balance_minor + delta)
            .returning(Account.balance_minor)
        )
        if delta < 0:
            statement = statement.where(Account.balance_minor >= -delta)
        return self.session.execute(statement).scalar_one_or_none()

    def _record_success(self, receipt: RequestReceipt, balance: int, delta: int) -> None:
        """Write the parent operation before the ledger's foreign key reference."""
        self.session.add(
            Operation(
                request_id=receipt.request_id,
                account_id=receipt.account_id,
                action=receipt.action,
                amount_minor=receipt.amount_minor,
                request_hash=receipt.request_hash,
                result_balance_minor=balance,
                status="success",
            )
        )
        self.session.flush()
        self.session.add(
            LedgerEntry(
                entry_id=str(uuid4()),
                request_id=receipt.request_id,
                account_id=receipt.account_id,
                delta_minor=delta,
                balance_after_minor=balance,
            )
        )

    def _transact(
        self, request_id: str, action: BankingAction, account: str, amount: int
    ) -> TransactionResult | BankingError:
        fingerprint = request_hash(action, account, amount)
        existing = self.session.get(RequestReceipt, request_id) or self.session.get(
            Operation, request_id
        )
        if existing is not None:
            return self._replay(existing, fingerprint)

        receipt = RequestReceipt(
            request_id=request_id,
            request_hash=fingerprint,
            account_id=account,
            action=action,
            amount_minor=amount,
            status="pending",
        )
        self.session.add(receipt)
        self.session.flush()

        delta = amount if action == "deposit" else -amount
        balance = self._update_balance(account, delta)

        if balance is None:
            error: BankingError = (
                UnknownAccount("Account does not exist")
                if self.session.get(Account, account) is None
                else InsufficientFunds("Insufficient account balance")
            )
            receipt.status = "error"
            receipt.error_code = error.code
            return error

        self._record_success(receipt, balance, delta)
        receipt.status = "success"
        receipt.result_balance_minor = balance
        return TransactionResult(request_id, account, action, balance)

    def transact(
        self, *, request_id: str, action: str, account: str, amount: int
    ) -> TransactionResult:
        if action not in ("deposit", "withdraw"):
            raise UnsupportedAction("Unsupported banking action")
        if type(amount) is not int or not 0 < amount <= MAX_TRANSACTION_AMOUNT:
            raise InvalidAmount("Amount must be a positive integer at most 10**15")

        with self.session.begin():
            result = self._transact(request_id, action, account, amount)
        if isinstance(result, BankingError):
            raise result
        return result
