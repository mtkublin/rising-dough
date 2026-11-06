# Runbook — Restore from Litestream

Reconstruct `/data/budget.db` from the Scaleway Object Storage replica.

## Context

Litestream streams WAL segments to `s3://budget-planner-prod-pl-waw/db/` every 10 s and takes a daily full snapshot (ADR-0034 §3). Retention is 30 days of WAL + snapshots, giving a 30-day point-in-time recovery window. RPO target is < 15 s; RTO target is < 60 s for the restore itself, < 60 min end-to-end from a cold VM (ADR-0032 §9).

This runbook is for restoring **into the current prod host** (DB corruption, accidental destructive write, bad migration). For restoring into a brand-new VM, use [`disaster-recovery.md`](disaster-recovery.md) instead — it wraps this restore inside a full re-provision.

The monthly automated drill (`.github/workflows/restore-drill.yml`) exercises a variant of this procedure against a scratch VM; see [`restore-log.md`](restore-log.md) for the drill history. When the drill starts the image on the restored copy, the entrypoint migrates that copy to the image's HEAD. That only happens on the scratch VM, and it doubles as a test of pending migrations against real data (ADR-0071 §5).

### Drill helper: `restore-from-prod`

The drill host (and only the drill host) has `/usr/local/bin/restore-from-prod`, installed by cloud-init from `terraform/cloud-init/bin/restore-from-prod.tpl` (T-D41a). The workflow runs it as `ssh operator@<drill-host> 'sudo /usr/local/bin/restore-from-prod'`. It stops `app` + `litestream`, moves the local DB (and `-wal`, `-shm`, Litestream meta dir) to `/data/pre-restore-<ts>/`, restores the latest state of `s3://budget-planner-prod-<region>/db` into `/data/budget.db`, checks `PRAGMA integrity_check`, chowns to uid 10001, runs `docker compose up -d litestream app` and waits until `/ready` reports `"status":"ok"`.

- **Credential**: a read-only key (`GetObject` + `ListBucket` on the prod bucket) passed as `TF_VAR_scw_access_key_restore` / `TF_VAR_scw_secret_key_restore` (workflow secrets `PROD_REPLICA_RO_ACCESS_KEY` / `PROD_REPLICA_RO_SECRET_KEY`). Cloud-init writes it to `/etc/budget-planner/restore-source.env` (0600, root). It is empty on prod and the helper does not exist there.
- **Age identity (T-D56)**: the prod replica is age-encrypted (ADR-0078 §3). The helper reads the identity from `/etc/budget-planner/litestream-age.key` (0600, root; Terraform `litestream_age_identity`, which on the drill env must be the **prod** identity) and exports it to the restore container. It refuses to run if the file is missing. **A lost identity means the replica is unrecoverable.**
- **Prod is never written**: the prod replica appears only in a throw-away config passed to `litestream restore`. The running Litestream service uses `/etc/budget-planner/litestream.yml`, which targets the drill bucket. The helper aborts if the source bucket equals the drill bucket or the read-only key equals the drill write key.

## Preconditions

- The decision to restore is intentional. Litestream restore is destructive to the current `/data/budget.db`.
- You know the target recovery point:
  - **Latest** — the default; recovers up to the most recent WAL segment uploaded (RPO ≤ 15 s).
  - **Point-in-time** — a specific UTC timestamp within the 30-day window.
- A read-only IAM credential scoped to `budget-planner-prod-pl-waw` exists (preferred — do not reuse the write credential the host already has for Litestream). If not, create one in Scaleway console: IAM → Applications → New application → policy `read-only on budget-planner-prod-pl-waw` → generate access key + secret.
- The age identity is available: `/etc/budget-planner/litestream-age.key` exists on the host (cloud-init writes it from `litestream_age_identity`), and the operator password manager holds the master copy. **Without the identity the replica cannot be decrypted; a restore attempted without it fails.**
- You have operator SSH access as `app@<prod-host>`.
- You have recorded the current audit-row count for a sanity check after restore:
  ```sh
  ssh app@<prod-host> \
    "sqlite3 /data/budget.db 'SELECT count(*), max(id), max(created_at) FROM audit_log;'" \
    || echo "DB unreadable — expected if corruption triggered this runbook"
  ```

## Procedure

