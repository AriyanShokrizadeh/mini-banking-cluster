"""Simple command line entrypoint for VM4 demo runs."""

import argparse
import os
import sys

import httpx2
from scripts.demos.lab import (
    BACKEND_A,
    BACKEND_B,
    GATEWAY,
    account_for,
    mark_blocked,
    restore_balance,
)
from scripts.demos.recording_scenarios import Demo
from scripts.demos.recording_support import DemoFailure, heading
from scripts.demos.recording_system import atomicity, durability, logs

SCENARIOS = ("health", "basic", "idempotency", "errors", "concurrency", "atomicity")
WRITES = {"basic", "idempotency", "errors", "concurrency", "all", "durability"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=(*SCENARIOS, "all", "durability", "logs"))
    parser.add_argument(
        "--allow-restart",
        action="store_true",
        help="Restart Banking B",
    )
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()

    if args.scenario == "durability" and not args.allow_restart:
        parser.error("Durability requires --allow-restart")
    if not (2 <= args.count <= 20 and 1 <= args.workers <= args.count):
        parser.error("Require 2 <= count <= 20 and 1 <= workers <= count")

    server, backend_a, backend_b = GATEWAY, BACKEND_A, BACKEND_B
    if any(not url.startswith(("http://", "https://")) for url in (server, backend_a, backend_b)):
        parser.error("Demo server addresses must be HTTP(S) URLs")

    account = account_for(args.scenario)
    demo = Demo(server, account)
    commands = {
        "health": lambda: demo.health(backend_a, backend_b),
        "basic": demo.basic,
        "idempotency": demo.idempotency,
        "errors": demo.errors,
        "concurrency": lambda: demo.concurrency(count=args.count, workers=args.workers),
        "atomicity": atomicity,
        "logs": lambda: logs(os.getenv("DEMO_SSH_A", "ariyan@192.168.200.128")),
        "durability": lambda: durability(
            demo,
            backend=backend_b,
            ssh_host=os.getenv("DEMO_SSH_B", "ariyan@192.168.200.129"),
        ),
    }
    try:
        if args.scenario in WRITES:
            restore_balance(server, account)
            demo.start_report()
        for name in SCENARIOS if args.scenario == "all" else (args.scenario,):
            commands[name]()
        if args.scenario in WRITES:
            restore_balance(server, account)
        heading("DEMO COMPLETED")
        return 0
    except (DemoFailure, ValueError, KeyError, OSError, httpx2.HTTPError) as exc:
        if demo.report:
            mark_blocked(account, f"{args.scenario}: {type(exc).__name__}: {exc}")
        print(f"DEMO FAILED: {exc}", file=sys.stderr)
        if demo.report:
            print(f"Evidence: {demo.report}", file=sys.stderr)
        return 1
    finally:
        demo.close()


if __name__ == "__main__":
    raise SystemExit(main())
