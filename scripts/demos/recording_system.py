"""Optional local rollback check, SSH logs and API durability demonstration."""

import subprocess
import sys
from time import sleep
from uuid import uuid4

import httpx2
from scripts.demos.recording_support import ROOT, DemoFailure, ensure, expect, heading


def logs(host: str) -> None:
    heading("BANKING A LOGS")
    result = subprocess.run(
        ["ssh", "-tt", host, "sudo journalctl -u banking-api -n 30 --no-pager -o cat"],
        check=False,
    )
    ensure(result.returncode == 0, "SSH log command failed")


def atomicity() -> None:
    heading("ATOMICITY: injected failure (local SQLite test)")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/unit/test_transactions.py::test_ledger_error_rolls_back_everything",
        ],
        cwd=ROOT,
        check=False,
    )
    ensure(result.returncode == 0, "Rollback test failed")
    print("PASS | Rolled back in SQLite (not a live YugabyteDB fault test)")


def durability(demo, *, backend: str, ssh_host: str) -> None:
    heading("DURABILITY: commit then restart Banking B")
    with httpx2.Client(base_url=backend, timeout=15) as client:
        path = f"/api/v1/accounts/{demo.account}/balance"
        before_response = client.get(path)
        expect(before_response, 200)
        before = before_response.json()["balance"]
        request_id = str(uuid4())
        payload = {
            "request_id": request_id,
            "action": "deposit",
            "account": demo.account,
            "amount": 1,
        }
        demo.record("request_sent", request_id=request_id, payload=payload, backend=backend)
        try:
            response = client.post("/api/v1/transactions", json=payload)
        except httpx2.RequestError as exc:
            raise DemoFailure(f"UNKNOWN financial outcome; check request_id={request_id}") from exc
        demo.record("response", request_id=request_id, status=response.status_code)
        ensure(
            response.status_code < 500,
            f"UNKNOWN financial outcome; check request_id={request_id}",
        )
        expect(response, 200)
        ensure(response.json()["balance"] == before + 1, "Unexpected deposit balance")

        print("Restarting Banking B API only (SSH/sudo may request a password)...")
        result = subprocess.run(
            ["ssh", "-tt", ssh_host, "sudo systemctl restart banking-api"], check=False
        )
        ensure(result.returncode == 0, "Restart failed")
        for _ in range(20):
            try:
                if client.get("/health/ready").status_code == 200:
                    break
            except httpx2.RequestError:
                pass
            sleep(1)
        else:
            raise DemoFailure("Banking B did not restart")
        final = client.get(path)
        expect(final, 200)
        ensure(final.json()["balance"] == before + 1, "Deposit was not durable")
        print(f"PASS | balance after restart: {before + 1}")
