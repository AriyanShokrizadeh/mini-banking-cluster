#!/usr/bin/env bash
set -euo pipefail


source /etc/os-release

printf '\n=== System Information ===\n'
printf 'OS: %s\n' "$PRETTY_NAME"
printf 'Architecture: %s\n' "$(uname -m)"

printf '\n=== CPU ===\n'
nproc
printf '\n=== Memory ===\n'
free -h

printf '\n=== Disk Space ===\n'
df -h / /var

printf '\n=== Clock ===\n'
timedatectl show -p NTPSynchronized --value 2>/dev/null || true

printf '\n=== Network Interfaces ===\n'
ip -br -4 addr

printf '\n=== System Limits ===\n'
printf 'Open files: %s\n' "$(ulimit -n)"
printf 'Processes: %s\n' "$(ulimit -u)"

printf '\n=== Listening TCP Ports ===\n'
ss -ltn | sed -n '1,40p'

printf '\n=== Required Ports ===\n'
printf '%-18s %s\n' \
    'Cluster RPC:'  '7100, 9100, 7000, 9000' \
    'YSQL:'         '5433' \
    'Yugabyted:'    '15433' \
    'Banking API:'  '8000' \
    'HAProxy:'      '8080'

printf '\nPreflight complete. No system changes were made.\n'
