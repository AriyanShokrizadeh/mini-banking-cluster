"""Prepare, reset, and reconcile the reusable lab accounts."""

from __future__ import annotations

import sys
from uuid import uuid4

from scripts.demos.cluster_demo import VM1, remote
from scripts.demos.lab import ACCOUNTS, GATEWAY, block_path, restore_balance
from scripts.demos.recording_support import DemoFailure

from client.banking_client import BankingClient

RUNNER = (
    "sudo systemd-run --wait --collect --pipe -p User=banking -p Group=banking "
    "-p WorkingDirectory=/opt/mini-banking-releases "
    "-p EnvironmentFile=/etc/mini-banking/banking.env "
    "/opt/mini-banking-releases/.venv/bin/python -m "
)


def confirm(message: str, phrase: str) -> None:
    if input(message).strip() != phrase:
        raise DemoFailure("Cancelled")


def reconcile(account: str) -> None:
    if account not in ACCOUNTS.values():
        raise DemoFailure("Use run.sh reconcile DEMO_LAB_<ACCOUNT>")
    path = block_path(account)
    if not path.exists():
        print(f"{account} is already unblocked")
        return

    print(path.read_text())
    confirm(
        "Have you reconciled EVERY request ID against the database audit? Type RECONCILED: ",
        "RECONCILED",
    )
    path.unlink()
    print(f"Unblocked {account}; no database rows were changed")


def reset_core() -> None:
    confirm("Restore A1001=1000 and A1002=800? Type RESET-CORE: ", "RESET-CORE")
    for account, target in (("A1001", 1000), ("A1002", 800)):
        with BankingClient(GATEWAY, timeout=15, retries=0) as client:
            before = int(client.balance(account)["balance"])
            if before == target:
                continue
            action = "deposit" if before < target else "withdraw"
            request_id = uuid4()
            print(f"Core reconciliation {account}: {before} -> {target} request_id={request_id}")
            client.transact(action, account, abs(target - before), request_id=request_id)
            if int(client.balance(account)["balance"]) != target:
                raise DemoFailure(f"Core restoration failed: {account}")


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    args = sys.argv[2:]
    if action == "prepare" and not args:
        from scripts.demos.deploy_tools import install

        install(VM1)
        remote(VM1, RUNNER + "scripts.setup.prepare_lab")
    elif action == "reset" and not args:
        for account in sorted(set(ACCOUNTS.values())):
            restore_balance(GATEWAY, account)
    elif action == "cleanup" and not args:
        remote(VM1, RUNNER + "scripts.setup.cleanup_legacy_demo")
    elif action == "cleanup-execute" and not args:
        confirm("Type DELETE-OLD-DEMOS to remove retired records: ", "DELETE-OLD-DEMOS")
        remote(
            VM1,
            RUNNER + "scripts.setup.cleanup_legacy_demo --execute --confirm DELETE-OLD-DEMOS",
        )
    elif action == "reconcile" and len(args) == 1:
        reconcile(args[0])
    elif action == "reset-core" and not args:
        reset_core()
    else:
        print("Usage: run.sh {prepare|reset|cleanup|cleanup-execute|reset-core|reconcile ACCOUNT}")
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"LAB ADMIN ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
