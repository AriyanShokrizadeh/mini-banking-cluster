"""HTTP client request formatting and retry identity."""

import json
from uuid import UUID

import httpx2
import pytest

from client.banking_client import BankingClient


def test_transaction_retry_reuses_request_id() -> None:
    seen: list[str] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(request.content)["request_id"])
        if len(seen) == 1:
            return httpx2.Response(503, json={"status": "error"})
        return httpx2.Response(200, json={"status": "success", "balance": 1100})

    with BankingClient(
        "http://bank.test",
        transport=httpx2.MockTransport(respond),
        retries=1,
    ) as client:
        result = client.transact("deposit", "A1001", 100)

    assert result["balance"] == 1100
    assert len(seen) == 2
    assert seen[0] == seen[1]
    assert UUID(seen[0])


def test_balance_request_is_read_only() -> None:
    def respond(request: httpx2.Request) -> httpx2.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v1/accounts/A1001/balance"
        return httpx2.Response(200, json={"status": "success", "account": "A1001", "balance": 1000})

    with BankingClient("http://bank.test", transport=httpx2.MockTransport(respond)) as client:
        assert client.balance("A1001")["balance"] == 1000


def test_http_client_does_not_retry_business_errors() -> None:
    count = 0

    def respond(_request: httpx2.Request) -> httpx2.Response:
        nonlocal count
        count += 1
        return httpx2.Response(409, json={"error": {"code": "INSUFFICIENT_FUNDS"}})

    with BankingClient(
        "http://bank.test", transport=httpx2.MockTransport(respond), retries=3
    ) as client:
        with pytest.raises(httpx2.HTTPStatusError):
            client.transact("withdraw", "A1001", 2000)
    assert count == 1


def test_http_client_reuses_id_after_network_timeout() -> None:
    seen = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(request.content)["request_id"])
        if len(seen) == 1:
            raise httpx2.ReadTimeout("simulated lost response")
        return httpx2.Response(200, json={"balance": 1001})

    with BankingClient(
        "http://bank.test", transport=httpx2.MockTransport(respond), retries=1
    ) as client:
        assert client.transact("deposit", "A1001", 1)["balance"] == 1001
    assert len(seen) == 2 and seen[0] == seen[1]


def test_http_client_default_does_not_retry_uncertain_writes() -> None:
    count = 0

    def respond(_request: httpx2.Request) -> httpx2.Response:
        nonlocal count
        count += 1
        raise httpx2.ReadTimeout("simulated lost response")

    with BankingClient("http://bank.test", transport=httpx2.MockTransport(respond)) as client:
        with pytest.raises(httpx2.ReadTimeout):
            client.transact("deposit", "A1001", 1)
    assert count == 1
