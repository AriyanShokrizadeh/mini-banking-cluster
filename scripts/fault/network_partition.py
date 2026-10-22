"""Manage a temporary network partition on a lab VM.

Run on VM1. Rules use a dedicated nftables table and a
systemd timer schedules automatic recovery.
"""

import argparse
import ipaddress
import json
import os
import shutil
import subprocess
import sys

TABLE = "mini_banking_fault"
RESTORE_UNIT = "mini-banking-fault-restore"


def valid_ip(value: str) -> str:
    try:
        ip = ipaddress.IPv4Address(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Invalid IPv4 address") from None

    documentation_ranges = (
        "192.0.2.0/24",
        "198.51.100.0/24",
        "203.0.113.0/24",
    )

    if (
        not ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or any(ip in ipaddress.ip_network(net) for net in documentation_ranges)
    ):
        raise argparse.ArgumentTypeError("Use a private IPv4 address")

    return str(ip)


def is_root() -> bool:
    return getattr(os, "geteuid", lambda: -1)() == 0


def run(
    *command: str,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
        check=check,
    )


def local_ips() -> set[str]:
    devices = json.loads(run("ip", "-j", "-4", "address", "show").stdout)

    return {
        address["local"]
        for device in devices
        for address in device.get("addr_info", [])
        if address.get("family") == "inet"
    }


def build_rules(peers: list[str]) -> str:
    incoming = "\n".join(f"    ip saddr {ip} drop" for ip in peers)
    outgoing = "\n".join(f"    ip daddr {ip} drop" for ip in peers)

    return f"""table inet {TABLE} {{
  chain input {{
    type filter hook input priority -5; policy accept;
{incoming}
  }}
  chain output {{
    type filter hook output priority -5; policy accept;
{outgoing}
  }}
}}
"""


def table_exists() -> bool:
    result = run("nft", "list", "table", "inet", TABLE, check=False)

    if result.returncode == 0:
        return True
    if "No such file or directory" in result.stderr:
        return False

    raise RuntimeError(result.stderr.strip() or "Cannot inspect fault table")


def restore() -> None:
    if table_exists():
        run("nft", "delete", "table", "inet", TABLE)

    run("systemctl", "stop", f"{RESTORE_UNIT}.timer", check=False)
    print("Partition removed.")


def apply(peers: list[str], duration: int) -> None:
    if table_exists():
        raise RuntimeError("Fault already active. Restore it first.")

    nft = shutil.which("nft")
    if not nft:
        raise RuntimeError("nft is required")

    rules = build_rules(peers)
    run("nft", "-c", "-f", "-", input_text=rules)
    run(
        "systemd-run",
        "--collect",
        f"--unit={RESTORE_UNIT}",
        f"--on-active={duration}s",
        nft,
        "delete",
        "table",
        "inet",
        TABLE,
    )

    try:
        run("nft", "-f", "-", input_text=rules)
    except Exception:
        if not table_exists():
            run("systemctl", "stop", f"{RESTORE_UNIT}.timer", check=False)
        raise

    print(f"Partition applied. Recovery scheduled in {duration}s.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "apply", "status", "restore"))
    parser.add_argument("--self-ip", type=valid_ip)
    parser.add_argument("--peer", action="append", type=valid_ip, default=[])
    parser.add_argument("--gateway-ip", type=valid_ip)
    parser.add_argument("--duration", type=int, default=120)
    parser.add_argument("--acknowledge-disruption", action="store_true")
    args = parser.parse_args()

    if args.action == "status":
        if table_exists():
            print(run("nft", "list", "table", "inet", TABLE).stdout)
        else:
            print("No active fault rules.")
        return 0

    if args.action == "restore":
        if not is_root():
            parser.error("Restore requires sudo")
        restore()
        return 0

    peers = list(dict.fromkeys(args.peer))

    if not args.self_ip or not args.gateway_ip or not peers:
        parser.error("--self-ip, --gateway-ip and --peer are required")

    if args.self_ip not in local_ips():
        parser.error("--self-ip is not configured on this VM")

    if args.self_ip == args.gateway_ip or {args.self_ip, args.gateway_ip} & set(peers):
        parser.error("Self IP and management gateway cannot be blocked")

    if not 30 <= args.duration <= 300:
        parser.error("--duration must be between 30 and 300 seconds")

    print(build_rules(peers), end="")

    if args.action == "plan":
        return 0

    if not is_root() or not args.acknowledge_disruption:
        parser.error("Apply requires sudo and --acknowledge-disruption")

    apply(peers, args.duration)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"Fault operation failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
