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

## Readiness review 2026-11-18

Scope: can the first `restore-drill.yml` dispatch (from `main`) pass on an ADR-0111 agent-managed drill host, with the v3.0.2 Litestream changes (ADR-0114)? Static review only; nothing was dispatched.

**Verdict (superseded by run 44330551119 below): no blocking bug found by static review.** The first run then failed on the readiness probe.

### 1. Host agent vs restore-from-prod
- `bp_agent.converge()` returns early when `applied-generation == config generation` and `docker inspect {{.Config.Image}}` of the app container equals the desired ref. A stopped container still inspects with the same image, so a converged agent does nothing while `app` + `litestream` are stopped. It never brings compose up on its own in that state.
- The agent writes only managed files under `/etc/budget-planner` and its state dirs. It never touches `/data`. `restore-from-prod` writes only under `/data` (and `/run`), so there is no file contention.
- Residual risk (low): if the first convergence failed and the agent is in back-off, a retry could run `compose up -d` while the restore has the stack stopped. The workflow only waits for `cloud-init status --wait`. Mitigation, outside my ownership: before the restore step, wait until `/.well-known/bp-deploy-status.json` has `state: ok`. Check it by hand at the start of the run.

### 2. Litestream marker and generation (ADR-0114) — can the drill write to the prod bucket?
- **No path writes to prod.** The running `litestream replicate` reads `/etc/budget-planner/litestream.yml`, rendered with `var.bucket_name` (the drill's own bucket) and the drill write key (`litestream.env`). The prod bucket appears only in the throw-away config inside `restore-from-prod`, which is passed to `litestream restore` (read-only) with the read-only key; the script also refuses `source bucket == drill bucket` and `restore key == drill write key`. The one-shot `litestream-restore` compose service uses the drill-bucket config.
- `move_local_db_aside` moves `budget.db*` and `.budget.db-litestream`. The marker `/data/.litestream-age-generation` does not match `budget.db*`, so it stays. After the restore, `litestream replicate` starts with the marker present (no forced regeneration) and no meta dir, so Litestream creates a fresh generation in the drill bucket anyway. A marker-less host would only `rm -rf` an already absent meta dir. There is no interaction that could target the prod path.
- Note: the drill's `litestream.yml` uses the prod age recipient (same key pair as prod, by design), so the drill's own generations in its bucket are encrypted and decryptable with the prod identity.

### 3. Age identity on the restore path
- `restore_from_prod` reads the first `AGE-SECRET-KEY-` line from `/etc/budget-planner/litestream-age.key` (written from `litestream_age_identity`, which `restore-drill.yml` sets from the `LITESTREAM_AGE_IDENTITY` secret = the PROD identity), exports it, passes `-e LITESTREAM_AGE_IDENTITY` to the container, and the throw-away config has `age.identities: [${LITESTREAM_AGE_IDENTITY}]`. Preflight aborts when the key file is missing. So generation `2901fbd3873a6696` (encrypted) can be decrypted. The older plaintext generations are not read: `restore` picks the newest generation.
- Verified by hand before the run: the `LITESTREAM_AGE_IDENTITY` and `LITESTREAM_AGE_RECIPIENT` secrets exist in the `restore-drill` environment and are the pair prod uses (do not print them).

### 4. Other checks
- `trap ... RETURN` in `restore_from_prod` fires once, at that function's return (tested in bash 5); no `set -u` unbound-variable fallout later.
- T-D57 check in the workflow allows `/data/.budget.db-litestream*`; the moved-aside dir and pre-migration backups are removed by the EXIT trap.
- Watch in the first run: duration (RTO), the `restoring from s3://...` and `integrity_check=ok` lines, and that the Verify steps pass.

### Restore-log entry template (fill after the run, then append to `../runbooks/restore-log.md`, newest first)

`scripts/ci/litestream_cleanup.py` accepts an entry as green only if it has a `## YYYY-MM-DD` heading, a `- **Result**: pass` line and a `- **integrity_check**: ok` line (case-insensitive, first token after the colon). The entry date must be on or after the day of the first encrypted snapshot of the newest encrypted generation.

```
## 2026-MM-DD
- **Operator**: <handle or system-restore-drill>
- **Env**: drill-scratch-vm
- **Trigger**: manual-ad-hoc
- **Duration**: <mm'ss"> (terraform apply -> green /ready)
- **Audit rows (prod)**: <count>, max_id=<n>, max_created_at=<utc>
- **Audit rows (restored)**: <count>, max_id=<n>
- **integrity_check**: ok
- **Recovery point**: latest (generation 2901fbd3873a6696 or newer; <utc of last restored WAL segment>)
- **Result**: pass
- **Notes**: workflow run <url>; prod row counts read-only from prod via the operator; deviations: <none>.
```

### Run 44330551119: failed, cause, fix
- **Result:** the restore itself worked. Generation `2901fbd3873a6696` restored (snapshot plus WAL 0..2), `integrity_check=ok`, litestream and app started, migrations `applied: []`. The app was healthy throughout (`GET /ready 200` from inside the container every 30 s). Yet `start_stack_and_wait` ended with `ERROR: /ready did not report ok within 120s`, with no `ready.status=` line.
- **Cause 1, wrong TLS name.** The probe used `https://localhost/ready` with `--resolve localhost:443:127.0.0.1 -k`. Caddy defines a site only for the host name, so SNI `localhost` has no certificate and the handshake failed (`-k` skips verification, not the missing certificate).
- **Cause 2, wrong expected status.** The script required `.status == "ok"`, but `/ready` returns `{"status":"ready","db":"ok"}` (`web/routers/health.py`). It would have failed even with a working handshake.
- **Fix (T-D40-FIX).** `restore-from-prod.tpl` now probes `https://<hostname>/ready` with `--resolve <hostname>:443:127.0.0.1` and normal TLS verification, so the Caddy proxy path is proven too. The `hostname` template variable is passed from `modules/compute/user_data.tf`. It requires `status == "ready"` and `db == "ok"`, and logs the curl error or the (truncated) body on every failed attempt, so the next failure is diagnosable. Tests: `tests/unit/deploy/test_restore_ready_check.py`.
- **Next:** re-dispatch `restore-drill.yml` from `main` after this lands. The workflow's own verify step is fixed separately.

### Run 44340976282: restore, integrity and ready all ok; failed on RETURN-trap bug; fixed
- Generation `2901fbd3873a6696` restored, `integrity_check=ok`, `ready.status=ready ready.db=ok` (attempt 3). Then `restore-from-prod: line 208: cfg: unbound variable` (exit 1) after the complete log. Cause: `trap ... RETURN` set inside `restore_from_prod` persisted and fired when `main` returned, where `local cfg` was out of scope (`set -u`). Fix (T-D40-FIX2): temp config is a global `RESTORE_CFG` removed by the `cleanup_copies` EXIT trap (also covers failure paths); no RETURN traps remain. Tests reproduce the failure in `ubuntu:24.04` (bash 5.2) when Docker is available.

### Run 44346338885: restore, ready and integrity green; T-D57 check found tmp-wal/shm; fixed
- Run 44346338885 (trunk 8f466a5): restore, ready and integrity green; the "Verify no extra DB copies remain (T-D57)" step found `/data/budget.db.tmp-wal` and `/data/budget.db.tmp-shm`. Cause: `litestream restore` builds the DB in `budget.db.tmp`, applies the WAL, renames it to `budget.db` ("renaming database from temporary location") and leaves the tmp sidecars. Docker repro (`litestream/litestream:0.3.14`, file replica): `budget.db` passes `integrity_check`, `budget.db.tmp-wal` is 0 bytes, `budget.db.tmp-shm` is 32 KiB. Fix (T-D40-FIX3): `remove_restore_tmp_sidecars` runs before the integrity check, logs the removal, and dies (keeping the files) if the tmp-wal is non-empty. The workflow's T-D57 check is unchanged. Tests: `tests/unit/deploy/test_restore_ready_check.py`.
- **Next:** re-dispatch `restore-drill.yml` from `main` after this lands.
