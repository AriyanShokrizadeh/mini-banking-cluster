"""Read-only integrity audit of the banking database after fault tests."""

import json
import sys
from typing import TypedDict

from sqlalchemy import text
from sqlalchemy.engine import Engine

from banking.config import get_settings
from banking.infrastructure.database import make_engine


class CheckResult(TypedDict):
    count: int
    sample_ids: list[str]


class AuditReport(TypedDict):
    passed: bool
    accounts: int
    operations: int
    checks: dict[str, CheckResult]


CHECKS = {
    "balance_mismatch": """
        SELECT a.account_id AS identifier
        FROM accounts AS a LEFT JOIN (
            SELECT account_id, SUM(delta_minor) AS delta
            FROM ledger_entries GROUP BY account_id
        ) AS l ON l.account_id = a.account_id
        WHERE a.balance_minor <> a.opening_balance_minor + COALESCE(l.delta, 0)
    """,
    "ledger_mismatch": """
        SELECT l.request_id AS identifier
        FROM ledger_entries AS l JOIN operations AS o ON o.request_id = l.request_id
        WHERE l.account_id <> o.account_id
           OR l.balance_after_minor <> o.result_balance_minor
           OR l.delta_minor <> CASE WHEN o.action = 'deposit'
                                   THEN o.amount_minor ELSE -o.amount_minor END
    """,
    "missing_success_records": """
        SELECT r.request_id AS identifier
        FROM request_receipts AS r
        LEFT JOIN operations AS o ON o.request_id = r.request_id
        LEFT JOIN ledger_entries AS l ON l.request_id = r.request_id
        WHERE r.status = 'success' AND (
            o.request_id IS NULL OR l.request_id IS NULL
            OR o.result_balance_minor <> r.result_balance_minor
        )
    """,
    "invalid_failed_receipts": """
        SELECT r.request_id AS identifier
        FROM request_receipts AS r
        LEFT JOIN operations AS o ON o.request_id = r.request_id
        WHERE r.status = 'error' AND o.request_id IS NOT NULL
    """,
    "incomplete_receipts": """
        SELECT request_id AS identifier
        FROM request_receipts WHERE status = 'pending'
    """,
}


def audit(engine: Engine) -> AuditReport:
    """Run the integrity checks against a quiet database."""
    failures: dict[str, CheckResult] = {}
    with engine.connect() as connection:
        for name, statement in CHECKS.items():
            rows = connection.execute(text(statement)).scalars().all()
            failures[name] = {"count": len(rows), "sample_ids": [str(row) for row in rows[:10]]}
        accounts = connection.scalar(text("SELECT count(*) FROM accounts")) or 0
        operations = connection.scalar(text("SELECT count(*) FROM operations")) or 0
    return {
        "passed": all(item["count"] == 0 for item in failures.values()),
        "accounts": accounts,
        "operations": operations,
        "checks": failures,
    }


def main() -> int:
    engine = make_engine(get_settings())
    try:
        result = audit(engine)
    except Exception as exc:
        print(f"Audit unavailable: {type(exc).__name__}", file=sys.stderr)
        return 2
    finally:
        engine.dispose()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
