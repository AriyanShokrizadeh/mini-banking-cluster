#!/usr/bin/env bash
# Four-VM rolling release for the existing lab. Run on VM4 as the VMWare user.
set -euo pipefail
umask 077
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
MODE="${1:-check}"
VM1="${DEMO_SSH_A:-ariyan@192.168.200.128}"
VM2="${DEMO_SSH_B:-ariyan@192.168.200.129}"
VM3="${DEMO_SSH_DB:-ariyan@192.168.200.132}"
GATEWAY=http://127.0.0.1:8080
BUNDLE=''

usage() {
    echo 'Usage: ./scripts/deploy/prepare_four_vms.sh {check|apply|cleanup-preview|cleanup-apply}'
}
[[ "$MODE" == check || "$MODE" == apply || "$MODE" == cleanup-preview || "$MODE" == cleanup-apply ]] || { usage; exit 2; }
for host in "$VM1" "$VM2" "$VM3"; do
    [[ "$host" =~ ^[a-zA-Z0-9_.-]+@[0-9.]+$ ]] || { echo "Invalid SSH destination: $host" >&2; exit 2; }
done

remote() { local host="$1"; shift; ssh -tt -o ConnectTimeout=8 "$host" "$@"; }
check_http() {
    local label="$1" url="$2" expected="$3" result
    result=$(curl -fsS --max-time 12 "$url") || { echo "FAIL | $label" >&2; return 1; }
    [[ "$result" == *"$expected"* ]] || { echo "Unexpected $label: $result" >&2; return 1; }
    echo "PASS | $label: $result"
}
check_all() {
    echo '===== VM1 BANKING A ====='
    check_http VM1 http://192.168.200.128:8000/health/ready '"instance":"banking-a"'
    echo '===== VM2 BANKING B ====='
    check_http VM2 http://192.168.200.129:8000/health/ready '"instance":"banking-b"'
    echo '===== VM3 YUGABYTED ====='
    remote "$VM3" 'systemctl is-active --quiet yugabyted && echo "PASS | VM3 YugabyteDB active"'
    timeout 5 bash -c 'echo > /dev/tcp/192.168.200.132/5433' || { echo 'FAIL | VM3 YSQL port' >&2; return 1; }
    echo '===== VM4 HAPROXY ====='
    systemctl is-active --quiet haproxy
    check_http VM4 "$GATEWAY/health/ready" '"status":"ready"'
    echo '===== CLUSTER BALANCE CHECK ====='
    for ip in 192.168.200.128 192.168.200.129; do
        check_http "A1001 on $ip" "http://$ip:8000/api/v1/accounts/A1001/balance" '"status":"success"'
    done
}
cleanup_remote() {
    local host="$1" role="$2" target="/home/ariyan/.mini-banking-cleanup-$$.sh"
    scp -q "$ROOT/scripts/deploy/cleanup_previous.sh" "$host:$target"
    if [[ "$MODE" == cleanup-apply ]]; then
        remote "$host" "sudo bash '$target' apply '$role'"
    else
        remote "$host" "bash '$target' preview '$role'"
    fi
    remote "$host" "rm -f -- '$target'"
}
cleanup_all() {
    check_all
    if [[ "$MODE" == cleanup-apply ]]; then
        read -r -p 'Type CLEAN-OLD-STAGES to delete ONLY previewed temporary files: ' approval
        [[ "$approval" == CLEAN-OLD-STAGES ]] || { echo 'Cancelled'; exit 2; }
    fi
    cleanup_remote "$VM1" api
    cleanup_remote "$VM2" api
    cleanup_remote "$VM3" database
    if [[ "$MODE" == cleanup-apply ]]; then
        sudo bash "$ROOT/scripts/deploy/cleanup_previous.sh" apply gateway
    else
        bash "$ROOT/scripts/deploy/cleanup_previous.sh" preview gateway
    fi
    echo 'Legacy staging cleanup completed. Financial data and rollback archives untouched.'
}
prepare_bundle() {
    [[ -f "$ROOT/uv.lock" ]] || { echo 'STOP: no uv.lock. Preserve it from the working VM4 project; do not create a different lock on the API nodes.' >&2; exit 2; }
    [[ -x "$ROOT/.venv/bin/python" ]] || { echo 'STOP: VM4 .venv is missing.' >&2; exit 2; }
    BUNDLE=$(mktemp /tmp/mini-banking-release.XXXXXXXX.tar.gz)
    # Explicit manifest: no credentials, .venv, reports, source-control data or old stages.
    manifest=(src scripts tests docs infra diagram pyproject.toml README.md Makefile .env.example .gitignore .pre-commit-config.yaml uv.lock)
    [[ ! -f "$ROOT/pyrightconfig.json" ]] || manifest+=(pyrightconfig.json)
    tar -czf "$BUNDLE" -C "$ROOT" \
      --exclude='*/__pycache__' --exclude='*.pyc' \
      --exclude='scripts/demos/config.env' --exclude='*/.pytest_cache' \
      "${manifest[@]}"
    sha256sum "$BUNDLE"
}
apply_node() {
    local host="$1" role="$2" remote_bundle="/home/ariyan/.mini-banking-upgrade-$$.tar.gz" \
          remote_script="/home/ariyan/.mini-banking-installer-$$.sh"
    echo "===== UPDATE $role ====="
    scp -q "$BUNDLE" "$host:$remote_bundle"
    scp -q "$ROOT/scripts/deploy/install_api_node.sh" "$host:$remote_script"
    if ! remote "$host" "sudo bash '$remote_script' '$role' '$remote_bundle'"; then
        remote "$host" "rm -f -- '$remote_bundle' '$remote_script'" || true
        echo "STOP: $role update failed. Other API node was not touched in this step." >&2
        exit 1
    fi
    remote "$host" "rm -f -- '$remote_bundle' '$remote_script'"
    check_http "$role" "http://${host##*@}:8000/health/ready" "\"instance\":\"$role\""
}

if [[ "$MODE" == check ]]; then
    check_all
elif [[ "$MODE" == cleanup-preview || "$MODE" == cleanup-apply ]]; then
    cleanup_all
else
    cd "$ROOT"
    check_all
    echo '===== VM4 LOCAL TESTS ====='
    "$ROOT/.venv/bin/python" -m pytest tests/unit -q
    read -r -p 'Type DEPLOY to upgrade VM2 then VM1 (with a brief API restart): ' approval
    [[ "$approval" == DEPLOY ]] || { echo 'Cancelled'; exit 2; }
    prepare_bundle
    trap '[[ -z "$BUNDLE" ]] || rm -f -- "$BUNDLE"' EXIT
    # Upgrade backup first, then primary; the other service stays online.
    apply_node "$VM2" banking-b
    apply_node "$VM1" banking-a
    check_all
    echo 'PASS | Four-VM deployment verified. Existing financial data preserved.'
    echo 'Next: ./scripts/demos/run.sh prepare'
    echo 'Optional: ./scripts/deploy/prepare_four_vms.sh cleanup-preview'
fi
