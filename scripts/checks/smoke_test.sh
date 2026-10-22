#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
BASE_URL="${BASE_URL%/}"

check_health() {
    local name="$1"
    local endpoint="$2"

    printf '\nChecking %s...\n' "$name"

    curl --fail --silent --show-error --max-time 5 \
        "${BASE_URL}${endpoint}"

    printf '\n'
}

check_health "API liveness" "/health/live"
check_health "database connectivity" "/health/db"
check_health "write readiness" "/health/ready"

printf '\nAll health checks passed.\n'
