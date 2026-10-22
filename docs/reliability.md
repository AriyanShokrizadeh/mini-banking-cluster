# Reliability and safety

| Mechanism | Guarantee / limitation |
| --- | --- |
| `SERIALIZABLE` + conditional balance update | Protects concurrent balances; verify on YugabyteDB |
| Request receipt + fingerprint | Same request ID replays a stored result; different payload conflicts |
| Single transaction for balance, operation and ledger | Atomic database effects; HTTP delivery is not guaranteed |
| Bounded SQL retries | Handles known serialization/deadlock failures, not unknown commits |
| HAProxy active/backup, no POST retry | API failover after a health-check detection window |
| YugabyteDB RF=3 | Quorum replication; minority writes may become unavailable |

## Health checks

- `/health/live`: API process is running.
- `/health/db`: simple database connectivity (`SELECT 1`).
- `/health/ready`: commits a write to `health_probes`; does **not** change money.

Readiness can still time out during driver or database faults. HAProxy applies its own timeout. A multi-host database connection can fail over **between connections**, not resume an in-flight transaction.

## Lessons from the lab

During October 2026 testing, a YugabyteDB node showed YSQL metadata/leader-discovery timeouts despite healthy-looking cluster membership. After checking peers, a **single-node restart** restored service; the root cause was not proven. VM service permissions and Fedora SELinux also required environment-specific fixes.

Do not treat restarts as routine repairs. Check quorum and preserve a recovery path; never restart all three database nodes together.

## Operating rules

- Never reinitialize or reseed existing `banking` data.
- Run integration tests against **disposable** `banking_test` only; explicitly opt into test writes.
- Keep environment files and credentials private. Use only `DEMO_...` accounts for recording.
- Treat timeouts and HTTP 5xx as **unknown transaction outcomes**. Reconcile by request ID before retrying.
- Validate balances and ledger after failover or partition recovery.
