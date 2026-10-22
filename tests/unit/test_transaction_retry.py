"""Only known, safely retryable transaction errors get fresh sessions."""

from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from banking.application.retry import execute_transaction, is_retryable


class DatabaseFailure(Exception):
    def __init__(self, state: str, constraint: str | None = None):
        super().__init__(state)
        self.sqlstate = state
        self.diag = SimpleNamespace(constraint_name=constraint)


def failure(state: str, constraint: str | None = None) -> DBAPIError:
    return DBAPIError("SQL", {}, DatabaseFailure(state, constraint))


def test_serialization_failure_restarts_with_new_session(engine: Engine) -> None:
    sessions = []

    def operation(session: Session) -> str:
        sessions.append(session)
        if len(sessions) == 1:
            raise failure("40001")
        return "ok"

    assert execute_transaction(engine, operation, attempts=2, wait_max=0) == "ok"
    assert len(sessions) == 2 and sessions[0] is not sessions[1]


@pytest.mark.parametrize(
    ("state", "constraint", "retryable"),
    [
        ("40001", None, True),
        ("40P01", None, True),
        ("23505", "request_receipts_pkey", True),
        ("23505", "other_table_pkey", False),
        ("23503", "ledger_entries_request_id_fkey", False),
        ("08006", None, False),
    ],
)
def test_only_safe_database_errors_are_retryable(state, constraint, retryable) -> None:
    assert is_retryable(failure(state, constraint)) is retryable


def test_non_database_exception_does_not_retry(engine: Engine) -> None:
    calls = []

    def fail(_session: Session) -> None:
        calls.append(1)
        raise ValueError("business failure")

    with pytest.raises(ValueError):
        execute_transaction(engine, fail, attempts=3, wait_max=0)
    assert len(calls) == 1
