"""Public HTTP contracts backed by local SQLite, not a distributed cluster."""

import logging
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from tests.helpers import IsolatedSettings

from banking.application.service import BankingService
from banking.infrastructure.models import Account, HealthProbe
from banking.main import create_app

TRANSACTIONS = "/api/v1/transactions"


def payload(action: str = "deposit", amount: int = 100) -> dict[str, str | int]:
    return {
        "request_id": str(uuid4()),
        "action": action,
        "account": "A1001",
        "amount": amount,
    }


def test_balance_and_missing_account(client: TestClient) -> None:
    response = client.get("/api/v1/accounts/A1001/balance")
    assert response.json() == {"status": "success", "account": "A1001", "balance": 1000}
    missing = client.get("/api/v1/accounts/MISSING/balance")
    assert (missing.status_code, missing.json()["error"]["code"]) == (
        404,
        "ACCOUNT_NOT_FOUND",
    )


def test_deposit_replay_has_one_effect(client: TestClient) -> None:
    body = payload()
    first = client.post(TRANSACTIONS, json=body)
    replay = client.post(TRANSACTIONS, json=body)
    assert first.status_code == replay.status_code == 200
    assert (first.json()["balance"], replay.json()["balance"]) == (1100, 1100)
    assert (first.json()["replayed"], replay.json()["replayed"]) == (False, True)
    assert client.get("/api/v1/accounts/A1001/balance").json()["balance"] == 1100


def test_reusing_id_with_different_amount_conflicts(client: TestClient) -> None:
    body = payload(amount=10)
    assert client.post(TRANSACTIONS, json=body).status_code == 200
    response = client.post(TRANSACTIONS, json={**body, "amount": 20})
    assert (response.status_code, response.json()["error"]["code"]) == (
        409,
        "IDEMPOTENCY_CONFLICT",
    )


def test_insufficient_funds_is_replayed_as_an_error(client: TestClient) -> None:
    body = payload("withdraw", 1200)
    for _ in range(2):
        response = client.post(TRANSACTIONS, json=body)
        assert (response.status_code, response.json()["error"]["code"]) == (
            409,
            "INSUFFICIENT_FUNDS",
        )


@pytest.mark.parametrize(
    ("body", "code", "status"),
    [
        (b'{"action":', "MALFORMED_REQUEST", 400),
        (b'{"action":"deposit","account":"A1001"}', "MISSING_FIELD", 422),
    ],
)
def test_invalid_requests_have_public_error_codes(
    client: TestClient, body: bytes, code: str, status: int
) -> None:
    response = client.post(TRANSACTIONS, content=body, headers={"content-type": "application/json"})
    assert (response.status_code, response.json()["error"]["code"]) == (status, code)


def test_health_checks_without_database() -> None:
    settings = IsolatedSettings(database_url=None, instance_name="api-test")
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/live").json() == {
            "status": "alive",
            "instance": "api-test",
        }
        assert client.get("/health/db").status_code == 503
        ready = client.get("/health/ready")
        assert (ready.status_code, ready.json()["reason"]) == (
            503,
            "database_not_configured",
        )


def test_readiness_commits_without_changing_balance(client: TestClient, engine: Engine) -> None:
    assert client.get("/health/db").json()["status"] == "connected"
    for _ in range(2):
        assert client.get("/health/ready").json()["status"] == "ready"
    with Session(engine) as session:
        assert session.scalar(select(HealthProbe.sequence)) == 2
        assert (
            session.scalar(select(Account.balance_minor).where(Account.account_id == "A1001"))
            == 1000
        )


def test_database_errors_do_not_leak_details(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(_service: BankingService, _account: str) -> int:
        raise SQLAlchemyError("private database diagnostic")

    monkeypatch.setattr(BankingService, "get_balance", fail)
    response = client.get("/api/v1/accounts/A1001/balance")
    assert (response.status_code, response.json()["error"]["code"]) == (
        503,
        "SERVICE_UNAVAILABLE",
    )
    assert "private database diagnostic" not in response.text


def test_database_errors_log_safe_diagnostics(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class DriverError(Exception):
        sqlstate = "23503"
        diag = SimpleNamespace(constraint_name="ledger_entries_request_id_fkey")

    def fail(_service: BankingService, _account: str) -> int:
        raise IntegrityError(
            "private SQL statement", {"secret": "private parameter"}, DriverError()
        )

    monkeypatch.setattr(BankingService, "get_balance", fail)
    with caplog.at_level(logging.ERROR, logger="banking.errors"):
        response = client.get("/api/v1/accounts/A1001/balance")

    assert response.status_code == 503
    assert "private" not in response.text
    errors = [record for record in caplog.records if record.msg == "database_operation_failed"]
    assert len(errors) == 1
    record = errors[0]
    assert vars(record)["exception_type"] == "IntegrityError"
    assert vars(record)["database_exception_type"] == "DriverError"
    assert vars(record)["sqlstate"] == "23503"
    assert vars(record)["constraint_name"] == "ledger_entries_request_id_fkey"
    assert not record.exc_info
    assert "private" not in record.getMessage()


@pytest.mark.parametrize("header", ["trace-42", "unsafe id"])
def test_request_id_header_is_safe(client: TestClient, header: str) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": header})
    actual = response.headers["X-Request-ID"]
    if header == "trace-42":
        assert actual == header
    else:
        assert str(UUID(actual)) == actual


@pytest.mark.parametrize(
    ("endpoint", "probe", "reason"),
    [
        ("/health/db", "check_ysql_connection", "database_unreachable"),
        ("/health/ready", "probe_committed_write", "database_write_unavailable"),
    ],
)
def test_health_probe_errors_log_diagnostics_without_sql(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    endpoint: str,
    probe: str,
    reason: str,
) -> None:
    from banking.api import health

    class DriverError(Exception):
        sqlstate = "40P01"
        diag = SimpleNamespace(constraint_name=None)

    def fail(*_args: object) -> None:
        raise IntegrityError("private SQL text", {"secret": "private parameter"}, DriverError())

    monkeypatch.setattr(health, probe, fail)
    with caplog.at_level(logging.ERROR, logger="banking.health"):
        response = client.get(endpoint)

    assert response.status_code == 503
    assert response.json()["reason"] == reason
    record = next(row for row in caplog.records if row.name == "banking.health")
    assert vars(record)["exception_type"] == "IntegrityError"
    assert vars(record)["sqlstate"] == "40P01"
    assert record.exc_info is None
    assert "private" not in record.getMessage()
    assert "private" not in response.text