1. Announce the restore to any other operator (if applicable). Prod will be read-only for the duration.
2. Stop the app container (Litestream stays up — we want it to flush pending WAL):
   ```sh
   ssh app@<prod-host> "cd /etc/budget-planner && docker compose stop app"
   ```
3. Wait 15 s for Litestream to flush any outstanding WAL to the bucket, then stop Litestream:
   ```sh
   ssh app@<prod-host> "sleep 15 && cd /etc/budget-planner && docker compose stop litestream"
   ```
4. Move the current DB aside (do not delete — forensic value):
   ```sh
   ssh app@<prod-host> \
     "sudo mv /data/budget.db /data/budget.db.pre-restore-$(date -u +%Y%m%dT%H%M%SZ) \
      && sudo mv /data/budget.db-wal /data/budget.db-wal.pre-restore 2>/dev/null || true \
      && sudo mv /data/budget.db-shm /data/budget.db-shm.pre-restore 2>/dev/null || true"
   ```
5. Export the read-only credential (if different from the write credential already on the host) into the restore shell:
   ```sh
   ssh app@<prod-host>
   export LITESTREAM_ACCESS_KEY_ID='<RO-KEY-ID>'
   export LITESTREAM_SECRET_ACCESS_KEY='<RO-KEY-SECRET>'
   ```
6. Run the restore. Replicas are age-encrypted, so restore through the config file (a bare `s3://` URL carries no identity and cannot decrypt). `/etc/budget-planner/litestream-restore.yml` already holds the bucket and `age.identities: [${LITESTREAM_AGE_IDENTITY}]`; export the identity from the key file and pass the read-only credential as `SCW_ACCESS_KEY` / `SCW_SECRET_KEY`:
   ```sh
   export LITESTREAM_AGE_IDENTITY="$(sudo grep -m1 '^AGE-SECRET-KEY-' /etc/budget-planner/litestream-age.key)"
   export SCW_ACCESS_KEY="$LITESTREAM_ACCESS_KEY_ID" SCW_SECRET_KEY="$LITESTREAM_SECRET_ACCESS_KEY"
   sudo -E docker run --rm \
     -v /data:/data \
     -v /etc/budget-planner/litestream-restore.yml:/etc/litestream.yml:ro \
     -e LITESTREAM_AGE_IDENTITY -e SCW_ACCESS_KEY -e SCW_SECRET_KEY \
     litestream/litestream:0.3.14 \
     restore -config /etc/litestream.yml -o /data/budget.db /data/budget.db
   ```
   Point-in-time: add `-timestamp 2026-11-15T08:00:00Z` before the final path argument. To prove the encryption, the same command with `LITESTREAM_AGE_IDENTITY` unset must fail.
7. Fix ownership and permissions back to the `app` uid:
   ```sh
   sudo chown "$(id -u app):$(id -g app)" /data/budget.db
   sudo chmod 0600 /data/budget.db
   ```
8. Start Litestream **before** the app so replication re-establishes from the restored DB:
   ```sh
   cd /etc/budget-planner && docker compose up -d litestream
   sleep 5
   docker compose logs litestream --tail 20   # expect "initialized db" + "replicating"
   ```
9. Start the app:
   ```sh
   docker compose up -d app
   ```
   The entrypoint applies any migrations the restored DB is missing before uvicorn starts. If the DB already has migrations applied, it writes a pre-migration backup to `/data/backups/` first (ADR-0071). Check `docker logs budget-planner-app 2>&1 | grep startup_migrations`. The `litestream-restore` one-shot also runs again, but it does nothing because `/data/budget.db` now exists.

### Variant — restore from the pre-migration backup

Use this to undo a migration that broke data, or to roll back a release flagged **"rollback requires restore"** (ADR-0071 §4). The entrypoint keeps the newest 3 `VACUUM INTO` copies taken just before each migrating start:

```sh
ssh app@<prod-host> "ls -lt /data/backups/"
# budget.db.pre-migrate-<last applied NNNN>-<UTC ts>
```

