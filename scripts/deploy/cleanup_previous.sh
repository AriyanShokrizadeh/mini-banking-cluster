#!/usr/bin/env bash
# Explicit, conservative removal of disposable leftovers only (no DB, no service files).
set -euo pipefail
MODE="${1:-preview}"
ROLE="${2:-}"
[[ "$MODE" == preview || "$MODE" == apply ]] || { echo 'Usage: cleanup_previous.sh {preview|apply} {api|database|gateway}' >&2; exit 2; }
[[ "$ROLE" == api || "$ROLE" == database || "$ROLE" == gateway ]] || exit 2
if [[ "$MODE" == apply && $EUID -ne 0 ]]; then echo 'sudo required to apply cleanup' >&2; exit 2; fi
if [[ "$ROLE" == api ]]; then
    [[ "$(systemctl show banking-api -p WorkingDirectory --value)" == /opt/mini-banking-releases ]] || exit 2
    systemctl is-active --quiet banking-api || exit 2
elif [[ "$ROLE" == database ]]; then
    systemctl is-active --quiet yugabyted || exit 2
else
    systemctl is-active --quiet haproxy || exit 2
fi
safe_remove() {
    local path="$1"
    [[ -e "$path" && ! -L "$path" ]] || return 0
    [[ ! -d "$path" ]] || { mountpoint -q "$path" && { echo "SKIP mounted: $path"; return 0; }; }
    echo "$MODE | $path"
    if [[ "$MODE" == apply ]]; then
        if [[ -d "$path" ]]; then rm -rf --one-file-system -- "$path"; else rm -f -- "$path"; fi
    fi
}
# Named staging and legacy items only. Never delete an active project, backups, or the service venv.
for home in /home/ariyan /home/VMWare; do
    [[ -d "$home" ]] || continue
    for path in "$home"/mini-banking-stage-* "$home"/mini-banking-demo-stage-* \
                "$home"/projects/mini-banking-stage-* \
                "$home"/projects/mini-banking-cluster-legacy-* \
                "$home"/projects/mini-banking-venv-backup-* \
                "$home"/projects/stage-20261022; do
        safe_remove "$path"
    done
    for archive in "$home"/mini-banking-v0.7.0-httpx2-release.tar.gz \
                   "$home"/Downloads/mini-banking-v0.7.0-httpx2-release.tar.gz; do
        safe_remove "$archive"
    done
done
if [[ "$ROLE" == api ]]; then
    for path in /opt/mini-banking-releases/v0.7.0-*; do
        safe_remove "$path"
    done
    for path in /etc/systemd/system/banking-api.service.d/50-httpx2-release.conf.disabled \
                /etc/systemd/system/banking-api.service.pre-httpx2.bak; do
        safe_remove "$path"
    done
fi
# VM3 once held an obsolete copy of the API sources. Remove only when no
# active service references that path, never any YugabyteDB installation/data.
if [[ "$ROLE" == database ]]; then
    LEGACY=/opt/mini-banking-cluster
    if [[ -d "$LEGACY" && ! -L "$LEGACY" ]]; then
        if systemctl show yugabyted -p ExecStart -p ExecStop -p WorkingDirectory --value | grep -Fq "$LEGACY"; then
            echo "SKIP referenced by YugabyteDB service: $LEGACY"
        elif pgrep -af "$LEGACY" | grep -v -E 'cleanup_previous[.]sh|pgrep -af' >/dev/null; then
            echo "SKIP running process references: $LEGACY"
        else
            safe_remove "$LEGACY"
        fi
    fi
fi
if [[ "$ROLE" == gateway ]]; then
    if [[ -x /home/VMWare/projects/mini-banking-cluster/.venv/bin/python ]]; then
        safe_remove /home/VMWare/projects/mini-banking-cluster/.venv.before-promotion
    fi
    for path in /etc/haproxy/haproxy.cfg.banking-b-stage \
                /etc/haproxy/haproxy.cfg.before-httpx2-cutover; do
        safe_remove "$path"
    done
fi
if [[ "$MODE" == preview ]]; then echo 'PREVIEW ONLY — no changes.'; fi
