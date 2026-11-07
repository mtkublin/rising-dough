# T-D40 — First backup restore drill

> **Superseded by ADR-0099 (2026-11-07).** Drill applies for the restore drill run through `drill.yml` / `restore-drill.yml`, not a local `terraform apply -var-file=...`. Current procedure: [`runbooks/drill.md`](../runbooks/drill.md) and [`runbooks/restore.md`](../runbooks/restore.md). The text below is the original spec, kept as written.

- **Phase**: 4 — Validation
- **Sequential**: must complete before production is declared live
- **Depends on**: T-D27 (prod up and taking writes)
- **References**: ADR-0034 §5

## Context

Litestream replication is only as good as the restore. The first drill proves that the Scaleway Object Storage bucket contents can be reconstructed into a working DB on a scratch VM, within the RTO target of < 60 minutes.

## Procedure

1. **Snapshot the primary state** (read-only on prod):
   - `ssh operator@budget.<domain> "sqlite3 /data/budget.db 'SELECT count(*) FROM audit_log; SELECT max(id) FROM audit_log;'"`
   - Record the two numbers in the PR description.
2. **Create a read-only IAM credential** for the prod bucket (one-shot, via Scaleway console or an auxiliary Terraform output). Scope: `GetObject`, `ListBucket` on `budget-planner-prod-pl-waw` only.
3. **Provision a disposable drill environment** with that credential:
   ```sh
   cd terraform
   terraform workspace new drill-restore-$(date +%Y%m%d)
   terraform apply -var-file=envs/drill/terraform.tfvars \
     -var scw_access_key_restore=<ro-key-id> \
     -var scw_secret_key_restore=<ro-key-secret>
   ```
   The compute module reads the `_restore` variables and renders a Litestream config pointed at the **prod** bucket.
4. **Trigger restore on first boot**: cloud-init runs `litestream restore -o /data/budget.db s3://budget-planner-prod-pl-waw/db` before starting the app container.
5. **Verify**:
   - `sqlite3 /data/budget.db "PRAGMA integrity_check;"` → `ok`.
   - `sqlite3 /data/budget.db "SELECT count(*), max(id) FROM audit_log;"` → matches step 1 within one minute's worth of new writes.
   - `curl -fsS https://drill-restore-....<domain>/ready | jq .` → `"db": "ok"`.
   - `curl -fsS https://drill-restore-....<domain>/health` → 200.
6. **Tear down**: `terraform destroy` + `terraform workspace delete drill-restore-YYYYMMDD`. Revoke the read-only credential.
7. **Record** the drill in `../runbooks/restore-log.md`:

   ```
   | Date       | Duration | Audit rows (prod) | Audit rows (restored) | integrity_check | Operator | Notes |
   |------------|----------|-------------------|------------------------|------------------|---------|-------|
   | 2026-11-01 | 24m 11s  | 18 423            | 18 423                 | ok               | mkublin | first drill |
   ```

## Acceptance criteria

- End-to-end time < 60 minutes from `terraform apply` to green `/ready`.
- Audit-row count matches exactly (allowing for new rows written after step 1).
- `integrity_check` returns `ok`.
- Read-only credential revoked and drill environment destroyed within the same working window.
- Runbook entry committed in the same PR.

## Validation hook

```sh
# After full drill run:
cat docs/plans/v3/runbooks/restore-log.md | tail -3
```

Expect: today's dated row with `ok` and matching counts.
