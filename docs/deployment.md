# Four-VM release (existing lab)

> **Clean replacement:** The new RAR-derived `mini-banking-cluster-four-vm-clean.tar.gz` includes `uv.lock` and a safe replacement wrapper. For deleting old source after deployment, follow [`scripts/deploy/README.md`](../scripts/deploy/README.md), not the legacy in-place ZIP instructions below. Live YugabyteDB data must be preserved.


This project is configured for the established cluster:

| VM | Host | Purpose | Managed path |
| --- | --- | --- | --- |
| VM1 | `192.168.200.128` | YugabyteDB + Banking A | `/opt/mini-banking-releases` |
| VM2 | `192.168.200.129` | YugabyteDB + Banking B | `/opt/mini-banking-releases` |
| VM3 | `192.168.200.132` | YugabyteDB third replica | `/var/lib/yugabyte/cluster` |
| VM4 | `192.168.200.130` | HAProxy + demos | `~/projects/mini-banking-cluster` |

**This is a source-only rolling deployment of the existing cluster**, not a fresh YugabyteDB installation. It does not initialize schemas, alter `banking.env`, edit financial balances or delete the cluster data. It preserves flat API paths and existing `.venv` directories. The new project deliberately requires the **same** `uv.lock` as the installed API versions; a changed lock must be tested and deployed separately.

## One-time source update on VM4

Extract the provided updated ZIP **over** the existing VM4 project, rather than deleting it. The ZIP does not contain `uv.lock`, `.venv`, protected configuration or financial reports; keep those files from the working VM4 project. For an archive with top-level `mini-banking-cluster/`:

```bash
unzip -oq ~/Downloads/mini-banking-cluster-4vm-ready.zip -d ~/projects/
cd ~/projects/mini-banking-cluster
./scripts/deploy/prepare_four_vms.sh check
```

If the archive is given a different filename, use that filename instead. Never run a blanket `rm -rf` on the existing VM4 project; the existing `uv.lock` and `.venv` must survive.

## Rolling deployment

Open consoles for all four VMs. Confirm the healthy three-master YugabyteDB cluster, verify SSH to VM1–VM3 and working interactive sudo on VM1/VM2. On VM4:

```bash
./scripts/deploy/prepare_four_vms.sh apply
```

The script checks all four nodes, runs VM4 unit tests, asks for `DEPLOY`, sends a source-only bundle to VM2 then VM1, and verifies both APIs and HAProxy. It uses the already-installed systemd units and the flat path, backs up pre-deployment source to `/var/backups/mini-banking-deploy/`, and attempts source rollback if an API fails readiness. An unexpected active working directory or systemd override **stops** installation. No automatic VM3 database restart is performed.

If any node fails readiness, inspect `systemctl status banking-api` and `journalctl -u banking-api`; do not proceed to removing backups or forcing the second update.

## Fixed demo accounts and removal of old artifacts

After the release passes its checks on VM4:

```bash
./scripts/demos/run.sh prepare
./scripts/deploy/prepare_four_vms.sh cleanup-preview
./scripts/deploy/prepare_four_vms.sh cleanup-apply
```

Cleanup only removes **named, disposable source-stage paths and transfer archives**, never running services, accounts, YugabyteDB files, `.venv`, the canonical project or rollback archives. The cleanup command requires `CLEAN-OLD-STAGES` confirmation. Inspect preview first.

For past `DEMO_*` **database rows**, use a separate, opt-in account cleanup with a JSON history snapshot:

```bash
./scripts/demos/run.sh cleanup
./scripts/demos/run.sh cleanup-execute
```

This targets only the explicitly named retired IDs in `scripts/setup/cleanup_legacy_demo.py`, not other accounts. Run it only after financial reconciliation and a real YugabyteDB backup. Permanent removal of ledger history is not equivalent to reversing transactions; keep snapshots and audit evidence. Core accounts `A1001` and `A1002` are never deleted.

## One-command demonstrations on VM4

```bash
./scripts/demos/run.sh health
./scripts/demos/run.sh all
./scripts/demos/run.sh durability
./scripts/demos/run.sh failover
./scripts/demos/run.sh partition
```

Disruptive demos require interactive approval (`RUN`) and working SSH/sudo access. Review `scripts/demos/README.md` for the complete commands, evidence and manual recovery steps.
