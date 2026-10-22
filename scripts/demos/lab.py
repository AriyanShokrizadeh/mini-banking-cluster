"""Reusable demo accounts and balance restoration through audited transactions."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx2
from scripts.demos.recording_support import ROOT, DemoFailure, ensure

from client.banking_client import BankingClient

GATEWAY = os.getenv("DEMO_SERVER", "http://192.168.200.130:8080")
BACKEND_A = os.getenv("DEMO_BACKEND_A", "http://192.168.200.128:8000")
BACKEND_B = os.getenv("DEMO_BACKEND_B", "http://192.168.200.129:8000")
BASELINE = 1000
ACCOUNTS = {
    "basic": "DEMO_LAB_BASIC",
    "errors": "DEMO_LAB_BASIC",
    "idempotency": "DEMO_LAB_BASIC",
    "concurrency": "DEMO_LAB_CONCURRENCY",
    "durability": "DEMO_LAB_DURABILITY",
    "failover": "DEMO_LAB_FAILOVER",
    "partition": "DEMO_LAB_PARTITION",
}


def account_for(scenario: str) -> str:
    return ACCOUNTS.get(scenario, ACCOUNTS["basic"])


def balance(server: str, account: str) -> int:
    try:
        with BankingClient(server, timeout=8, retries=0) as client:
            return int(client.balance(account)["balance"])
    except httpx2.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise DemoFailure(
                f"Missing {account}. Run the one-time lab setup on VM1 (see demos/README.md)."
            ) from exc
        raise


def block_path(account: str) -> Path:
    ensure(account in ACCOUNTS.values(), "Not a fixed lab account")
    return ROOT / "demo-results" / f"BLOCKED-{account}.json"


def assert_unblocked(account: str) -> None:
    path = block_path(account)
    if path.exists():
        raise DemoFailure(
            f"{account} has unresolved outcomes ({path}). Audit IDs and then "
            "run 'run.sh reconcile <account>' before reuse."
        )


def mark_blocked(account: str, reason: str) -> None:
    path = block_path(account)
    path.parent.mkdir(mode=0o700, exist_ok=True)
    payload = {"account": account, "reason": reason, "time": datetime.now(timezone.utc).isoformat()}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    print(f"BLOCKED | {account}. Evidence: {path}", flush=True)


def restore_balance(server: str, account: str, target: int = BASELINE) -> None:
    """Compensate to the target without deleting receipts or ledger entries."""
    ensure(account in ACCOUNTS.values(), "Only the fixed lab account pool can be reset")
    assert_unblocked(account)
    current = balance(server, account)
    if current == target:
        print(f"BASELINE | {account} = {target}", flush=True)
        return

    action = "deposit" if current < target else "withdraw"
    request_id = uuid4()
    print(f"RESTORE | {account}: {current} -> {target}, request_id={request_id}", flush=True)
    try:
        with BankingClient(server, timeout=15, retries=0) as client:
            client.transact(action, account, abs(target - current), request_id=request_id)
    except httpx2.HTTPError as exc:
        mark_blocked(account, f"Unknown compensating transaction: {request_id}")
        raise DemoFailure(
            f"UNKNOWN reset outcome for {account}, request_id={request_id}; "
            "do NOT repeat until this request is reconciled"
        ) from exc
    ensure(balance(server, account) == target, "Balance did not reach expected baseline")


def report_path(kind: str) -> Path:
    folder = ROOT / "demo-results"
    folder.mkdir(mode=0o700, exist_ok=True)
    return folder / f"{kind}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex[:8]}.json"


def check_health(server: str = GATEWAY) -> None:
    try:
        with BankingClient(server, timeout=8) as client:
            ensure(client.check("ready")["status"] == "ready", "Gateway not ready")
    except httpx2.HTTPError as exc:
        raise DemoFailure(f"Gateway not ready: {type(exc).__name__}") from exc
