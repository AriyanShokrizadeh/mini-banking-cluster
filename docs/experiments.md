# Experiments and evidence

Run the demos from VM4 with `./scripts/demos/run.sh <scenario>`. See the
[demo command reference](../scripts/demos/README.md) for setup, commands,
reconciliation, and cleanup. The same five lab accounts are reused; their
balances are restored through recorded compensating transactions, not direct
SQL updates or ledger deletion.

## What each experiment establishes

| Experiment | Evidence | Limitation |
| --- | --- | --- |
| Basic, idempotency, errors, concurrency | API responses and balances | Not a distributed fault test |
| Atomicity | Local SQLite rollback test | Does not inject a fault in YugabyteDB |
| Durability | Successful write survives a Banking B API restart | Does not restart a database node |
| Failover | Gateway switches from Banking A to B; request IDs reconciled | Does not prove zero interruption |
| Partition | Financial reconciliation and separate minority/majority write probes | Financial balances alone do not prove Raft quorum |

## Safety and recovery

`failover` and `partition` require an operator, SSH/sudo access, and an
accessible VM console. Never run them unattended or in production. The partition
script schedules an automatic 180-second restoration; the orchestrator also
attempts cleanup in `finally`. If the controller loses connectivity, use the VM1
console:

```bash
sudo python3 /opt/mini-banking-releases/scripts/fault/network_partition.py restore
```

Quorum checks target the disposable `banking_test` database **while the fault is
active**. Reconcile original request IDs and audit committed state after recovery.
A timeout or HTTP 5xx indicates an *unknown outcome*, not a proven rollback.
Do not repeat an uncertain financial operation with a new ID.

Retired demo-account cleanup is always explicit and separate from experiments.
