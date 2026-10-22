# One-command demos (VM4)

Every recording uses one of **five fixed lab accounts**. Successful scenarios
restore balances to 1000 through auditable compensating transactions; they do
not create new accounts or erase financial history.

## One-time preparation

On VM4, with the existing Python environment and SSH/sudo access to VM1:

```bash
./scripts/demos/run.sh prepare
```

This installs only the two lab-admin scripts on VM1 and creates any missing
`DEMO_LAB_*` accounts without changing existing balances or restarting APIs.
The existing `fault/` tools must already be installed on VM1/VM2. Copy
`config.env.example` to `config.env` only if your lab addresses differ.

## Run a scenario

```bash
./scripts/demos/run.sh health
./scripts/demos/run.sh basic
./scripts/demos/run.sh errors
./scripts/demos/run.sh idempotency
./scripts/demos/run.sh concurrency
./scripts/demos/run.sh atomicity
./scripts/demos/run.sh durability
./scripts/demos/run.sh logs
./scripts/demos/run.sh all
./scripts/demos/run.sh failover
./scripts/demos/run.sh partition
```

- `all` runs health, basic transactions, idempotency, error handling,
  concurrency, and local SQLite atomicity checks.
- `durability` restarts only Banking B's API. `failover` stops and restores
  Banking A's API after three deposits.
- `partition` applies a bounded 180-second nftables fault on VM1, runs
  separate minority/majority quorum probes, then restores networking.
  Financial results alone do not prove Raft quorum.

**Do not run disruptive demos on production VMs.** `failover` and `partition`
require typing `RUN` in an interactive terminal, working SSH/sudo access,
and an accessible VMware console. Do not run demos concurrently.

## Reconciliation and cleanup

Reports and request IDs are saved to `demo-results/`. An unknown write outcome
(timeout or HTTP 5xx) can leave an account blocked. Check **every request ID**
against the database audit before explicitly unblocking it:

```bash
./scripts/demos/run.sh reconcile DEMO_LAB_BASIC
./scripts/demos/run.sh reset
./scripts/demos/run.sh cleanup
./scripts/demos/run.sh cleanup-execute
./scripts/demos/run.sh reset-core
```

`reset` compensates the fixed lab balances. `cleanup` is a read-only preview;
`cleanup-execute` requires a confirmation phrase and backs up the **named,
retired** `DEMO_*` accounts and history before removing them. It never deletes
seeded `A1001/A1002` or the reusable pool. `reset-core` is optional and
separately restores seeded accounts through logged transactions.

Source files and local tests never clean up records on running VMs. For details
on evidence and emergency recovery, see [experiments](../../docs/experiments.md).
