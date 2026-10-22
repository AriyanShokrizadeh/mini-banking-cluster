"""Opt-in YugabyteDB concurrency tests on a disposable, initialized database."""

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from banking.application.retry import execute_transaction
from banking.application.service import BankingService
from banking.domain.exceptions import InsufficientFunds

pytestmark = pytest.mark.cluster


@pytest.fixture
def test_account() -> Iterator[tuple[Engine, str]]:
    url = os.getenv("BANKING_TEST_DATABASE_URL")
    if not url or os.getenv("BANKING_TEST_ENABLE_WRITES") != "1":
        pytest.skip("Set BANKING_TEST_DATABASE_URL and BANKING_TEST_ENABLE_WRITES=1")

    parsed = make_url(url)
    name = (parsed.database or "").lower()
    if parsed.drivername != "postgresql+psycopg" or not (
        name.startswith("test_") or name.endswith("_test")
    ):
        pytest.fail("Writes require a disposable PostgreSQL *_test database")

    engine = create_engine(url, isolation_level="SERIALIZABLE", pool_pre_ping=True)
    account = f"TEST_{uuid4().hex[:20]}"
    try:
        with engine.begin() as connection:
            connection.execute(
                text("""
                    INSERT INTO accounts (account_id, opening_balance_minor, balance_minor)
                    VALUES (:account, 1000, 1000)
                """),
                {"account": account},
            )
        yield engine, account
    finally:
        try:
            with engine.begin() as connection:
                for table in (
                    "ledger_entries",
                    "operations",
                    "request_receipts",
                    "accounts",
                ):
                    connection.execute(
                        text(f"DELETE FROM {table} WHERE account_id = :account"),
                        {"account": account},
                    )
        finally:
            engine.dispose()


def test_duplicate_concurrent_deposits_are_applied_once(
    test_account: tuple[Engine, str],
) -> None:
    engine, account = test_account
    request_id = str(uuid4())

    def deposit(_: int) -> int:
        def operation(session: Session):
            return BankingService(session).transact(
                request_id=request_id, action="deposit", account=account, amount=30
            )

        return execute_transaction(engine, operation, attempts=8, wait_max=0.4).balance

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(deposit, range(4))) == [1030] * 4

    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT balance_minor FROM accounts WHERE account_id = :account"),
                {"account": account},
            )
            == 1030
        )
        assert (
            connection.scalar(
                text("SELECT COUNT(*) FROM ledger_entries WHERE request_id = :id"),
                {"id": request_id},
            )
            == 1
        )


def test_concurrent_withdrawals_never_overdraw(
    test_account: tuple[Engine, str],
) -> None:
    engine, account = test_account

    def withdraw(_: int) -> bool:
        request_id = str(uuid4())

        def operation(session: Session):
            return BankingService(session).transact(
                request_id=request_id,
                action="withdraw",
                account=account,
                amount=100,
            )

        try:
            execute_transaction(engine, operation, attempts=12, wait_max=0.5)
            return True
        except InsufficientFunds:
            return False

    with ThreadPoolExecutor(max_workers=6) as pool:
        successes = sum(pool.map(withdraw, range(20)))
    assert successes == 10

    with engine.connect() as connection:
        for table, column, expected in (
            ("accounts", "balance_minor", 0),
            ("ledger_entries", "COUNT(*)", 10),
            ("request_receipts", "COUNT(*)", 20),
        ):
            assert (
                connection.scalar(
                    text(f"SELECT {column} FROM {table} WHERE account_id = :account"),
                    {"account": account},
                )
                == expected
            ), table
