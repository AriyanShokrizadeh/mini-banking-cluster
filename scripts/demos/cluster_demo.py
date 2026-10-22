"""One-command orchestrator for fault demonstrations (VM4 only).

Requires SSH and scoped sudo on the lab nodes. All faults are bounded and restored.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from time import monotonic, sleep
from typing import Any

import httpx2
from scripts.demos import failover_demo, partition_demo
from scripts.demos.lab import (
    BACKEND_A,
    BACKEND_B,
    GATEWAY,
    account_for,
    balance,
    check_health,
    mark_blocked,
    report_path,
    restore_balance,
)
from scripts.demos.recording_support import DemoFailure, ensure, heading

from client.banking_client import BankingClient

VM1 = os.getenv("DEMO_SSH_A", "ariyan@192.168.200.128")
VM2 = os.getenv("DEMO_SSH_B", "ariyan@192.168.200.129")
FAULT = "/opt/mini-banking-releases/scripts/fault/network_partition.py"
PROBE = "/opt/mini-banking-releases/scripts/fault/quorum_probe.py"
PYTHON = "/opt/mini-banking-releases/.venv/bin/python"


def remote(host: str, command: str, *, allow_failure: bool = False) -> int:
    print(f"REMOTE | {host} | {command}", flush=True)
    result = subprocess.run(["ssh", "-tt", "-o", "ConnectTimeout=8", host, command], check=False)
    if result.returncode and not allow_failure:
        raise DemoFailure(f"Remote command failed on {host}: {result.returncode}")
    return result.returncode


def wait_backend(instance: str, *, timeout: float = 60) -> None:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        try:
            with BankingClient(GATEWAY, timeout=4, retries=0) as client:
                if client.check("live").get("instance") == instance:
                    print(f"PASS | Gateway routing: {instance}", flush=True)
                    return
        except httpx2.HTTPError:
            pass
        sleep(1)
    raise DemoFailure(f"Gateway did not route to {instance}")


def verify_all_ready(*, timeout: float = 90) -> None:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        try:
            for url in (BACKEND_A, BACKEND_B, GATEWAY):
                check_health(url)
            print("PASS | All three endpoints ready", flush=True)
            return
        except (DemoFailure, httpx2.HTTPError):
            sleep(2)
    raise DemoFailure("Cluster did not recover to readiness")


def fault_status() -> int:
    return remote(VM1, f"sudo python3 {FAULT} status")


def partition_restore() -> None:
    remote(VM1, f"sudo python3 {FAULT} restore", allow_failure=False)


def quorum(host: str, address: str, expectation: str) -> None:
    command = (
        f"sudo timeout 20s env BANKING_TEST_ENABLE_WRITES=1 "
        f"BANKING_TEST_DATABASE_URL=postgresql+psycopg://yugabyte@{address}:5433/banking_test "
        f"{PYTHON} {PROBE} --expect {expectation}"
    )
    remote(host, command)


def save_report(name: str, payload: dict[str, Any]) -> None:
    dest = report_path(name)
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    dest.chmod(0o600)
    print(f"REPORT | {dest}", flush=True)


def quorum_sequence() -> None:
    """Display read-only evidence from the disposable database on VM2."""
    command = (
        "/opt/yugabyte/current/bin/ysqlsh -X -A -t "
        "-h 192.168.200.129 -p 5433 -U yugabyte -d banking_test -w "
        "-v ON_ERROR_STOP=1 -c "
        '"SELECT sequence FROM public.health_probes '
        "WHERE instance_name = 'phase7-quorum';\""
    )
    if remote(VM2, command, allow_failure=True) != 0:
        print("WARN | Could not read quorum sequence; check it independently", flush=True)


def finalize_scenario(
    name: str,
    account: str,
    result: dict[str, Any],
    passed: bool,
    restore: Callable[[], None],
) -> bool:
    try:
        restore()
    except Exception as exc:
        result["restoration_error"] = str(exc)
        print(f"RESTORE ERROR: {exc}", file=sys.stderr)

    if passed and "restoration_error" not in result:
        try:
            restore_balance(GATEWAY, account)
            result["restored_to_baseline"] = True
        except Exception as exc:
            result["balance_reset_error"] = str(exc)
            print(f"RESET ERROR: {exc}", file=sys.stderr)

    errors = ("restoration_error", "balance_reset_error")
    if result.get("request_ids") and (not passed or any(key in result for key in errors)):
        mark_blocked(account, f"{name.title()} interrupted: reconcile report request IDs")
    save_report(name, result)
    return passed and not any(key in result for key in errors)


def failover() -> bool:
    account = account_for("failover")
    restore_balance(GATEWAY, account)
    verify_all_ready()
    wait_backend("banking-a")
    heading("FAILOVER: stop primary while depositing")
    result: dict[str, Any] = {"scenario": "failover", "account": account, "completed": False}
    passed = False
    try:

        def progress(number: int) -> None:
            if number == 3:
                remote(VM1, "sudo systemctl stop banking-api")
                wait_backend("banking-b")

        report = failover_demo.run_demo(
            GATEWAY,
            account,
            count=20,
            amount=1,
            interval=0.6,
            retries=3,
            workers=1,
            on_progress=progress,
            before_reconcile=lambda: wait_backend("banking-b"),
            on_begin=lambda ids: result.update(request_ids=ids),
        )
        result.update(report)
        result["completed"] = True
        passed = bool(report["passed"])
    except Exception as exc:
        result["error"] = str(exc)
        raise
    finally:

        def restore_service() -> None:
            remote(VM1, "sudo systemctl start banking-api")
            verify_all_ready()

        final_passed = finalize_scenario("failover", account, result, passed, restore_service)
    return final_passed


def partition() -> bool:
    account = account_for("partition")
    restore_balance(GATEWAY, account)
    verify_all_ready()
    heading("PARTITION: isolate VM1 from VM2/VM3")
    state = {"applied": False}
    result: dict[str, Any] = {"scenario": "partition", "account": account, "completed": False}
    passed = False
    quorum_sequence()
    try:
        fault_status()

        def progress(number: int) -> None:
            if number != 5:
                return
            deadline = monotonic() + 35
            while monotonic() < deadline:
                try:
                    if balance(GATEWAY, account) >= 1003:
                        break
                except httpx2.HTTPError:
                    pass
                sleep(0.5)
            else:
                raise DemoFailure("3 committed deposits not seen; no partition applied")

            remote(
                VM1,
                f"sudo python3 {FAULT} apply --self-ip 192.168.200.128 "
                "--gateway-ip 192.168.200.130 --peer 192.168.200.129 "
                "--peer 192.168.200.132 --duration 180 --acknowledge-disruption",
            )
            state["applied"] = True
            remote(VM1, "systemctl is-active --quiet mini-banking-fault-restore.timer")
            print("===== MINORITY QUORUM =====", flush=True)
            remote(VM1, "sudo nft list table inet mini_banking_fault >/dev/null")
            quorum(VM1, "192.168.200.128", "blocked")
            print("===== MAJORITY QUORUM =====", flush=True)
            quorum(VM2, "192.168.200.129", "available")
            remote(VM1, "sudo nft list table inet mini_banking_fault >/dev/null")
            result["quorum_probe_results"] = "both matched during the active fault"

        def recovered() -> None:
            if not state["applied"]:
                raise DemoFailure("Partition was never applied")
            partition_restore()
            verify_all_ready()

        report = partition_demo.run_demo(
            GATEWAY,
            account,
            count=20,
            amount=1,
            workers=1,
            interval=0.5,
            recovery_wait=0,
            timeout=5,
            on_progress=progress,
            before_reconcile=recovered,
            on_begin=lambda ids: result.update(request_ids=ids),
        )
        result.update(report)
        result["completed"] = True
        passed = bool(report["financial_check_passed"])
    except Exception as exc:
        result["error"] = str(exc)
        raise
    finally:

        def restore_network() -> None:
            partition_restore()
            verify_all_ready()
            quorum_sequence()

        final_passed = finalize_scenario("partition", account, result, passed, restore_network)
    return final_passed


def main() -> int:
    name = sys.argv[1] if len(sys.argv) == 2 else ""
    if name not in {"failover", "partition"}:
        print("Usage: run.sh {failover|partition}", file=sys.stderr)
        return 2
    ensure(
        sys.stdin.isatty(),
        "Fault tests require an interactive terminal with VMware console recovery",
    )
    print(f"This will disrupt the LAB cluster for scenario {name}.")
    if input("Type RUN to proceed: ").strip() != "RUN":
        print("Cancelled")
        return 2
    try:
        return 0 if (failover() if name == "failover" else partition()) else 1
    except (DemoFailure, httpx2.HTTPError, OSError, ValueError) as exc:
        print(f"DEMO FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
