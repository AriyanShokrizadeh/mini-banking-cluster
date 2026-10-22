"""Fixed-pool lifecycle and orchestrator callbacks, without live VM access."""

import pytest
from scripts.demos import failover_demo
from scripts.demos.lab import ACCOUNTS, BASELINE, account_for
from scripts.setup.prepare_lab import LAB_ACCOUNTS, prepare
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from tests.fakes import FakeBank

from banking.infrastructure.models import Account


def test_fixed_pool_is_reused_and_preparation_is_idempotent(engine: Engine) -> None:
    assert account_for("basic") == account_for("idempotency")
    assert account_for("partition") != account_for("failover")
    assert set(ACCOUNTS.values()) == set(LAB_ACCOUNTS)
    prepare(engine)
    prepare(engine)
    with Session(engine) as session:
        accounts = session.scalars(
            select(Account).where(Account.account_id.in_(LAB_ACCOUNTS))
        ).all()
        assert len(accounts) == 5
        assert all(item.balance_minor == BASELINE for item in accounts)
        assert session.get_one(Account, "A1001").balance_minor == 1000


def test_streaming_failover_callback_interleaves_with_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bank = FakeBank()
    events = []
    monkeypatch.setattr(failover_demo, "BankingClient", lambda *_a, **_k: bank)
    monkeypatch.setattr(failover_demo, "sleep", lambda _t: None)

    def progress(index: int) -> None:
        events.append((index, bank.attempts))

    report = failover_demo.run_demo(
        "http://fake",
        "DEMO_LAB_FAILOVER",
        count=4,
        amount=1,
        interval=0,
        retries=0,
        workers=1,
        on_progress=progress,
    )
    assert report["passed"] is True
    assert events == [(1, 1), (2, 2), (3, 3), (4, 4)]


def test_restore_is_a_compensating_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.demos import lab

    state = {"amount": 1050, "requests": []}

    class FakeClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def balance(self, _account):
            return {"balance": state["amount"]}

        def transact(self, action, _account, amount, *, request_id):
            state["requests"].append(request_id)
            state["amount"] += amount if action == "deposit" else -amount
            return {"balance": state["amount"]}

    monkeypatch.setattr(lab, "BankingClient", FakeClient)
    lab.restore_balance("http://local", "DEMO_LAB_BASIC")
    assert state["amount"] == 1000
    assert len(state["requests"]) == 1
    with pytest.raises(Exception, match="fixed lab account"):
        lab.restore_balance("http://local", "A1001")


def test_legacy_cleanup_saves_snapshot_and_keeps_seeded_account(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from uuid import uuid4

    from scripts.setup import cleanup_legacy_demo as cleanup

    from banking.application.service import BankingService

    with Session(engine) as session, session.begin():
        session.add(
            Account(
                account_id="DEMO_PARTITION_01",
                opening_balance_minor=1000,
                balance_minor=1000,
            )
        )
    with Session(engine) as session:
        BankingService(session).transact(
            request_id=str(uuid4()),
            action="deposit",
            account="DEMO_PARTITION_01",
            amount=17,
        )

    monkeypatch.setattr(cleanup, "BACKUP_DIR", tmp_path / "backups")
    cleanup.run(engine, execute=False)
    with Session(engine) as session:
        assert session.get_one(Account, "DEMO_PARTITION_01").balance_minor == 1017
    cleanup.run(engine, execute=True)
    with Session(engine) as session:
        assert session.get(Account, "DEMO_PARTITION_01") is None
        assert session.get_one(Account, "A1001").balance_minor == 1000
    snapshots = list((tmp_path / "backups").glob("*.json"))
    assert len(snapshots) == 1
    assert "DEMO_PARTITION_01" in snapshots[0].read_text()


def test_failover_orchestrator_recovers_service_even_if_demo_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.demos import cluster_demo as cluster
    from scripts.demos.recording_support import DemoFailure

    calls: list[str] = []
    monkeypatch.setattr(cluster, "restore_balance", lambda *_: None)
    monkeypatch.setattr(cluster, "verify_all_ready", lambda: None)
    monkeypatch.setattr(cluster, "wait_backend", lambda *_a, **_kw: None)
    monkeypatch.setattr(cluster, "remote", lambda _host, command: calls.append(command))
    monkeypatch.setattr(cluster, "save_report", lambda *_a: calls.append("saved"))
    monkeypatch.setattr(cluster, "mark_blocked", lambda *_a: calls.append("blocked"))

    def interrupted(_server, _account, *, on_begin, on_progress, **_kwargs):
        on_begin(["sample-id"])
        on_progress(3)
        raise DemoFailure("simulated client loss")

    monkeypatch.setattr(cluster.failover_demo, "run_demo", interrupted)
    with pytest.raises(DemoFailure, match="simulated"):
        cluster.failover()
    assert "sudo systemctl stop banking-api" in calls
    assert "sudo systemctl start banking-api" in calls
    assert "blocked" in calls
    assert calls[-1] == "saved"


def test_partition_orchestrator_restores_fault_after_quorum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.demos import cluster_demo as cluster

    events: list[str] = []
    monkeypatch.setattr(cluster, "restore_balance", lambda *_: events.append("reset"))
    monkeypatch.setattr(cluster, "verify_all_ready", lambda: events.append("ready"))
    monkeypatch.setattr(cluster, "fault_status", lambda: None)
    monkeypatch.setattr(cluster, "quorum_sequence", lambda: events.append("sequence"))
    monkeypatch.setattr(cluster, "balance", lambda *_: 1003)
    monkeypatch.setattr(cluster, "remote", lambda _host, command: events.append(command))
    monkeypatch.setattr(cluster, "partition_restore", lambda: events.append("restore"))
    monkeypatch.setattr(cluster, "quorum", lambda *_args: events.append("probe"))
    monkeypatch.setattr(cluster, "save_report", lambda *_: events.append("saved"))

    def fake_run(_server, _account, *, on_begin, on_progress, before_reconcile, **_kwargs):
        on_begin(["id-1"])
        on_progress(5)
        before_reconcile()
        return {"financial_check_passed": True, "quorum_proved": False}

    monkeypatch.setattr(cluster.partition_demo, "run_demo", fake_run)
    assert cluster.partition() is True
    assert "probe" in events
    assert events.count("restore") == 2
    assert events[-1] == "saved"
