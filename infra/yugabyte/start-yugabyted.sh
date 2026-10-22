#!/usr/bin/env bash
set -euo pipefail

# Start one YugabyteDB node under systemd supervision.

# Required configuration
: "${YB_NODE_IP:?YB_NODE_IP is required}"
: "${YB_CLOUD_LOCATION:?YB_CLOUD_LOCATION is required}"

# Defaults
YB_HOME="${YB_HOME:-/opt/yugabyte/current}"
YB_BASE_DIR="${YB_BASE_DIR:-/var/lib/yugabyte/cluster}"
YB_FAULT_TOLERANCE="${YB_FAULT_TOLERANCE:-zone}"

YUGABYTED="$YB_HOME/bin/yugabyted"


die() {
    echo "Error: $*" >&2
    exit 2
}

# Validate configuration
case "$YB_NODE_IP" in
    127.*|0.0.0.0|192.0.2.*|198.51.100.*|203.0.113.*)
        die "YB_NODE_IP must be a valid VM address."
        ;;
esac

[[ "$YB_CLOUD_LOCATION" == *.*.* ]] ||
    die "YB_CLOUD_LOCATION must be cloud.region.zone."

[[ "$YB_FAULT_TOLERANCE" == "zone" ]] ||
    die "Only zone-level fault tolerance is supported."

# Build startup arguments
args=(
    start
    "--advertise_address=$YB_NODE_IP"
    "--base_dir=$YB_BASE_DIR"
    "--cloud_location=$YB_CLOUD_LOCATION"
    "--fault_tolerance=$YB_FAULT_TOLERANCE"
    "--background=false"
)

# Join an existing cluster if configured
if [[ -n "${YB_JOIN_IP:-}" ]]; then
    case "$YB_JOIN_IP" in
        "$YB_NODE_IP"|127.*|0.0.0.0|192.0.2.*|198.51.100.*|203.0.113.*)
            die "YB_JOIN_IP must reference another cluster node."
            ;;
    esac

    args+=("--join=$YB_JOIN_IP")
fi

# Preview the command without starting the service
if [[ "${1:-}" == "--dry-run" ]]; then
    printf '%q ' "$YUGABYTED" "${args[@]}"
    printf '\n'
    exit 0
fi

# Start YugabyteDB
[[ -x "$YUGABYTED" ]] ||
    die "YugabyteDB executable not found: $YUGABYTED"

exec "$YUGABYTED" "${args[@]}"
