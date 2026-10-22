.PHONY: install test check serve smoke audit

install:
	uv sync --group dev

test:
	uv run pytest -q -m 'not cluster'

check:
	bash scripts/checks/release_check.sh

serve:
	uv run python -m banking

smoke:
	bash scripts/checks/smoke_test.sh

audit:
	uv run python scripts/checks/audit_ledger.py
