# Runbook — Restore from Litestream

> **SSH access (ADR-0094):** port 22 is closed to the internet. Join the tailnet (Tailscale app on your machine, see [`tailscale-ssh.md`](tailscale-ssh.md)) and use the MagicDNS names `budget-planner-prod` / `budget-planner-drill-<run id>`. Every host placeholder below means that name.

Reconstruct `/data/budget.db` from the Scaleway Object Storage replica.

## Context

Litestream streams WAL segments to `s3://budget-planner-prod-pl-waw/db/` every 10 s and takes a daily full snapshot (ADR-0034 §3). Retention is 30 days of WAL + snapshots, giving a 30-day point-in-time recovery window. That window has a gap from 2026-11-07 to 2026-11-18; see the incident record below. RPO target is < 15 s; RTO target is < 60 s for the restore itself, < 60 min end-to-end from a cold VM (ADR-0032 §9).

This runbook is for restoring **into the current prod host** (DB corruption, accidental destructive write, bad migration). For restoring into a brand-new VM, use [`disaster-recovery.md`](disaster-recovery.md) instead — it wraps this restore inside a full re-provision.

The monthly automated drill (`.github/workflows/restore-drill.yml`) exercises a variant of this procedure against a scratch VM; see [`restore-log.md`](restore-log.md) for the drill history. When the drill starts the image on the restored copy, the entrypoint migrates that copy to the image's HEAD. That only happens on the scratch VM, and it doubles as a test of pending migrations against real data (ADR-0071 §5).

### Drill helper: `restore-from-prod`

The drill host (and only the drill host) has `/usr/local/bin/restore-from-prod`, rendered from `terraform/cloud-init/bin/restore-from-prod.tpl` and written by the host agent as a managed file in `bp-config` (ADR-0111, T-D41a). The workflow runs it as `ssh operator@budget-planner-drill-<run id> 'sudo /usr/local/bin/restore-from-prod'`. It stops `app` + `litestream`, moves the local DB (and `-wal`, `-shm`, Litestream meta dir) to `/data/pre-restore-<ts>/`, restores the latest state of `s3://budget-planner-prod-<region>/db` into `/data/budget.db`, checks `PRAGMA integrity_check`, chowns to uid 10001, runs `docker compose up -d litestream app` and waits until `/ready` over the host name (pinned to loopback, TLS verified) reports `"status":"ready"` and `"db":"ok"`.

- **Credential**: the key of the `restore-reader` IAM application (read-only on the prod project, listed in the prod bucket policy; ADR-0092; lives in `terraform/bootstrap/ci` since ADR-0104; rotate there under break-glass, see `key-rotation.md`, then update the secrets), passed as `TF_VAR_scw_access_key_restore` / `TF_VAR_scw_secret_key_restore` (workflow secrets `PROD_REPLICA_RO_ACCESS_KEY` / `PROD_REPLICA_RO_SECRET_KEY`). The host agent writes it from `bp-config` to `/etc/budget-planner/restore-source.env` (0600, root). It is empty on prod and the helper does not exist there.
- **Age identity (T-D56)**: the prod replica is age-encrypted (ADR-0078 §3). The helper reads the identity from `/etc/budget-planner/litestream-age.key` (0600, root; Terraform `litestream_age_identity`, which on the drill env must be the **prod** identity) and exports it to the restore container. It refuses to run if the file is missing. **A lost identity means the replica is unrecoverable.**
- **Prod is never written**: the prod replica appears only in a throw-away config passed to `litestream restore`. The running Litestream service uses `/etc/budget-planner/litestream.yml`, which targets the drill bucket. The helper aborts if the source bucket equals the drill bucket or the read-only key equals the drill write key.

## Preconditions

- The decision to restore is intentional. Litestream restore is destructive to the current `/data/budget.db`.
- You know the target recovery point:
  - **Latest** — the default; recovers up to the most recent WAL segment uploaded (RPO ≤ 15 s).
  - **Point-in-time** — a specific UTC timestamp within the 30-day window.
