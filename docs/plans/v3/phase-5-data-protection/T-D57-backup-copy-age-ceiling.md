# T-D57 — Maximum copy age: 37 days

- **Phase**: 5 — Data-protection quick wins
- **Parallel-safe**: no
- **Depends on**: T-D56, T-D19a
- **References**: [ADR-0078](../../../adr/0078-v3-data-protection-quick-wins.md) §4, [ADR-0071](../../../adr/0071-production-startup-migrations.md)

## Context

Worst-case copy lifetime today is ~60 days (Litestream 30 d + noncurrent 30 d), pre-migration backups have no age limit, drill copies linger. v4 erasure (ADR-0083) promises a bound; this task establishes it.

## Deliverables

1. `terraform/main.tf`: `lifecycle_days = 7` for the durability bucket (state bucket unchanged).
2. `db/startup_migrate.py`: prune `<db dir>/backups/*.pre-migrate-*` older than `backup_max_age_days - 7` (= 30) **in addition to** keep-newest-3 (both rules; whichever deletes more). New setting `backup_max_age_days` (default 37, validator 7..365).
3. `restore-from-prod.tpl` + drill workflow: delete moved-aside / restored DB copies at the end of the run (success or failure, `trap`).
4. `docs/requirements.md` §6.5 records the 37-day ceiling (done in this docs change; verify wording on landing).
5. `runbooks/data-inventory.md` (T-D61) references the ceiling.

## Acceptance criteria

- Unit: pruning keeps newest 3 but removes any older than 30 days; idempotent.
- `terraform plan` shows only the lifecycle change.
- Drill run leaves no extra `*.db*` files under `/data` (asserted in the workflow).

## Validation hook

```sh
just test tests/unit/db/test_startup_migrate.py -k prune
cd terraform && terraform plan -var-file=envs/drill/terraform.tfvars
```
