"""In-memory bank for failover demos without real network writes."""

from uuid import UUID

import httpx2


class FakeBank:
    def __init__(self, *, lost_responses: int = 0, switch_backend: bool = True) -> None:
        self.balance_minor = 800
        self.requests: dict[UUID, int] = {}
        self.attempts = 0
        self.lost_responses = lost_responses
        self.instances = iter(["banking-a", "banking-b" if switch_backend else "banking-a"])

    def __enter__(self) -> "FakeBank":
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def balance(self, _account: str) -> dict[str, int]:
        return {"balance": self.balance_minor}

    def check(self, _endpoint: str) -> dict[str, str]:
        return {"instance": next(self.instances)}

    def transact(
        self, _action: str, _account: str, amount: int, *, request_id: UUID
    ) -> dict[str, object]:
        self.attempts += 1
        replayed = request_id in self.requests
        if replayed:
            assert self.requests[request_id] == amount
        else:
            self.requests[request_id] = amount
            self.balance_minor += amount

        if self.attempts <= self.lost_responses:
            raise httpx2.ConnectError("response lost after commit")
        return {"replayed": replayed, "balance": self.balance_minor}