- A read-only IAM credential scoped to `budget-planner-prod-pl-waw` exists (preferred — do not reuse the write credential the host already has for Litestream). `terraform/bootstrap/ci` creates it (`restore_reader_access_key` / `restore_reader_secret_key` outputs, ADR-0092, ADR-0104); do not create ad-hoc applications, they would not be in the bucket policy.
- The age identity is available: `/etc/budget-planner/litestream-age.key` exists on the host (the host agent writes it from `litestream_age_identity` via `bp-config`), and the operator password manager holds the master copy. **Without the identity the replica cannot be decrypted; a restore attempted without it fails.**
- You have operator SSH access as `operator@budget-planner-prod`.
- You have recorded the current audit-row count for a sanity check after restore:
  ```sh
  ssh operator@budget-planner-prod \
    "sqlite3 /data/budget.db 'SELECT count(*), max(id), max(created_at) FROM audit_log;'" \
    || echo "DB unreadable — expected if corruption triggered this runbook"
  ```

## Procedure

1. Announce the restore to any other operator (if applicable). Prod will be read-only for the duration.
2. Stop the app container (Litestream stays up — we want it to flush pending WAL):
   ```sh
   ssh operator@budget-planner-prod "cd /etc/budget-planner && docker compose stop app"
   ```
3. Wait 15 s for Litestream to flush any outstanding WAL to the bucket, then stop Litestream:
   ```sh
   ssh operator@budget-planner-prod "sleep 15 && cd /etc/budget-planner && docker compose stop litestream"
   ```
4. Move the current DB aside (do not delete — forensic value):
   ```sh
   ssh operator@budget-planner-prod \
     "sudo mv /data/budget.db /data/budget.db.pre-restore-$(date -u +%Y%m%dT%H%M%SZ) \
      && sudo mv /data/budget.db-wal /data/budget.db-wal.pre-restore 2>/dev/null || true \
      && sudo mv /data/budget.db-shm /data/budget.db-shm.pre-restore 2>/dev/null || true"
   ```
5. Export the read-only credential (if different from the write credential already on the host) into the restore shell:
   ```sh
   ssh operator@budget-planner-prod
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
   `litestream restore` leaves `/data/budget.db.tmp-wal` (empty) and `/data/budget.db.tmp-shm` behind. Remove them, but only if the WAL is empty; a non-empty tmp-wal means the restore is incomplete, so stop and investigate:
   ```sh
   sudo test ! -s /data/budget.db.tmp-wal && sudo rm -f /data/budget.db.tmp-wal /data/budget.db.tmp-shm
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
   The entrypoint applies any migrations the restored DB is missing before uvicorn starts. If the DB already has migrations applied, it writes a pre-migration backup to `/data/backups/` first (ADR-0071). Check `docker logs budget-planner-app 2>&1 | grep startup_migrations`. The `litestream-restore` one-shot also runs again, but it does nothing because `/data/budget.db` now exists.

### Variant — restore from the pre-migration backup

Use this to undo a migration that broke data, or to roll back a release flagged **"rollback requires restore"** (ADR-0071 §4). The entrypoint keeps the newest 3 `VACUUM INTO` copies taken just before each migrating start:

```sh
ssh operator@budget-planner-prod "ls -lt /data/backups/"
# budget.db.pre-migrate-<last applied NNNN>-<UTC ts>
```

