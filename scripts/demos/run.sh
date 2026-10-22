#!/usr/bin/env bash
# A single VM4 entry point, serialized to prevent concurrent demos.
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -f "$ROOT/scripts/demos/config.env" ]]; then
    set -a
    source "$ROOT/scripts/demos/config.env"
    set +a
fi
PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    echo "Missing .venv; run 'uv sync' once on VM4" >&2
    exit 2
fi
export PYTHONPATH="$ROOT/src:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$ROOT/demo-results"
cd "$ROOT"
SCENARIO="${1:-help}"
shift || true
case "$SCENARIO" in
    prepare|reset|cleanup|cleanup-execute|reset-core|reconcile)
        CMD=("$PYTHON" -m scripts.demos.lab_admin "$SCENARIO" "$@") ;;
    failover|partition)
        CMD=("$PYTHON" -m scripts.demos.cluster_demo "$SCENARIO" "$@") ;;
    health|basic|idempotency|errors|concurrency|atomicity|all|logs|durability)
        ARGS=("$@")
        if [[ "$SCENARIO" == durability ]]; then
            ARGS=(--allow-restart "${ARGS[@]}")
        fi
        CMD=("$PYTHON" -m scripts.demos.recording_demo "$SCENARIO" "${ARGS[@]}") ;;
    *)
        echo 'Run: ./scripts/demos/run.sh <health|basic|errors|idempotency|concurrency|atomicity|durability|failover|partition|logs|all|prepare|reset|cleanup|cleanup-execute|reset-core|reconcile>'
        exit 2 ;;
esac
if ! command -v flock >/dev/null; then
    echo "Missing 'flock' command (util-linux)" >&2
    exit 2
fi
exec flock -n -E 75 "$ROOT/demo-results/.run.lock" "${CMD[@]}"
