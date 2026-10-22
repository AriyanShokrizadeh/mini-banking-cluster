#!/usr/bin/env bash
# Run on VM4 from the extracted NEW release staged under ~/projects.
# Backend upgrades are rolling; old VM4 source is removed only after verification.
set -Eeuo pipefail
umask 077

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
CANON="$HOME/projects/mini-banking-cluster"
MODE="${1:-check}"
UV="${UV_BIN:-$(command -v uv || true)}"
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP="$HOME/projects/mini-banking-rollback-$STAMP"
PROMOTED=0

msg() { printf '\n===== %s =====\n' "$*"; }
fail() { echo "STOP: $*" >&2; exit 1; }

[[ "$MODE" == check || "$MODE" == install || "$MODE" == cleanup-preview || "$MODE" == cleanup-apply ]] ||
    fail 'Usage: replace_four_vms.sh {check|install|cleanup-preview|cleanup-apply}'
[[ "$(id -un)" == VMWare ]] || fail 'Run as the VMWare user on VM4, not root.'
[[ -n "$UV" && -x "$UV" ]] || fail 'Install uv in the VMWare user environment first.'
[[ -f "$ROOT/uv.lock" && -f "$ROOT/pyproject.toml" ]] || fail 'Release archive is incomplete.'

check_project() {
    msg 'VERIFY NEW VM4 PROJECT'
    "$UV" sync --project "$ROOT" --locked --python 3.12
    (cd "$ROOT"
      "$UV" run --locked ruff check .
      "$UV" run --locked ruff format --check .
      "$UV" run --locked pyright
      "$UV" run --locked pytest -q -m 'not cluster'
    )
}

check_cluster() {
    msg 'VERIFY FOUR VM CLUSTER'
    bash "$ROOT/scripts/deploy/prepare_four_vms.sh" check
}

rollback_local() {
    local code=$?
    trap - ERR
    if ((PROMOTED)); then
        echo 'Local promotion failed. Attempting to restore previous VM4 source.' >&2
        if [[ -d "$CANON" && ! -L "$CANON" ]]; then
            mv -- "$CANON" "$HOME/projects/mini-banking-failed-$STAMP" || true
        fi
        if [[ -d "$BACKUP" && ! -L "$BACKUP" ]]; then mv -- "$BACKUP" "$CANON" || true; fi
        echo 'NOTICE: remote API nodes may already have the new source. Inspect service health.' >&2
    fi
    exit "$code"
}

case "$MODE" in
    check)
        check_project
        check_cluster
        echo 'PASS | Preflight completed. No running application source replaced.'
        ;;
    install)
        [[ "$ROOT" != "$CANON" ]] || fail 'Extract the new release to a separate staging directory, not over the active project.'
        [[ "$ROOT" == "$HOME/projects/"* ]] || fail 'Stage the new release under ~/projects on VM4.'
        [[ ! -L "$ROOT" && ! -L "$CANON" ]] || fail 'Symlinked project directories are not supported.'
        [[ ! -e "$BACKUP" ]] || fail "Rollback directory already exists: $BACKUP"
        [[ "$(stat -c %d "$ROOT")" == "$(stat -c %d "$HOME/projects")" ]] ||
            fail 'Staging and canonical projects must be on the same filesystem.'
        check_project
        check_cluster
        echo 'The next step will update Banking B, then Banking A without erasing YugabyteDB.'
        read -r -p 'Type REPLACE-SOURCE to continue: ' answer
        [[ "$answer" == REPLACE-SOURCE ]] || fail 'Cancelled.'
        # This existing tool validates, backs up and rolls back each banking API independently.
        bash "$ROOT/scripts/deploy/prepare_four_vms.sh" apply
        msg 'PROMOTE VM4 NEW PROJECT'
        trap rollback_local ERR
        PROMOTED=1
        if [[ -d "$CANON" ]]; then mv -- "$CANON" "$BACKUP"; fi
        mv -- "$ROOT" "$CANON"
        # Preserve local demo configuration and previous evidence across promotion.
        if [[ -d "$BACKUP" && -f "$BACKUP/scripts/demos/config.env" &&
              ! -e "$CANON/scripts/demos/config.env" ]]; then
            install -m 0600 "$BACKUP/scripts/demos/config.env" "$CANON/scripts/demos/config.env"
        fi
        if [[ -d "$BACKUP/demo-results" ]]; then
            mkdir -p "$CANON/demo-results/previous-$STAMP"
            cp -a "$BACKUP/demo-results/." "$CANON/demo-results/previous-$STAMP/"
        fi
        # Virtualenv entry points may contain absolute paths from the staged location.
        rm -rf --one-file-system -- "$CANON/.venv"
        "$UV" sync --project "$CANON" --locked --python 3.12
        (cd "$CANON" && ./scripts/demos/run.sh health)
        bash "$CANON/scripts/deploy/prepare_four_vms.sh" check
        PROMOTED=0
        trap - ERR
        msg 'DEPLOYMENT COMPLETE'
        echo "Active VM4 project: $CANON"
        if [[ -d "$BACKUP" ]]; then echo "Old VM4 source kept for rollback: $BACKUP"; fi
        echo 'Next: cd ~/projects/mini-banking-cluster && ./scripts/demos/run.sh prepare'
        echo 'After verifying all demos, use: ./scripts/deploy/replace_four_vms.sh cleanup-preview'
        ;;
    cleanup-preview|cleanup-apply)
        [[ "$ROOT" == "$CANON" ]] || fail 'Run cleanup from the promoted canonical project on VM4.'
        bash "$CANON/scripts/deploy/prepare_four_vms.sh" check
        msg 'PREVIEW RETIRED VM4 SOURCE'
        shopt -s nullglob
        backups=("$HOME"/projects/mini-banking-rollback-*)
        for d in "${backups[@]}"; do
            [[ -d "$d" && ! -L "$d" ]] || continue
            if mountpoint -q "$d"; then echo "SKIP mounted: $d"; continue; fi
            echo "old project candidate: $d"
        done
        if [[ "$MODE" == cleanup-apply ]]; then
            read -r -p 'Type DELETE-OLD-PROJECTS to remove old VM4 project backups: ' answer
            [[ "$answer" == DELETE-OLD-PROJECTS ]] || fail 'Cancelled.'
            for d in "${backups[@]}"; do
                [[ -d "$d" && ! -L "$d" ]] || continue
                mountpoint -q "$d" && continue
                rm -rf --one-file-system -- "$d"
                echo "Removed: $d"
            done
        fi
        echo 'The deployment cleanup tool will preview/remove named stages on all four VMs.'
        if [[ "$MODE" == cleanup-apply ]]; then
            bash "$CANON/scripts/deploy/prepare_four_vms.sh" cleanup-apply
        else
            bash "$CANON/scripts/deploy/prepare_four_vms.sh" cleanup-preview
        fi
        ;;
esac
