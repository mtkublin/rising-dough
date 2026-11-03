# ADR-0071: Production Startup Migrations — Container Entrypoint, Restore-Before-Start, N-1 Rollback Policy

- **Status**: Accepted
- **Date**: 2026-11-03
- **Related**: T-D19a, T-D19 / ADR-0069 (lifespan fails fast on an unmigrated schema), ADR-0032 §2 (single VM, compose stack), ADR-0034 (Litestream), ADR-0037 §3 (deploy shim), T-D10 (Dockerfile), T-D11 (prod-sim stack), T-D23 (cloud-init), T-D32 (deploy shim), T-D34 (rollback), T-D41 (restore drill)

## Context

Since T-D19 the production lifespan raises `SystemExit(1)` when the schema predates migration 0012 (`SchemaNotMigratedError`). Nothing in the production path ran migrations: the Dockerfile `CMD` starts uvicorn directly, cloud-init runs `docker compose up -d`, and the deploy shim runs `docker compose up -d app`. So a fresh `/data` volume never starts, and neither does an image that ships a new migration.

Constraints:

1. **Single writer.** One `app` container (fixed `container_name`) is the only SQLite writer; Litestream only reads the WAL and ships it to object storage (ADR-0034 §1).
2. **Litestream ordering.** On a fresh volume where a replica exists (DR, drill), the DB must be restored *before* anything creates a new empty DB. Otherwise the app would create and migrate an empty DB (with a freshly bootstrapped admin) and Litestream would start a new generation from it. That looks healthy and hides the real data.
3. **Rollback.** The deploy shim auto-reverts to the previous tag when `/ready` fails, and `rollback.yml` re-applies the previous tag. Both can start an older image against a schema that a newer image already migrated.
4. **Idempotency.** Containers restart (crash, host reboot, `restart: unless-stopped`). Every start must be safe.

Options considered:

- **(A) Container entrypoint.** Run migrations in the app container before `exec uvicorn`.
- **(B) Deploy shim.** Add a `docker compose run --rm app python -m budget_planner.db.migrate` step to `deploy-budget-planner`.
- **(C) Both.**

(B) misses every start path that does not go through the shim: cloud-init first boot, host reboot, DR re-provision, the restore drill, and the local prod-sim stack. (C) adds a second place that can drift. (A) covers every path with one mechanism.

## Decision

### 1. Migrations run in the container entrypoint

`Dockerfile` sets `ENTRYPOINT ["/app/docker-entrypoint.sh"]` (source: `deploy/docker-entrypoint.sh`). The entrypoint runs `python -m budget_planner.db.startup_migrate` and then `exec "$@"`, so the `CMD` (uvicorn) keeps PID 1 and receives signals directly. If the migration step exits non-zero, the entrypoint exits too (`set -e`) and uvicorn never starts. The deploy shim (T-D32) and cloud-init are unchanged.

Single-writer safety comes from the topology. `compose up -d app` stops the old container before the new one starts, because `container_name` is fixed and only one replica can exist, so migrations never race a live app. SQLite file locking plus `busy_timeout` still protect against a stray operator `exec`. Migrations open their connection through `get_connection`, so `wal_autocheckpoint = 0` holds for the migration writer too (ADR-0034 §2).

### 2. `budget_planner.db.startup_migrate`

This is an additive module on top of `db.migrate.apply_migrations`. The runner itself does not change.

- **Idempotent.** When no migration is pending, it opens the DB, logs `event="startup_migrations" applied=[]`, and writes nothing.
- **Pre-migration backup.** It takes a backup only when the DB already has applied migrations *and* some are pending. A fresh DB has nothing to back up. The backup uses `VACUUM INTO '<db dir>/backups/<db name>.pre-migrate-<last applied NNNN>-<UTC ts>'`, a consistent single-file copy taken through the same connection. Only the newest **3** backups are kept. They sit on the same volume as the DB, outside Litestream's watched path. This is the fast rollback path for a bad migration. Litestream PITR (30-day window, ADR-0034 §3) remains the second line of defence. The disk cost is a few MB.
- **Schema ahead of image.** When the DB records versions the image does not ship (a rollback onto a newer schema), it logs `schema_ahead_of_image` with those versions and **continues**. Refusing to start would defeat the auto-rollback in the deploy shim.
- **Failure.** Each migration runs in its own transaction (existing runner). On any error the process logs `startup_migrations_failed` and exits 1. The container then restart-loops, `/ready` fails, and the shim reverts to the previous tag on an unchanged (rolled-back) DB.

### 3. Restore-before-start in compose

Both `terraform/cloud-init/compose/docker-compose.yml.tpl` and the prod-sim `docker-compose.yml` gain a one-shot `litestream-restore` service:

```
litestream restore -if-db-not-exists -if-replica-exists -config /etc/litestream.yml /data/budget.db
```

The service then runs `chown 10001:10001` on `/data` and the restored files (Litestream runs as root and the app runs as uid 10001). `app` and the `litestream` replicator both depend on it with `condition: service_completed_successfully`. The step is a no-op when the DB exists, so re-running it on every `compose up -d app` is harmless. If no replica exists it also exits 0, and the app migrates and bootstraps an empty DB. DR therefore becomes automatic: re-provision, restore, migrate, bootstrap, `/ready`.

### 4. Rollback policy (N-1 schema compatibility)

- Every migration must leave the schema **readable and writable by the previous released image** (expand-only). Add columns as nullable or with defaults, add tables, and add indexes. Drop or rename only in a *later* release, once no image that relies on the old shape is in the rollback window.
- A migration that cannot meet N-1 compatibility must be called out in its `docs/CHANGELOG.md` entry as **"rollback requires restore"**. For that release, rollback means [`restore.md`](../plans/v3/runbooks/restore.md) (pre-migration backup or Litestream PITR to just before the deploy), followed by the older image. `rollback.yml` alone is not enough.
- Down scripts (`migrations/down/`) remain CI-only smoke tests and are never run against production.

### 5. Restore drill

The drill (T-D41) restores prod data into a scratch VM and starts the image. The entrypoint therefore migrates the restored copy to HEAD on the drill host, which also tests the pending migrations against real data. This happens on the scratch VM only and never touches the prod bucket.

## Consequences

- A fresh volume, an upgrade, a rollback, a reboot and DR all start without operator steps.
- Every start costs one extra short-lived Python process (well under 1 s when there is nothing to do).
- Operator commands run through `docker run <image> …` also migrate first. `docker compose exec app …` does not, because the app is already running and migrated.
- Migrations carry an N-1 compatibility obligation that review must enforce.
- `/data/backups/` must be considered in disk-usage alerts (bounded to 3 copies).
