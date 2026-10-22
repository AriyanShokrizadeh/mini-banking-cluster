#!/usr/bin/env bash
# Run as root on VM1/VM2; preserve the flat active release and the protected environment.
set -Eeuo pipefail
umask 077

ROLE="${1:-}"
BUNDLE="${2:-}"
BASE=/opt/mini-banking-releases
UNIT=/etc/systemd/system/banking-api.service
BACKUPS=/var/backups/mini-banking-deploy
WORK=''
BACKUP=''
UPDATED=0

fail() { echo "ERROR: $*" >&2; exit 1; }
ready() {
    local i response
    for i in $(seq 1 35); do
        response=$(curl -fsS --max-time 8 http://127.0.0.1:8000/health/ready 2>/dev/null) || true
        if [[ "$response" == *'"status":"ready"'* && "$response" == *"\"instance\":\"$ROLE\""* ]]; then
            return 0
        fi
        sleep 1
    done
    return 1
}
rollback() {
    local code=$?
    trap - ERR EXIT
    if (( UPDATED )) && [[ -f "$BACKUP" ]]; then
        echo 'Deployment failed. Restoring the previous source...' >&2
        systemctl stop banking-api || true
        cd "$BASE"
        for p in src scripts tests docs infra diagram pyproject.toml README.md Makefile .env.example .gitignore .pre-commit-config.yaml uv.lock pyrightconfig.json; do
            rm -rf -- "$p"
        done
        tar -xzf "$BACKUP" -C "$BASE" || true
        chown -R banking:banking "$BASE/src" "$BASE/scripts" 2>/dev/null || true
        systemctl start banking-api || true
        ready && echo 'Rollback restored a ready API.' >&2 || echo 'URGENT: Check banking-api on VMware console.' >&2
    fi
    [[ -z "$WORK" ]] || rm -rf --one-file-system -- "$WORK"
    exit "$code"
}
trap rollback EXIT

[[ $EUID -eq 0 ]] || fail 'Run with sudo.'
[[ "$ROLE" == banking-a || "$ROLE" == banking-b ]] || fail 'Expected banking-a or banking-b.'
[[ -f "$BUNDLE" && ! -L "$BUNDLE" ]] || fail 'Release bundle not found.'
[[ -d "$BASE" && ! -L "$BASE" ]] || fail 'Flat active directory is missing or linked.'
[[ -f "$UNIT" ]] || fail 'Missing systemd unit.'
[[ "$(systemctl show banking-api -p WorkingDirectory --value)" == "$BASE" ]] || fail 'Unexpected active directory; refusing deployment.'
[[ -z "$(systemctl show banking-api -p DropInPaths --value)" ]] || fail 'Unexpected systemd override.'
[[ "$(systemctl show banking-api -p User --value)" == banking ]] || fail 'Unexpected service user.'
[[ -f /etc/mini-banking/banking.env ]] || fail 'Missing protected environment.'
[[ -x "$BASE/.venv/bin/python" ]] || fail 'Missing working venv.'
systemctl is-active --quiet banking-api || fail 'API must be running before deployment.'
ready || fail 'API not ready before deployment.'

WORK=$(mktemp -d /var/tmp/mini-banking-install.XXXXXXXX)
mkdir "$WORK/new"
tar -xzf "$BUNDLE" -C "$WORK/new" --no-same-owner
[[ -f "$WORK/new/uv.lock" && -f "$WORK/new/pyproject.toml" ]] || fail 'Missing lockfile/project metadata.'
[[ -f "$WORK/new/src/banking/__main__.py" && -f "$WORK/new/scripts/fault/network_partition.py" ]] || fail 'Incomplete release.'
# Keep this rollout source-only. A changed dependency lock requires a separate vetted upgrade.
cmp -s "$BASE/uv.lock" "$WORK/new/uv.lock" || fail 'uv.lock differs from active API. Upgrade dependencies separately before source deployment.'

install -d -o root -g root -m 0700 "$BACKUPS"
BACKUP="$BACKUPS/${ROLE}-$(date +%Y%m%d-%H%M%S).tar.gz"
managed=(src scripts tests docs infra diagram pyproject.toml README.md Makefile .env.example .gitignore .pre-commit-config.yaml uv.lock pyrightconfig.json)
old=()
for p in "${managed[@]}"; do
    [[ ! -e "$BASE/$p" ]] || old+=("$p")
done
tar -czf "$BACKUP" -C "$BASE" "${old[@]}"
echo "ROLLBACK BACKUP: $BACKUP"

systemctl stop banking-api
UPDATED=1
for p in "${managed[@]}"; do
    rm -rf -- "$BASE/$p"
done
# The archive consists only of source and configuration examples (no secrets or .venv).
tar -xzf "$BUNDLE" -C "$BASE" --no-same-owner
chown -R banking:banking "$BASE/src" "$BASE/scripts" "$BASE/tests" "$BASE/docs" "$BASE/infra" "$BASE/diagram"

# Existing interpreter and installed runtime dependencies survive this source upgrade.
# Verify requirements have not drifted; no root-owned Python interpreter is created.
UV=''
for candidate in /home/ariyan/.local/bin/uv /usr/local/bin/uv /usr/bin/uv /root/.local/bin/uv; do
    if [[ -x "$candidate" ]]; then UV="$candidate"; break; fi
done
[[ -n "$UV" ]] || fail 'uv not found; rollback will be attempted.'
"$UV" sync --project "$BASE" --locked --no-dev \
    --python "$BASE/.venv/bin/python" --no-managed-python
chown -R banking:banking "$BASE/.venv"

# Reuse the already installed unit, which explicitly points to the flat directory.
if grep -Fq '/v0.' "$UNIT"; then fail 'Old release path still present in unit.'; fi
systemctl start banking-api
ready || fail 'New API did not become ready.'
echo "PASS | $ROLE live on $BASE"
UPDATED=0
rm -rf --one-file-system -- "$WORK"
trap - EXIT