1. Do steps 1–4 above (stop app, flush + stop Litestream, move the current DB aside).
2. Copy the backup into place (copy, don't move, so the backup survives):
   ```sh
   sudo cp /data/backups/budget.db.pre-migrate-<NNNN>-<ts> /data/budget.db
   ```
3. Continue with step 7 (ownership). Then:
   - **Undoing a broken migration**: before step 9, roll the image back (`rollback.yml`, see [`rollback.md`](rollback.md)). If you start the image that contains the migration, the entrypoint applies it again.
   - **Rolling back a "rollback requires restore" release**: dispatch `rollback.yml` (see [`rollback.md`](rollback.md)) as step 9 instead of `docker compose up -d app`. The agent only changes containers when the Terraform generation changes, so do not release or roll back while the restore is half done.
4. Writes made between the backup timestamp and the restore are lost. Litestream treats the copied DB as a new generation.

## Verification

```sh
# Integrity.
ssh operator@budget-planner-prod "sqlite3 /data/budget.db 'PRAGMA integrity_check;'"
# Expect: ok

# Row counts — compare against the pre-restore numbers you recorded,
# minus any writes that happened between the recovery point and the restore.
ssh operator@budget-planner-prod \
  "sqlite3 /data/budget.db 'SELECT count(*), max(id), max(created_at) FROM audit_log;'"

# Readiness probe hits DB.
curl -fsS "https://budget-planner-prod/ready" | jq .
# Expect: {"status":"ok","db":"ok", ...}

# Litestream is replicating again, not just reading.
ssh operator@budget-planner-prod "docker compose -f /etc/budget-planner/docker-compose.yml logs litestream --tail 20"
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
   ssh operator@budget-planner-prod \
     "sudo mv /data/budget.db /data/budget.db.restore-attempt-$(date -u +%Y%m%dT%H%M%SZ) \
      && sudo mv /data/budget.db.pre-restore-* /data/budget.db"
   ```
3. Start Litestream, then app. Verify as above.
4. Rotate the read-only credential and triage the Litestream bucket contents before attempting another restore.

## Incident record: replication stall, 2026-11-07 to 2026-11-18 (T-D136)

- **Symptom:** prod WAL replication stalled from 2026-11-07T17:52Z with `cannot determine replica position: lz4: bad magic number`. Litestream only logged and retried, so the container stayed "up".
- **Cause:** the replicate config had age recipients but no identity, so the restart path could not read back the age-encrypted last segment (ADR-0114).
- **RPO during the stall:** daily snapshots continued. The last snapshot before the fix was 2026-11-17 17:57Z, so RPO was at most about 24 h. Point-in-time recovery inside the stall window is not available.
- **Fix:** release `v3.0.2` (ADR-0114, T-D136). On 2026-11-18T14:37Z the litestream entrypoint logged "forcing a new generation (one-time, ADR-0114)". Litestream opened generation `2901fbd3873a6696`, wrote a snapshot, and has written WAL segments every 10 to 60 s since, with no errors. A second start did not force again (the marker works).
- **Verified:** on prod, 2026-11-18, by the operator. The restore drill ran green against this generation on 2026-11-18 (run 44351020259, first `restore-log.md` entry).

## Replication stall: detect and recover (T-D144, ADR-0119, ADR-0114)

The external monitor on `https://budget.rising-dough.eu/health/replication` (UptimeRobot, 5 min) goes red when the newest object in the prod replica is older than 26 h, or the probe stopped reporting. `/health` and `/ready` do not notice a stall. All commands below are single lines from the operator laptop.

**Monitor setup (2026-11-18, v3.0.3).** The second UptimeRobot monitor is a **Keyword** monitor, not a plain status-code monitor: type Keyword, URL above, keyword `"status":"ok"`, alert when the keyword does not exist, 5 min. Why: the free UptimeRobot plan probes with HEAD and cannot change the method. Until T-D146 (v3.0.4) the route returned 405 on HEAD, so a plain HTTP(S) monitor would report the host down while it is healthy. The Keyword check uses GET and reads the body. A stale replica returns 503 and the keyword is missing, so the monitor still goes red. After v3.0.4 the plain HTTP(S) check also works (optional switch).

**1. Detect and confirm**

```sh
curl -sS -w '\nHTTP %{http_code}\n' https://budget.rising-dough.eu/health/replication
ssh operator@budget-planner-prod "cat /var/lib/budget-planner/replication/status.json"
ssh operator@budget-planner-prod "docker logs budget-planner-litestream --since 1h 2>&1 | grep -E 'cannot determine|wal segment written|write wal segment|snapshot written|error' | tail -30"
ssh operator@budget-planner-prod "docker logs budget-planner-litestream-probe --since 30m 2>&1 | tail -10"
```

Reading the answers: `status: stale` with the litestream log full of `cannot determine replica position` is the 2026-11 incident. `probe_stale` / `probe_error` means the probe itself or its listing fails (check the probe log, credentials, bucket reachability) and says nothing yet about Litestream. `no_objects` after a fresh start: wait 2 minutes, a new generation writes its snapshot right away. Healthy logs show `wal segment written` / `write wal segment` lines within a minute of a DB write.

**2. Safe manual backup first (before any recovery step)**

`/data` is owned by uid 10001 (mode 0700), so the operator cannot write there without sudo. Run the SQLite online backup inside the app container, which owns `/data`. `/data/backups` is the directory the pre-migration backups use; the command creates it if missing.

```sh
ssh operator@budget-planner-prod "docker exec budget-planner-app python -c \"import os,sqlite3,datetime as d; t=d.datetime.now(d.UTC).strftime('%Y%m%dT%H%M%SZ'); os.makedirs('/data/backups',exist_ok=True); p='/data/backups/budget.db.manual-'+t; s=sqlite3.connect('/data/budget.db'); b=sqlite3.connect(p); s.backup(b); b.close(); s.close(); print(p, sqlite3.connect(p).execute('PRAGMA integrity_check').fetchone()[0])\""
# Expect: /data/backups/budget.db.manual-<ts> ok
```

The backup is a consistent copy even while the app writes (SQLite backup API). It is outside the automatic pruning (`prune_backups` only matches `*.pre-migrate-*`), so delete it once the incident is closed, within the 37-day copy ceiling of ADR-0078 §4: `ssh operator@budget-planner-prod "docker exec budget-planner-app rm /data/backups/budget.db.manual-<ts>"`. If the app container is down, use `sudo`: `ssh operator@budget-planner-prod "sudo sqlite3 /data/budget.db \".backup '/data/backups/budget.db.manual-<ts>'\""` (then `sudo chown 10001:10001` the file).

**3. Force a new generation (the usual cure for a position error)**

Removing the marker makes the entrypoint (ADR-0114) delete Litestream's meta dir on the next start, so Litestream opens a new generation with a fresh snapshot. The SQLite DB and WAL are not touched.

```sh
ssh operator@budget-planner-prod "sudo rm -f /data/.litestream-age-generation && cd /etc/budget-planner && sudo docker compose restart litestream"
ssh operator@budget-planner-prod "docker logs budget-planner-litestream --since 2m 2>&1 | grep -E 'forcing a new generation|snapshot written|wal segment|error|cannot determine'"
# Expect: "forcing a new generation (one-time, ADR-0114)", then a snapshot and WAL segment lines, no errors.
ssh operator@budget-planner-prod "docker restart budget-planner-litestream-probe"
curl -sS https://budget.rising-dough.eu/health/replication
# Expect within about a minute: HTTP 200, "status":"ok", a new "generation".
```

The host agent does not undo this (it acts only when `bp-config` changes). The old generation stays in the bucket until retention (720 h) removes it.

**4. Escalate to a restore when**

- the new generation does not appear, or Litestream keeps logging errors other than the position error (403 / credential / bucket errors: fix the cause first, see Troubleshooting);
- the manual backup in step 2 fails `integrity_check`, or `/ready` is red (the live DB is the problem, not the replica): follow [Procedure](#procedure) with the backup variant above;
- the stall lasted longer than the data you can lose: the last good snapshot is the recovery point (point-in-time inside the stall window is not available).

Afterwards run the drill (`restore-drill.yml`) against the new generation and log it in [`restore-log.md`](restore-log.md).

**After a release that changes the probe (v3.0.3):** run the first `curl` above once. 200 `ok` proves the probe parsing; 503 `probe_error` with the probe log is the signal to fix the parser (ADR-0119, Consequences).

## Cut-over to an encrypted replica (T-D56, ADR-0078 §3, ADR-0112)

Do this once, after the age-enabled config is live on a bucket that already holds plaintext objects.

**What Litestream 0.3.14 does when age is enabled (read from `replica.go`, v0.3.14).** It does **not** start a new generation. The running generation continues, and only snapshots and WAL segments written *after* the restart are age ciphertext (each object starts with `age-encryption.org/v1`; file names stay `*.lz4`). So one generation can mix plaintext and encrypted objects, and a "plaintext generation" test is not reliable. The cleanup workflow classifies every object by its first bytes instead.

**Restart safety (T-D136, ADR-0114).** On every start the replicator re-reads its last WAL segment (`calcPos`) and decrypts it only if the replicate config has `age.identities`. The replicate config now carries the identity, and the litestream entrypoint forces one new generation per host (marker `/data/.litestream-age-generation`), so every segment it reads back is ciphertext. **This cut-over depends on T-D136 being live on the host** (live on prod since release `v3.0.2`, 2026-11-18); before that a restart of `litestream` stalls replication (`cannot determine replica position`). Check `docker compose logs litestream --tail 50` after the release converges.

1. **Encrypted generation exists.** Terraform was applied with `litestream_age_identity` / `litestream_age_recipient` (operator checklist); the host agent restarted `litestream`. Confirm on the host: `docker compose logs litestream | grep -i "snapshot written"`. With T-D136 the first start opens a new generation, so its snapshot is written right away; wait for it (a restore with the identity cannot use the older plaintext snapshots). Spot-check one new object: `aws s3api get-object --endpoint-url https://s3.pl-waw.scw.cloud --bucket budget-planner-prod-pl-waw --key <key> --range bytes=0-31 /dev/stdout | head -c 22` prints `age-encryption.org/v1`.
2. **Restore drill green.** Done 2026-11-18 (run 44351020259, generation `2901fbd3873a6696`). For a later drill, dispatch `restore-drill.yml` (T-D40/T-D41) after that snapshot, with the prod identity on the drill host. The operator appends the entry to [`restore-log.md`](restore-log.md) with `Result: pass` and `integrity_check: ok`. Also run the negative check from the restore steps (restore without the identity must fail).
3. **Dry run.** Dispatch `litestream-plaintext-cleanup.yml` from `main` with `dry_run=true` (default) and approve the `prod` environment. Read the step summary: counts, the plaintext keys to delete, and any `REFUSED` line. It refuses (exit 2, nothing deleted) when there is no encrypted snapshot, an object has an unknown format, a plaintext object is still needed by a restore (wait for the next snapshot), or `restore-log.md` has no green entry dated on or after the day of the first encrypted snapshot.
4. **Review.** Every key to delete must be an old snapshot or WAL segment with an index below the newest encrypted snapshot of its generation, or part of a wholly plaintext older generation.
5. **Delete.** Dispatch again with `dry_run=false`, approve `prod`. Only the listed plaintext objects are deleted. The bucket is versioned: the plaintext copies stay as noncurrent versions for the lifecycle window (7 d; 30 d retention + 7 d = 37 d ceiling, T-D57), which is also the undo window.
6. **Verify.** Re-run the dry run: it must list zero objects to delete. Mark T-D56 done in `docs/plans/v3/tasks.md`.

Credential used by the workflow: the `prod` environment's `APP_SCW_ACCESS_KEY` / `APP_SCW_SECRET_KEY` (the key Litestream replicates with; list/get/put/delete on the prod bucket only). No new secret.
