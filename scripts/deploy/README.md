# Four-VM setup

Execute from **VM4** only:

```bash
./scripts/deploy/prepare_four_vms.sh check
./scripts/deploy/prepare_four_vms.sh apply
./scripts/deploy/prepare_four_vms.sh cleanup-preview
./scripts/deploy/prepare_four_vms.sh cleanup-apply
```

`check` is read-only. `apply` validates the active services, runs unit tests and asks for confirmation before updating **VM2 first, VM1 second**; VM3's live YugabyteDB data is never modified. Both API nodes keep `/opt/mini-banking-releases` with no version-named child directory. A source backup for rollback is saved on each API node. Only compatible (identical) `uv.lock` is accepted.

Cleanup is a separate explicit step that removes selected obsolete stage directories and transport archives after verifying all four nodes, not the financial ledger or recovery backups. Read [deployment](../../docs/deployment.md) for prerequisites and limits.

## Replace the old VM4 project with an unpacked new release

Do **not** delete active code before the new release passes preflight. The clean
replacement wrapper upgrades VM2 then VM1, promotes the new VM4 source, and
retains a rollback copy of the old VM4 source until cleanup is explicitly
requested. VM3 runs YugabyteDB and must not have its data directory deleted.

Upload `mini-banking-cluster-four-vm-clean.tar.gz` to VM4, then:

```bash
mkdir -p ~/projects/mini-banking-stage-new
# Extract the archive into the new, empty staging directory:
tar -xzf ~/Downloads/mini-banking-cluster-four-vm-clean.tar.gz \
  -C ~/projects/mini-banking-stage-new
cd ~/projects/mini-banking-stage-new
./scripts/deploy/replace_four_vms.sh check
./scripts/deploy/replace_four_vms.sh install
```

After final verification, optionally remove old source directories:

```bash
cd ~/projects/mini-banking-cluster
./scripts/deploy/replace_four_vms.sh cleanup-preview
./scripts/deploy/replace_four_vms.sh cleanup-apply
```

Financial accounts, ledger, environment files and YugabyteDB volumes are
**not** deleted by source cleanup. Remove retired demo accounts separately
using `./scripts/demos/run.sh cleanup` followed by `cleanup-execute` only after
a YugabyteDB backup and explicit financial audit.
