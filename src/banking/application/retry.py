"""Retry serialization failures with a fresh transaction on each attempt."""

import logging
import random
from collections.abc import Callable
from time import sleep
from typing import TypeVar

from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

T = TypeVar("T")
logger = logging.getLogger("banking.retry")


def is_retryable(exc: BaseException) -> bool:
    if not isinstance(exc, DBAPIError):
        return False
    state = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
    if state in ("40001", "40P01"):
        return True
    if state == "23505":
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        return constraint == "request_receipts_pkey" or (
            constraint is None and "request_receipts.request_id" in str(exc.orig)
        )
    return False


def execute_transaction(
    engine: Engine,
    fn: Callable[[Session], T],
    *,
    attempts: int = 3,
    wait_max: float = 0.3,
) -> T:
    """Never retry uncertain network/commit failures or unrelated database errors."""
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    for attempt in range(attempts):
        try:
            with Session(engine) as session:
                return fn(session)
        except DBAPIError as exc:
            if attempt == attempts - 1 or not is_retryable(exc):
                raise
            logger.warning("transaction_retry", extra={"attempt_number": attempt + 1})
            sleep(random.uniform(0, min(0.02 * 2**attempt, wait_max)))
    raise AssertionError("unreachable")
