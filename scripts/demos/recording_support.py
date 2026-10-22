"""Small HTTP helper for recording demos; never retry an uncertain write."""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx2

ROOT = Path(__file__).resolve().parents[2]
TRANSACTIONS = "/api/v1/transactions"


class DemoFailure(Exception):
    """An expected demo check failed."""


def heading(text: str) -> None:
    print(f"\n===== {text} =====", flush=True)


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise DemoFailure(message)


def expect(response: httpx2.Response, status: int, code: str | None = None) -> None:
    ensure(response.status_code == status, f"Expected {status}, got {response.status_code}")
    if code:
        ensure(
            response.json().get("error", {}).get("code") == code,
            f"Expected error {code}",
        )


class DemoClient:
    def __init__(self, server: str, account: str) -> None:
        self.account = account
        self.client = httpx2.Client(base_url=server.rstrip("/"), timeout=15)
        self.report: Path | None = None

    def close(self) -> None:
        self.client.close()

    def start_report(self) -> None:
        folder = ROOT / "demo-results"
        folder.mkdir(mode=0o700, exist_ok=True)
        self.report = folder / f"demo-{uuid4().hex}.jsonl"
        self.report.touch(mode=0o600)
        print(f"Evidence: {self.report}")

    def record(self, event: str, **fields: object) -> None:
        if self.report:
            item = {
                "time": datetime.now(timezone.utc).isoformat(),
                "event": event,
                **fields,
            }
            with self.report.open("a", encoding="utf-8") as file:
                file.write(json.dumps(item, ensure_ascii=False) + "\n")

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict | None = None,
        content: bytes | None = None,
    ) -> httpx2.Response:
        write = method == "POST"
        request_id = payload.get("request_id") if payload else None
        if write:
            self.record("request_sent", request_id=request_id, payload=payload, path=path)
        try:
            response = self.client.request(
                method,
                path,
                json=payload,
                content=content,
                headers={"Content-Type": "application/json"} if content else None,
            )
        except httpx2.RequestError as exc:
            self.record("transport_error", request_id=request_id, error=type(exc).__name__)
            if write:
                raise DemoFailure(
                    f"UNKNOWN financial outcome; check request_id={request_id}"
                ) from exc
            raise DemoFailure(f"Could not read {path}: {type(exc).__name__}") from exc

        if write:
            self.record("response", request_id=request_id, status=response.status_code)
            if response.status_code >= 500:
                raise DemoFailure(
                    f"UNKNOWN financial outcome (HTTP {response.status_code}); "
                    f"check request_id={request_id}"
                )
        return response

    def balance(self) -> int:
        response = self.request("GET", f"/api/v1/accounts/{self.account}/balance")
        expect(response, 200)
        value = response.json()["balance"]
        ensure(type(value) is int, "Invalid balance")
        return value

    def transaction(
        self,
        action: str,
        amount: int,
        *,
        request_id: str | None = None,
        account: str | None = None,
    ) -> httpx2.Response:
        return self.request(
            "POST",
            TRANSACTIONS,
            payload={
                "request_id": request_id or str(uuid4()),
                "action": action,
                "account": account or self.account,
                "amount": amount,
            },
        )
