"""A ledger audit reports financial mismatches and pending receipts."""

from uuid import uuid4

from scripts.checks.audit_ledger import audit
from sqlalchemy import text
from sqlalchemy.engine import Engine


def test_audit_detects_balance_mismatch(engine: Engine) -> None:
    assert audit(engine)["passed"]

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE accounts SET balance_minor = 42 WHERE account_id = 'A1001'")
        )

    report = audit(engine)
    assert not report["passed"]
    assert report["checks"]["balance_mismatch"]["count"] == 1


def test_audit_detects_pending_receipt(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO request_receipts
                    (request_id, request_hash, account_id, action, amount_minor, status)
                VALUES (:id, 'hash', 'A1001', 'deposit', 1, 'pending')
            """),
            {"id": str(uuid4())},
        )

    assert audit(engine)["checks"]["incomplete_receipts"]["count"] == 1
