# Runbook — Restore from Litestream

Reconstruct `/data/budget.db` from the Scaleway Object Storage replica.

## Context

Litestream streams WAL segments to `s3://budget-planner-prod-pl-waw/db/` every 10 s and takes a daily full snapshot (ADR-0034 §3). Retention is 30 days of WAL + snapshots, giving a 30-day point-in-time recovery window. RPO target is < 15 s; RTO target is < 60 s for the restore itself, < 60 min end-to-end from a cold VM (ADR-0032 §9).

This runbook is for restoring **into the current prod host** (DB corruption, accidental destructive write, bad migration). For restoring into a brand-new VM, use [`disaster-recovery.md`](disaster-recovery.md) instead — it wraps this restore inside a full re-provision.

The monthly automated drill (`.github/workflows/restore-drill.yml`) exercises a variant of this procedure against a scratch VM; see [`restore-log.md`](restore-log.md) for the drill history.

## Preconditions

- The decision to restore is intentional. Litestream restore is destructive to the current `/data/budget.db`.
- You know the target recovery point:
  - **Latest** — the default; recovers up to the most recent WAL segment uploaded (RPO ≤ 15 s).
  - **Point-in-time** — a specific UTC timestamp within the 30-day window.
- A read-only IAM credential scoped to `budget-planner-prod-pl-waw` exists (preferred — do not reuse the write credential the host already has for Litestream). If not, create one in Scaleway console: IAM → Applications → New application → policy `read-only on budget-planner-prod-pl-waw` → generate access key + secret.
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
6. Run the restore. Latest:
   ```sh
   sudo -E docker run --rm \
     -v /data:/data \
     -v /etc/litestream.yml:/etc/litestream.yml:ro \
     -e LITESTREAM_ACCESS_KEY_ID \
     -e LITESTREAM_SECRET_ACCESS_KEY \
     litestream/litestream:0.3 \
     restore -o /data/budget.db \
     s3://budget-planner-prod-pl-waw/db
   ```
   Point-in-time (replace with the actual UTC timestamp):
   ```sh
   sudo -E docker run --rm \
     -v /data:/data \
     -v /etc/litestream.yml:/etc/litestream.yml:ro \
     -e LITESTREAM_ACCESS_KEY_ID \
     -e LITESTREAM_SECRET_ACCESS_KEY \
     litestream/litestream:0.3 \
     restore -o /data/budget.db \
     -timestamp 2026-11-15T08:00:00Z \
     s3://budget-planner-prod-pl-waw/db
   ```
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
