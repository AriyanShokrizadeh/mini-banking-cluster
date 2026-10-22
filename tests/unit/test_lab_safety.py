"""Lab guardrails without a live database or SSH connection."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import httpx2
import pytest
from scripts.demos import lab, lab_admin
from scripts.demos.recording_support import DemoFailure


@pytest.fixture
def isolated_reports(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(lab, "ROOT", tmp_path)
    return tmp_path / "demo-results"


def test_block_marker_contains_reconciliation_evidence(isolated_reports) -> None:
    lab.mark_blocked("DEMO_LAB_BASIC", "request id unresolved")
    path = isolated_reports / "BLOCKED-DEMO_LAB_BASIC.json"

    assert json.loads(path.read_text())["reason"] == "request id unresolved"
    with pytest.raises(DemoFailure, match="unresolved outcomes"):
        lab.assert_unblocked("DEMO_LAB_BASIC")


def test_health_failure_does_not_block_financial_accounts(
    isolated_reports, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = MagicMock()
    client.return_value.__enter__.return_value.check.side_effect = httpx2.ConnectError(
        "unavailable"
    )
    monkeypatch.setattr(lab, "BankingClient", client)
    with pytest.raises(DemoFailure, match="Gateway not ready"):
        lab.check_health("http://unavailable")
    assert not isolated_reports.exists()


def test_reset_with_unknown_outcome_blocks_account(
    isolated_reports, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = MagicMock()
    instance = client.return_value.__enter__.return_value
    instance.balance.return_value = {"balance": 1100}
    instance.transact.side_effect = httpx2.ReadTimeout("response lost")
    monkeypatch.setattr(lab, "BankingClient", client)
    with pytest.raises(DemoFailure, match="UNKNOWN reset outcome"):
        lab.restore_balance("http://test", "DEMO_LAB_BASIC")
    assert (isolated_reports / "BLOCKED-DEMO_LAB_BASIC.json").is_file()


def test_admin_without_command_shows_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["lab_admin"])
    assert lab_admin.main() == 2
