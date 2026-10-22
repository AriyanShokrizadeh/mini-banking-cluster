"""Probe one isolated YSQL endpoint, using an expendable test database only.

Run once before partition (expect available), during isolation (expect blocked),
and after recovery (expect available). No financial account is modified.
"""

import argparse
import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, DBAPIError


def check_url(value: str) -> None:
    """Reject production and multi-host URLs: this test must target one node."""
    url = make_url(value)

    if url.drivername != "postgresql+psycopg":
        raise ValueError("Only postgresql+psycopg:// URLs are allowed")
    database = (url.database or "").lower()
    if not (database.endswith("_test") or database.startswith("test_")):
        raise ValueError("Use a disposable *_test database, never banking")

    host_options = url.normalized_query.get("host", ())
    if len(host_options) > 1 or "," in (url.host or ""):
        raise ValueError("Use ONE YSQL host to probe the minority node")
    if len(host_options) == 1 and "," in host_options[0]:
        raise ValueError("Use ONE YSQL host to probe the minority node")
    if not (url.host or host_options):
        raise ValueError("A single explicit YugabyteDB node IP is required")


def write_probe(url: str) -> None:
    engine = create_engine(
        url,
        isolation_level="SERIALIZABLE",
        pool_pre_ping=False,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=5000"},
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                text("""
                    INSERT INTO health_probes (instance_name, sequence)
                    VALUES ('phase7-quorum', 1)
                    ON CONFLICT (instance_name)
                    DO UPDATE SET sequence = health_probes.sequence + 1
                """)
            )
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect", required=True, choices=["available", "blocked"])
    args = parser.parse_args()
    url = os.getenv("BANKING_TEST_DATABASE_URL", "")
    if os.getenv("BANKING_TEST_ENABLE_WRITES") != "1":
        parser.error("Set BANKING_TEST_ENABLE_WRITES=1 for the disposable test database")
    if not url:
        parser.error("BANKING_TEST_DATABASE_URL is required")
    try:
        check_url(url)
    except (ValueError, AttributeError, ArgumentError) as exc:
        parser.error(str(exc))

    try:
        write_probe(url)
        acknowledged = True
    except DBAPIError as exc:
        state = getattr(exc.orig, "sqlstate", None)
        if state in {"28000", "28P01", "3D000", "42P01", "42501"}:
            print(f"Invalid probe setup (SQLSTATE {state})", file=sys.stderr)
            return 2
        acknowledged = False
        print(f"YSQL rejected or could not confirm the write: {type(exc).__name__}")

    matched = acknowledged == (args.expect == "available")
    print(f"Expected={args.expect} acknowledged_commit={acknowledged} matched={matched}")
    print("A timeout is not proof of rollback or quorum safety; audit after recovery.")
    return 0 if matched else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Probe error: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
