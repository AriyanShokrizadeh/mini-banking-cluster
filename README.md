# Mini Banking Cluster

A simulated banking API running on two FastAPI servers behind HAProxy, backed by
three YugabyteDB YSQL nodes. Transactions use integer minor units, atomic ledger
updates, and durable idempotency receipts.

## Run demonstrations on VM4

Prepare the fixed lab accounts **once**, then run any scenario with one command:

```bash
./scripts/demos/run.sh prepare
./scripts/demos/run.sh all
./scripts/demos/run.sh durability
./scripts/demos/run.sh failover
./scripts/demos/run.sh partition
```

Demo accounts are reused; successful financial scenarios restore balances using
recorded compensating transactions. Fault scenarios require interactive approval
and a working VM console. See the [demo guide](scripts/demos/README.md) for all
commands, recovery, and cleanup.

## Development

Requires Python 3.12+ and the project's dependencies (including `httpx2`):

```bash
uv sync --group dev
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -q -m 'not cluster'
```

Cluster tests are opt-in and require a separate disposable `banking_test` DB.
Never run fault tests against production or reinitialize an existing database.

## Project map

| Path | Purpose |
| --- | --- |
| `src/banking/` | API, transactions, models, database access |
| `src/client/` | HTTP client and CLI |
| `scripts/demos/` | One-command demos and recovery |
| `scripts/setup/` | Schema and lab-account preparation, controlled cleanup |
| `scripts/fault/` | Bounded network faults and quorum probes |
| `scripts/checks/` | Readiness, ledger, and release checks |
| `infra/` | YugabyteDB, HAProxy and systemd configuration |
| `tests/` | Unit and opt-in integration tests |
| `diagram/` | Architecture and scenario diagrams |

More detail: [architecture](docs/architecture.md),
[deployment](docs/deployment.md), [reliability](docs/reliability.md),
[experiments](docs/experiments.md).

## Existing four-VM lab deployment

With the working VM4 `.venv` and `uv.lock` preserved, run
`./scripts/deploy/prepare_four_vms.sh check`, then
`./scripts/deploy/prepare_four_vms.sh apply` to update the two Banking APIs.
VM3 YugabyteDB is validated but never overwritten. After the release, use
`./scripts/demos/run.sh prepare` once and then the one-command demos.
Legacy files and financial-account cleanup are **separate opt-in steps**;
see [four-VM deployment](docs/deployment.md).

## Clean replacement on the existing four VMs

For an uploaded final release rather than an in-place source update, see
[scripts/deploy/README.md](scripts/deploy/README.md) and use
`replace_four_vms.sh` from a separate staging directory on VM4. Preserve
YugabyteDB cluster data and secrets during deployment.
