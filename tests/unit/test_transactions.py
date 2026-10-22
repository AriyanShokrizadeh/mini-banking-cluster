"""Balance, atomicity, and idempotency on a local SQLAlchemy database."""

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from banking.application.service import BankingService, request_hash
from banking.domain.exceptions import (
    IdempotencyConflict,
    InsufficientFunds,
    InvalidAmount,
    UnknownAccount,
)
from banking.domain.models import TransactionResult
from banking.infrastructure.models import (
    Account,
    LedgerEntry,
    Operation,
    RequestReceipt,
)


def transact(
    engine: Engine,
    action: str,
    amount: int,
    *,
    request_id: str | None = None,
    account: str = "A1001",
) -> TransactionResult:
    with Session(engine) as session:
        return BankingService(session).transact(
            request_id=request_id or str(uuid4()),
            action=action,
            account=account,
            amount=amount,
        )


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_deposits_and_withdrawals_update_balance_and_ledger(engine: Engine) -> None:
    assert transact(engine, "deposit", 250).balance == 1250
    assert transact(engine, "withdraw", 70).balance == 1180
    with Session(engine) as session:
        assert session.get_one(Account, "A1001").balance_minor == 1180
        assert count(session, LedgerEntry) == count(session, Operation) == 2


def test_ledger_insert_respects_foreign_key(engine: Engine) -> None:
    """Catch YSQL-style parent/child insert ordering errors using SQLite FK checks."""
    request_id = str(uuid4())
    result = transact(engine, "deposit", 25, request_id=request_id)

    with Session(engine) as session:
        operation = session.get_one(Operation, request_id)
        ledger = session.scalar(select(LedgerEntry).where(LedgerEntry.request_id == request_id))
        assert result.balance == 1025
        assert ledger is not None
        assert ledger.balance_after_minor == operation.result_balance_minor == 1025
        assert session.connection().exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_replay_does_not_deposit_twice(engine: Engine) -> None:
    request_id = str(uuid4())
    first = transact(engine, "deposit", 40, request_id=request_id)
    replay = transact(engine, "deposit", 40, request_id=request_id)
    assert (first.balance, first.replayed) == (1040, False)
    assert (replay.balance, replay.replayed) == (1040, True)
    with Session(engine) as session:
        assert count(session, LedgerEntry) == 1


def test_reusing_id_with_different_amount_fails(engine: Engine) -> None:
    request_id = str(uuid4())
    transact(engine, "deposit", 50, request_id=request_id)
    with pytest.raises(IdempotencyConflict):
        transact(engine, "deposit", 51, request_id=request_id)


def test_insufficient_funds_receipt_survives_later_deposit(engine: Engine) -> None:
    request_id = str(uuid4())
    with pytest.raises(InsufficientFunds):
        transact(engine, "withdraw", 1200, request_id=request_id)
    transact(engine, "deposit", 500)
    with pytest.raises(InsufficientFunds):
        transact(engine, "withdraw", 1200, request_id=request_id)

    with Session(engine) as session:
        receipt = session.get_one(RequestReceipt, request_id)
        assert (receipt.status, receipt.error_code) == ("error", "INSUFFICIENT_FUNDS")
        assert session.get_one(Account, "A1001").balance_minor == 1500
        assert count(session, LedgerEntry) == 1


def test_unknown_account_failure_is_saved_once(engine: Engine) -> None:
    request_id = str(uuid4())
    for _ in range(2):
        with pytest.raises(UnknownAccount):
            transact(engine, "deposit", 10, request_id=request_id, account="MISSING")
    with Session(engine) as session:
        assert session.get_one(RequestReceipt, request_id).error_code == "ACCOUNT_NOT_FOUND"
        assert count(session, LedgerEntry) == 0


@pytest.mark.parametrize("amount", [0, -1, 10**15 + 1, True, 1.1])
def test_invalid_amount_does_not_create_a_receipt(engine: Engine, amount: Any) -> None:
    with pytest.raises(InvalidAmount):
        transact(engine, "deposit", amount)
    with Session(engine) as session:
        assert count(session, RequestReceipt) == 0


def test_ledger_error_rolls_back_everything(engine: Engine) -> None:
    request_id = str(uuid4())
    with Session(engine) as session:

        def reject_ledger(current: Session, *_args: object) -> None:
            if any(isinstance(row, LedgerEntry) for row in current.new):
                raise RuntimeError("ledger unavailable")

        event.listen(session, "before_flush", reject_ledger)
        with pytest.raises(RuntimeError, match="ledger unavailable"):
            BankingService(session).transact(
                request_id=request_id, action="withdraw", account="A1001", amount=100
            )

    with Session(engine) as session:
        assert session.get_one(Account, "A1001").balance_minor == 1000
        assert session.get(RequestReceipt, request_id) is None
        assert count(session, LedgerEntry) == 0


def test_existing_operation_is_replayed_without_a_new_write(engine: Engine) -> None:
    request_id = str(uuid4())
    with Session(engine) as session:
        session.add(
            Operation(
                request_id=request_id,
                account_id="A1001",
                action="deposit",
                amount_minor=50,
                request_hash=request_hash("deposit", "A1001", 50),
                result_balance_minor=1050,
                status="success",
            )
        )
        session.commit()

    replay = transact(engine, "deposit", 50, request_id=request_id)
    assert (replay.balance, replay.replayed) == (1050, True)
    with Session(engine) as session:
        assert session.get_one(Account, "A1001").balance_minor == 1000
        assert count(session, RequestReceipt) == 0


def test_request_fingerprint_is_stable() -> None:
    assert request_hash("deposit", "A1001", 10) == (
        "f4b85f086816f66e5235c7dc79ffcb119fd362a778ae3e6789e8ba0c54f24947"
    )
