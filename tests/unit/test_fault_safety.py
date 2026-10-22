"""No network changes: pure validation and mocked recovery scheduling."""

import argparse

import pytest
from scripts.fault import network_partition as fault
from scripts.fault import quorum_probe as probe


def test_partition_rules_affect_only_specified_peers() -> None:
    rules = fault.build_rules(["10.4.0.12", "10.4.0.13"])
    assert "ip saddr 10.4.0.12 drop" in rules
    assert "ip daddr 10.4.0.13 drop" in rules
    assert "10.4.0.14" not in rules
    assert "policy accept" in rules
    assert "flush ruleset" not in rules


@pytest.mark.parametrize("address", ["192.0.2.11", "203.0.113.2", "127.0.0.1", "8.8.8.8"])
def test_partition_rejects_non_lab_ips(address: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        fault.valid_ip(address)


def test_auto_restore_is_scheduled_before_firewall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr(fault, "table_exists", lambda: False)
    monkeypatch.setattr(fault.shutil, "which", lambda name: f"/usr/sbin/{name}")
    monkeypatch.setattr(fault, "run", lambda *args, **kwargs: calls.append(args))
    fault.apply(["10.4.0.12"], duration=120)
    assert calls[0][:3] == ("nft", "-c", "-f")
    assert calls[1][0] == "systemd-run"
    assert calls[2][:2] == ("nft", "-f")


def test_only_a_dedicated_yugabyte_test_database_is_allowed() -> None:
    probe.check_url("postgresql+psycopg://user:secret@10.4.0.11:5433/banking_test")
    with pytest.raises(ValueError):
        probe.check_url("postgresql+psycopg://user:secret@10.4.0.11:5433/banking")
    with pytest.raises(ValueError):
        probe.check_url(
            "postgresql+psycopg://user:secret@/banking_test?host=10.4.0.11:5433&host=10.4.0.12:5433"
        )
