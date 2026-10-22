"""Guard the existing flat deployment paths and explicit cleanup semantics."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_systemd_uses_flat_release() -> None:
    unit = (ROOT / "infra/systemd/banking-api.service").read_text()
    assert "WorkingDirectory=/opt/mini-banking-releases\n" in unit
    assert "ExecStart=/opt/mini-banking-releases/.venv/bin/python -m banking" in unit
    assert "v0.7.0-httpx2" not in unit


def test_haproxy_routes_existing_lab() -> None:
    config = (ROOT / "infra/haproxy/haproxy.cfg").read_text()
    assert "server banking_a 192.168.200.128:8000 check" in config
    assert "server banking_b 192.168.200.129:8000 check backup" in config


def test_cleanup_requires_explicit_apply_and_never_targets_database() -> None:
    script = (ROOT / "scripts/deploy/cleanup_previous.sh").read_text()
    assert "preview" in script and "apply" in script
    assert "mountpoint" in script
    assert "/var/lib/yugabyte/cluster" not in script
    assert "rm -rf --one-file-system" in script


def test_deployment_rejects_unexpected_version_and_missing_lock() -> None:
    script = (ROOT / "scripts/deploy/install_api_node.sh").read_text()
    assert "DropInPaths --value" in script
    assert 'cmp -s "$BASE/uv.lock" "$WORK/new/uv.lock"' in script
    assert "trap rollback EXIT" in script
