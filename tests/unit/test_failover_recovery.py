"""Failover demonstration checks without stopping a real service."""

import pytest
from scripts.demos import failover_demo
from tests.fakes import FakeBank


def run_fake_demo(
    bank: FakeBank, monkeypatch: pytest.MonkeyPatch, *, count: int = 3
) -> dict[str, object]:
    monkeypatch.setattr(failover_demo, "sleep", lambda _seconds: None)
    monkeypatch.setattr(failover_demo, "BankingClient", lambda *_a, **_kw: bank)
    return failover_demo.run_demo(
        "http://lab.test", "A1002", count=count, amount=1, interval=0, retries=2
    )


def test_lost_response_retries_same_id_without_second_deposit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bank = FakeBank(lost_responses=1)
    report = run_fake_demo(bank, monkeypatch)

    assert report["passed"] is True
    assert (report["before"], report["after"], report["after_replay"]) == (
        800,
        803,
        803,
    )
    assert (report["confirmed"], report["recovered"]) == (2, 1)
    assert report["replay_verified"] is True
    assert len(bank.requests) == 3
    request_ids = report["request_ids"]
    assert isinstance(request_ids, list)
    assert set(request_ids) == {str(key) for key in bank.requests}


def test_no_backend_change_fails_check(monkeypatch: pytest.MonkeyPatch) -> None:
    report = run_fake_demo(FakeBank(switch_backend=False), monkeypatch, count=1)
    assert report["passed"] is False
    assert report["final_instance"] == "banking-a"


def test_unresolved_request_keeps_original_id(monkeypatch: pytest.MonkeyPatch) -> None:
    bank = FakeBank(lost_responses=2)
    report = run_fake_demo(bank, monkeypatch, count=1)

    assert report["passed"] is False
    assert report["unresolved_ids"] == [str(next(iter(bank.requests)))]
    assert report["request_ids"] == report["unresolved_ids"]
    assert (report["before"], report["after"]) == (800, 801)
    assert len(bank.requests) == 1