1. Do steps 1–4 above (stop app, flush + stop Litestream, move the current DB aside).
2. Copy the backup into place (copy, don't move, so the backup survives):
   ```sh
   sudo cp /data/backups/budget.db.pre-migrate-<NNNN>-<ts> /data/budget.db
   ```
3. Continue with step 7 (ownership). Then:
   - **Undoing a broken migration**: before step 9, roll the image back (`deploy-budget-planner rollback`). If you start the image that contains the migration, the entrypoint applies it again.
   - **Rolling back a "rollback requires restore" release**: run `ssh deploy@<prod-host> "rollback"` as step 9 instead of `docker compose up -d app`.
4. Writes made between the backup timestamp and the restore are lost. Litestream treats the copied DB as a new generation.

## Verification

```sh
# Integrity.
ssh app@<prod-host> "sqlite3 /data/budget.db 'PRAGMA integrity_check;'"
# Expect: ok

# Row counts — compare against the pre-restore numbers you recorded,
# minus any writes that happened between the recovery point and the restore.
ssh app@<prod-host> \
  "sqlite3 /data/budget.db 'SELECT count(*), max(id), max(created_at) FROM audit_log;'"

# Readiness probe hits DB.
curl -fsS "https://<prod-host>/ready" | jq .
# Expect: {"status":"ok","db":"ok", ...}

# Litestream is replicating again, not just reading.
ssh app@<prod-host> "docker compose -f /etc/budget-planner/docker-compose.yml logs litestream --tail 20"
# Expect: "write wal segment ..." lines within 30 s.
```

Record the restore in [`restore-log.md`](restore-log.md) with the recovery point, duration, operator, and `integrity_check` result.

## Troubleshooting

- **`restore` exits with "no generation" or "no snapshots found"**: the bucket path is wrong or the credential cannot list it. Confirm `s3://budget-planner-prod-pl-waw/db` resolves via `aws s3 ls --endpoint-url https://s3.pl-waw.scw.cloud s3://budget-planner-prod-pl-waw/db/ --profile <restore-creds>`.
- **`integrity_check` returns anything other than `ok`**: do not start the app. Keep `/data/budget.db.pre-restore-*` for forensic. Try an earlier `-timestamp` within the 30-day window and re-run from step 4.
- **Litestream logs "generation changed" after restore**: expected. Litestream treats a restore as a new generation. Keep going.
- **Row counts far below expectation**: you may have restored to too early a point-in-time. Repeat with a later timestamp. If the latest segment itself is already incomplete, the Scaleway bucket may be mid-upload — wait 30 s and retry.
- **Read-only credential rejected by Scaleway**: the IAM policy must include `GetObject` **and** `ListBucket` on the bucket resource; Litestream calls `ListObjectsV2` first.
- **`docker compose up -d litestream` fails with permission denied on `/data/budget.db`**: ownership not fixed in step 7. Re-run the `chown` + `chmod`.

## Rollback (of a bad restore)

The pre-restore DB files were preserved in step 4. If the restore itself turned out worse than the state you started with:

1. Stop app + Litestream again.
2. Swap the files back:
   ```sh
   ssh app@<prod-host> \
     "sudo mv /data/budget.db /data/budget.db.restore-attempt-$(date -u +%Y%m%dT%H%M%SZ) \
      && sudo mv /data/budget.db.pre-restore-* /data/budget.db"
   ```
3. Start Litestream, then app. Verify as above.
4. Rotate the read-only credential and triage the Litestream bucket contents before attempting another restore.

## Cut-over to an encrypted replica (T-D56, ADR-0078 §3)

Do this once, when first deploying the age-enabled config to a bucket that already holds plaintext generations.

1. Generate the identity (`age-keygen -o litestream-age.key`), store it in the password manager, set `TF_VAR_litestream_age_identity` / `TF_VAR_litestream_age_recipient` (see the operator checklist) and apply Terraform so cloud-init rewrites `litestream.yml` and writes the key. Restart `litestream` (`docker compose up -d litestream`); it starts a **new generation** whose objects are age ciphertext.
2. Confirm: `aws s3 cp s3://<bucket>/db/... - | head -c 32` starts with `age-encryption.org/v1` for objects of the new generation.
3. Run the restore drill (`gh workflow run restore-drill.yml`, T-D41) with the prod identity and confirm it is green and logged in [`restore-log.md`](restore-log.md).
4. Only then delete the unencrypted generations (`litestream generations -config /etc/budget-planner/litestream.yml s3://...` to list, then remove the old generation prefixes under `db/generations/<id>/` with the bucket tooling). Bucket versioning keeps noncurrent copies until the T-D57 lifecycle expires them.
