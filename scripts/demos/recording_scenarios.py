"""Core recording scenarios: each method demonstrates one banking requirement."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx2
from scripts.demos.recording_support import (
    TRANSACTIONS,
    DemoClient,
    DemoFailure,
    ensure,
    expect,
    heading,
)


class Demo(DemoClient):
    def health(self, a_url: str, b_url: str) -> None:
        heading("HEALTH: gateway, Banking A, Banking B")
        for name, url in (
            ("Gateway", str(self.client.base_url)),
            ("Banking A", a_url),
            ("Banking B", b_url),
        ):
            try:
                with httpx2.Client(base_url=url, timeout=6) as client:
                    for check in ("live", "db", "ready"):
                        expect(client.get(f"/health/{check}"), 200)
            except httpx2.RequestError as exc:
                raise DemoFailure(f"{name}: {type(exc).__name__}") from exc
            print(f"PASS | {name}")

    def basic(self) -> None:
        heading("BASIC: balance, deposit, withdraw")
        before = self.balance()
        expect(self.transaction("deposit", 20), 200)
        after_deposit = self.balance()
        ensure(after_deposit == before + 20, "Incorrect deposit balance")
        expect(self.transaction("withdraw", 10), 200)
        after_withdrawal = self.balance()
        ensure(after_withdrawal == after_deposit - 10, "Incorrect withdrawal balance")
        print(f"PASS | {before} -> {after_deposit} -> {after_withdrawal}")

    def idempotency(self) -> None:
        heading("IDEMPOTENCY: same ID, one deposit")
        before, request_id = self.balance(), str(uuid4())
        first = self.transaction("deposit", 5, request_id=request_id)
        again = self.transaction("deposit", 5, request_id=request_id)
        expect(first, 200)
        expect(again, 200)
        ensure(first.json()["replayed"] is False, "First request was replayed")
        ensure(again.json()["replayed"] is True, "Request was not replayed")
        ensure(self.balance() == before + 5, "Duplicate deposit")
        print(f"PASS | request_id={request_id}")

    def errors(self) -> None:
        heading("ERRORS: invalid requests")
        before = self.balance()
        ensure(before < 10**15, "Account balance too high for insufficient-funds demo")

        def body(**changes: object) -> dict:
            return {
                "request_id": str(uuid4()),
                "action": "deposit",
                "account": self.account,
                "amount": 1,
                **changes,
            }

        missing = body()
        del missing["amount"]
        cases = [
            (
                "Unknown account",
                body(account=f"DEMO_MISSING_{uuid4().hex[:10]}"),
                404,
                "ACCOUNT_NOT_FOUND",
            ),
            (
                "Insufficient funds",
                body(action="withdraw", amount=before + 1),
                409,
                "INSUFFICIENT_FUNDS",
            ),
            ("Zero amount", body(amount=0), 422, "INVALID_AMOUNT"),
            ("Negative amount", body(amount=-1), 422, "INVALID_AMOUNT"),
            ("Non-numeric", body(amount="invalid"), 422, "INVALID_AMOUNT"),
            ("Unsupported action", body(action="transfer"), 422, "UNSUPPORTED_ACTION"),
            ("Missing field", missing, 422, "MISSING_FIELD"),
        ]
        for name, payload, status, code in cases:
            expect(self.request("POST", TRANSACTIONS, payload=payload), status, code)
            print(f"PASS | {name}: {status} {code}")
        expect(
            self.request("POST", TRANSACTIONS, content=b'{"action":'),
            400,
            "MALFORMED_REQUEST",
        )
        print("PASS | Malformed JSON")
        ensure(self.balance() == before, "Rejected requests changed balance")

    def concurrency(self, *, count: int, workers: int) -> None:
        heading(f"ISOLATION: {count} concurrent withdrawals")
        before = self.balance()
        ensure(before >= 2, "Demo account must have balance >= 2")
        amount = before // 2 + 1
        requests = [
            {
                "request_id": str(uuid4()),
                "action": "withdraw",
                "account": self.account,
                "amount": amount,
            }
            for _ in range(count)
        ]

        def send(payload: dict) -> tuple[str, int, str]:
            response = self.request("POST", TRANSACTIONS, payload=payload)
            code = response.json().get("error", {}).get("code", "OK")
            return payload["request_id"], response.status_code, code

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(send, requests))
        for request_id, status, code in results:
            print(f"  {request_id[:8]} | {status} | {code}")
        approved = sum(status == 200 for _, status, _ in results)
        rejected = sum(
            status == 409 and code == "INSUFFICIENT_FUNDS" for _, status, code in results
        )
        ensure(approved == 1 and rejected == count - 1, "Invalid concurrent results")
        ensure(self.balance() == before - amount, "Incorrect concurrent balance")
        print(f"PASS | 1 approved, {rejected} rejected")
