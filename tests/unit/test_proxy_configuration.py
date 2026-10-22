"""Check that the gateway never retries a financial POST itself."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HAPROXY = ROOT / "infra/haproxy/haproxy.cfg"


def test_proxy_uses_readiness_for_active_passive_routing() -> None:
    contents = HAPROXY.read_text()
    assert "option httpchk GET /health/ready" in contents
    assert "http-check expect status 200" in contents
    assert re.search(r"^\s*server banking_a \S+:8000 check\s*$", contents, re.M)
    assert re.search(r"^\s*server banking_b \S+:8000 check backup\s*$", contents, re.M)


def test_proxy_never_retries_financial_requests() -> None:
    directives = [line.strip() for line in HAPROXY.read_text().splitlines()]
    assert "retries 0" in directives
    assert not any(line.startswith("retry-on ") for line in directives)
