#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
command -v uv >/dev/null || { echo 'Install uv first.' >&2; exit 1; }

if [[ -f uv.lock ]]; then
    uv sync --locked --group dev
else
    echo 'Generating uv.lock on the first install.'
    uv sync --group dev
fi

uv run --no-sync ruff check src scripts tests
uv run --no-sync ruff format --check src scripts tests
uv run --no-sync pyright
uv run --no-sync pytest -q -m 'not cluster'

while IFS= read -r -d '' script; do
    bash -n "$script"
done < <(find scripts -name '*.sh' -type f -print0)

echo 'Local checks passed. Live cluster tests are separate.'
