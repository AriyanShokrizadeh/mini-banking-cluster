"""Read-only smoke test of both backends before an operator-triggered crash."""

import os

import httpx2
import pytest

pytestmark = pytest.mark.cluster


def test_primary_and_backup_are_ready() -> None:
    primary = os.getenv("BANKING_TEST_PRIMARY_URL")
    backup = os.getenv("BANKING_TEST_BACKUP_URL")
    proxy = os.getenv("BANKING_TEST_HAPROXY_URL")
    if not all((primary, backup, proxy)):
        pytest.skip("Set PRIMARY, BACKUP and HAPROXY test URLs")

    assert primary is not None and backup is not None and proxy is not None
    with httpx2.Client(timeout=5) as client:
        a = client.get(f"{primary.rstrip('/')}/health/ready")
        b = client.get(f"{backup.rstrip('/')}/health/ready")
        gateway = client.get(f"{proxy.rstrip('/')}/health/ready")

    assert a.status_code == b.status_code == gateway.status_code == 200
    assert a.json()["instance"] != b.json()["instance"]
    assert gateway.json()["instance"] == a.json()["instance"]
