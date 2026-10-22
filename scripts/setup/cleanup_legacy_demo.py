"""Preview / remove ONLY known, retired simulated accounts and linked history.

Never edits A1001/A1002 or the reusable DEMO_LAB_* pool. Execute only after
stopping demo workloads. A private JSON snapshot is fsynced before deletion.
"""

import argparse
import json
import os
from datetime import datetime, timezone
from itertools import chain
from pathlib import Path
from uuid import uuid4

from scripts.setup.prepare_lab import LAB_ACCOUNTS
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from banking.config import get_settings
from banking.infrastructure.database import make_engine
from banking.infrastructure.models import Account, LedgerEntry, Operation, RequestReceipt

BACKUP_DIR = Path("/var/tmp/mini-banking-demo-backups")

RETIRED = (
    "DEMO_VIDEO_20261022_01",
    "DEMO_CONCURRENCY_01",
    "DEMO_DURABILITY_01",
    "DEMO_FAILOVER_01",
    "DEMO_FAILOVER_02",
    "DEMO_FAILOVER_03",
    "DEMO_PARTITION_01",
    "DEMO_PARTITION_02",
)


def as_dict(records):
    return [
        {
            column.name: (value.isoformat() if isinstance(value, datetime) else value)
            for column in type(record).__table__.columns
            if (value := getattr(record, column.name)) is not None
        }
        for record in records
    ]


def check_history(accounts, operations, ledger, receipts) -> None:
    names = {account.account_id for account in accounts}
    for account in accounts:
        delta = sum(entry.delta_minor for entry in ledger if entry.account_id == account.account_id)
        if account.balance_minor != account.opening_balance_minor + delta:
            raise RuntimeError(f"Ledger mismatch: {account.account_id}; refusing deletion")
    if any(receipt.status == "pending" for receipt in receipts):
        raise RuntimeError("Pending receipts exist; refusing deletion")
    if {op.request_id for op in operations} != {entry.request_id for entry in ledger}:
        raise RuntimeError("Operation/ledger mismatch; refusing deletion")
    if any(row.account_id not in names for row in chain(ledger, operations, receipts)):
        raise RuntimeError("Unexpected account ownership")


def save_snapshot(accounts, operations, ledger, receipts) -> Path:
    BACKUP_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    if BACKUP_DIR.is_symlink():
        raise RuntimeError("Backup directory must not be a symlink")
    path = BACKUP_DIR / f"retired-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex[:8]}.json"
    data = {
        "accounts": as_dict(accounts),
        "operations": as_dict(operations),
        "ledger_entries": as_dict(ledger),
        "request_receipts": as_dict(receipts),
    }
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def run(engine, *, execute: bool) -> None:
    with Session(engine) as session, session.begin():
        accounts = session.scalars(
            select(Account).where(Account.account_id.in_(RETIRED)).with_for_update()
        ).all()
        names = sorted(item.account_id for item in accounts)
        print(f"Retired accounts eligible for cleanup: {names}")
        other_demo = session.scalars(
            select(Account.account_id).where(Account.account_id.like("DEMO_%"))
        ).all()
        extra = sorted(set(other_demo) - set(names) - set(LAB_ACCOUNTS))
        if extra:
            print(f"Other DEMO_ accounts NOT touched: {extra}")
        if not names:
            print("Nothing to remove")
            return

        receipts = session.scalars(
            select(RequestReceipt).where(RequestReceipt.account_id.in_(names))
        ).all()
        operations = session.scalars(select(Operation).where(Operation.account_id.in_(names))).all()
        ledger = session.scalars(select(LedgerEntry).where(LedgerEntry.account_id.in_(names))).all()
        check_history(accounts, operations, ledger, receipts)
        print(
            f"Rows: {len(accounts)} accounts / {len(operations)} operations / "
            f"{len(ledger)} ledger entries / {len(receipts)} receipts"
        )
        if not execute:
            print("DRY RUN ONLY. No rows deleted.")
            return

        backup = save_snapshot(accounts, operations, ledger, receipts)
        print(f"SNAPSHOT SAVED: {backup}")
        # Delete children before accounts to satisfy foreign keys.
        session.execute(delete(LedgerEntry).where(LedgerEntry.account_id.in_(names)))
        session.execute(delete(Operation).where(Operation.account_id.in_(names)))
        session.execute(delete(RequestReceipt).where(RequestReceipt.account_id.in_(names)))
        session.execute(delete(Account).where(Account.account_id.in_(names)))
        print(f"Deleted {len(names)} retired DEMO accounts and associated history")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    if args.execute and args.confirm != "DELETE-OLD-DEMOS":
        parser.error("--execute requires --confirm DELETE-OLD-DEMOS")
    engine = make_engine(get_settings())
    try:
        run(engine, execute=args.execute)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
