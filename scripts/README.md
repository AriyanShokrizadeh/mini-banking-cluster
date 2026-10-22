# Scripts

- `demos/run.sh`: the only entrypoint needed on VM4 for routine demonstrations.
- `demos/README.md`: one-time preparation, one-command scenarios, cleanup.
- `setup/prepare_lab.py`: idempotent creation of the fixed lab account pool.
- `setup/cleanup_legacy_demo.py`: audited preview/backup/cleanup of known retired accounts.
- `fault/`: time-bounded network fault and minority quorum probe.
- `checks/`: checks, database/ledger audits, and smoke verification.

No test automatically deletes account history or edits the seeded accounts.
