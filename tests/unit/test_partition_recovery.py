"""A clean financial report never claims to prove Raft quorum by itself."""

from threading import Lock

import pytest
from scripts.demos import partition_demo as demo


def test_financial_success_is_not_automatically_quorum_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    balance = 1000
    seen = set()
    lock = Lock()

    class FakeClient:
        def __init__(self, _base_url, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def balance(self, _account):
            return {"balance": balance}

    def fake_send(_server, _account, amount, request_id, _timeout):
        nonlocal balance
        with lock:
            if request_id not in seen:
                seen.add(request_id)
                balance += amount
        return "confirmed"

    monkeypatch.setattr(demo, "BankingClient", FakeClient)
    monkeypatch.setattr(demo, "deposit", fake_send)
    monkeypatch.setattr(demo, "sleep", lambda _: None)
    report = demo.run_demo(
        "http://gateway",
        "TEST_ACCOUNT",
        count=10,
        amount=2,
        workers=4,
        interval=0,
        recovery_wait=0,
        timeout=3,
    )
    assert report["financial_check_passed"] is True
    assert report["quorum_proved"] is False
    assert report["before"] == 1000
    assert report["after"] == 1020
