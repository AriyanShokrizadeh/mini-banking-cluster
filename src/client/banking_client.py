"""Synchronous HTTP banking client with safe, opt-in retries."""

import random
from time import sleep
from typing import Any, Literal
from uuid import UUID, uuid4

import httpx2

BankingAction = Literal["deposit", "withdraw"]
HealthEndpoint = Literal["live", "ready", "db"]


class BankingClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 5.0,
        transport: httpx2.BaseTransport | None = None,
        retries: int = 0,
    ) -> None:
        if not 0 <= retries <= 10:
            raise ValueError("retries must be between 0 and 10")
        self.retries = retries
        self.http = httpx2.Client(
            base_url=base_url.rstrip("/"), timeout=timeout, transport=transport
        )

    def __enter__(self) -> "BankingClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.http.close()

    def _get(self, path: str) -> dict[str, Any]:
        response = self.http.get(path)
        response.raise_for_status()
        return response.json()

    def check(self, endpoint: HealthEndpoint = "live") -> dict[str, Any]:
        return self._get(f"/health/{endpoint}")

    def balance(self, account: str) -> dict[str, Any]:
        return self._get(f"/api/v1/accounts/{account}/balance")

    def transact(
        self,
        action: BankingAction,
        account: str,
        amount: int,
        *,
        request_id: UUID | None = None,
    ) -> dict[str, Any]:
        payload = {
            "request_id": str(request_id or uuid4()),
            "action": action,
            "account": account,
            "amount": amount,
        }
        for attempt in range(self.retries + 1):
            try:
                response = self.http.post("/api/v1/transactions", json=payload)
                response.raise_for_status()
                return response.json()
            except httpx2.HTTPStatusError as exc:
                if exc.response.status_code not in (502, 503, 504) or attempt == self.retries:
                    raise
            except (httpx2.ConnectError, httpx2.TimeoutException, httpx2.RemoteProtocolError):
                if attempt == self.retries:
                    raise
            # Reuse the same request ID on each retry, never a second financial action.
            sleep(random.uniform(0, min(0.1 * 2**attempt, 1)))
        raise AssertionError("unreachable")
