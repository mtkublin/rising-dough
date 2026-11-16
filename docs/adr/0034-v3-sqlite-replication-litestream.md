# ADR-0034: v3 SQLite Durability — Continuous Replication via Litestream to Scaleway Object Storage

- **Status**: Proposed
- **Date**: 2026-10-27 (renumbered v2 → v3 on 2026-10-28)
- **Related**: ADR-0003 (SQLite only in v1), ADR-0029 (SQLite connection threading), ADR-0032 (v3 remote deployment)
- **Amends**: ADR-0003 (adds an off-host durability layer; SQLite remains the single OLTP store).

## Context

ADR-0032 puts the SQLite file on the local SSD of one Scaleway Stardust VM. That VM has no availability SLA and can be destroyed on short notice (or by the user running `terraform destroy`). The whole point of ADR-0032's "disposable host" model is that durability must live elsewhere.

Options evaluated:

1. **Litestream** — streams SQLite WAL segments to any S3-compatible target. First-class Scaleway Object Storage support. Zero-downtime, continuous, no DB engine change.
2. **LiteFS** — Fly.io's FUSE-based replication. Requires FUSE on the host and is primarily tuned for Fly's platform.
3. **Periodic `.backup` to S3** — simple but RPO is the backup interval (minutes to hours).
4. **Scaleway Block Volume snapshots** — gives point-in-time recovery per snapshot, but adds a billable volume and a different failure/restore model from "restore from object storage".

## Decision

Use **Litestream** as a sidecar process on the Scaleway VM, replicating `/data/budget.db` continuously to the Scaleway Object Storage bucket created by Terraform.

### 1. Topology

```
┌───────────────────────┐
│  app container        │
│    FastAPI / uvicorn  │
│    writes /data/*.db  │
└──────────┬────────────┘
           │ shared /data volume
┌──────────▼────────────┐
│  litestream sidecar   │   WAL → s3://budget-planner-prod-pl-waw/db/
│    v0.3.x pinned      │
└───────────────────────┘
```

- `litestream` runs in its own container with read-write access to `/data`.
- The app container never speaks to object storage directly; Litestream is the only writer to S3.
- `litestream.yml` is mounted read-only from the host at `/etc/litestream.yml`.

### 2. SQLite tuning (required by Litestream)

- `PRAGMA journal_mode = WAL;` on every connection (ADR-0029 continues to apply).
- `PRAGMA synchronous = NORMAL;` (sufficient; Litestream requires WAL mode but tolerates `NORMAL`).
- `PRAGMA wal_autocheckpoint = 0;` — Litestream owns checkpoint cadence to guarantee it reads every WAL segment before SQLite recycles it.
- `PRAGMA busy_timeout = 5000;`.
- These settings are centralised in `src/budget_planner/db/connection.py` and documented in the module-level docstring. Phase 1 adds a startup assertion that `wal_autocheckpoint == 0` and fails fast if the DB is misconfigured.

### 3. Litestream configuration

```yaml
# /etc/litestream.yml (final shape, authoritative)
dbs:
  - path: /data/budget.db
    replicas:
      - type: s3
        endpoint: https://s3.pl-waw.scw.cloud
        region: pl-waw
        bucket: budget-planner-prod-pl-waw
        path: db
        access-key-id:     ${SCW_ACCESS_KEY}
        secret-access-key: ${SCW_SECRET_KEY}
        retention: 720h          # 30 days of WAL + snapshots
        retention-check-interval: 24h
        snapshot-interval: 24h   # one full snapshot per day
        sync-interval: 10s
```

- Credentials come from environment variables injected by `docker compose` from `/etc/budget-planner/litestream.env` (mode 0600, owned root, rendered by Terraform via cloud-init). Never committed, never logged.
- The IAM credential is scoped to **this single bucket**, read + write + list only, created by Terraform.
- Retention of 30 days WAL + daily snapshots gives a 30-day point-in-time recovery window.
- `sync-interval: 10s` → RPO target of 15 seconds (10 s sync + ~5 s upload).

### 4. Restore procedure

Documented step-by-step in the Phase 4 runbook (`docs/runbooks/restore.md`, created in Phase 4). The one-command shape:

```
litestream restore \
  -o /data/budget.db \
  s3://budget-planner-prod-pl-waw/db
```

Restores the latest known-good state (or `-timestamp 2026-11-15T08:00:00Z` for point-in-time). After restore:

1. Stop the app container.
2. Run `sqlite3 /data/budget.db 'PRAGMA integrity_check;'` — must return `ok`.
3. Run `sqlite3 /data/budget.db 'SELECT count(*) FROM audit_log;'` and compare against the pre-destroy value recorded by the monthly drill.
4. Start the Litestream sidecar first, then the app container.

### 5. Drill schedule and acceptance

- **First drill** = part of Phase 4 acceptance. Must succeed before v3 is declared live.
- **Monthly drill** afterwards. The drill is: provision a scratch Stardust VM via `terraform workspace new drill-YYYY-MM` + `terraform apply -var env=drill`, restore from the primary bucket (read-only credential), verify `PRAGMA integrity_check` + audit log count, destroy. Logged in `docs/runbooks/restore-log.md`.
- **Automation**: the monthly drill is driven by a scheduled GitHub Actions workflow that provisions, restores, verifies, and tears down. If it fails, the workflow opens a GitHub issue titled `restore-drill-failure-YYYY-MM`.
- **Addendum 2026-11-06 (T-D66)**: the drill environment is always destroyed (`terraform destroy` runs `if: always()`, then a verification step fails the job if anything remains). The previous "leave the host standing for post-mortem" behaviour is superseded (cost: ~EUR 4.46/month if forgotten). Debugging evidence (cloud-init, journal, app/litestream/caddy logs; no secret-bearing files) is captured best-effort over SSH before destroy and kept as the `restore-drill-evidence` workflow artifact.

### 6. Operational guards

- Pre-commit assertion in the Phase 1 docker-compose smoke test: starting the app container without the Litestream sidecar running fails the compose health gate.
- Shutdown ordering: on `docker compose down`, `litestream` is given `stop_grace_period: 30s` to flush pending WAL. The app has `stop_grace_period: 10s`.
- Writes to object storage are the only outbound traffic that counts against egress; Scaleway Object Storage egress is included in the free tier (75 GB/mo); daily snapshot of a ~50 MB DB file + WAL fragments ≪ 1 GB/mo.

### 7. Version pinning

- Litestream `v0.3.x` (latest stable in the `0.3` line at the time of Phase 2 bootstrap). Image: `litestream/litestream:0.3`.
- Upgrades to `0.4` or later require a dedicated restore drill against the new version before rolling to production.

## Consequences

### Positive

- RPO ≤ 15 s. RTO depends on bucket read speed (small DB → < 60 s restore from the Warsaw region).
- Zero application code changes beyond PRAGMAs (centralised in `db/connection.py`).
- Scaleway bucket in `pl-waw` is same-region same-provider as compute → effectively zero network cost.
- The host VM is now genuinely disposable.
- Within Scaleway Object Storage free tier (75 GB) indefinitely at this scale.

### Negative

- Litestream is a sidecar process that must be running whenever the app writes. If it crashes silently, WAL grows unbounded (checkpointing is disabled). The Phase 1 health probe must assert Litestream is alive before the app accepts traffic.
- Point-in-time recovery is limited to the 30-day retention window. Compliance scenarios beyond that need a cross-region replica (deferred).
- WAL mode + `wal_autocheckpoint = 0` means every connection needs to be aware; a developer bypassing `db/connection.py` can corrupt the invariant. Phase 1 adds a mypy guard and runtime assertion.

### Follow-ups

- A later ADR may introduce cross-region replication (`pl-waw` → `fr-par`) for data > 10 GB or if the project leaves single-user territory.
- A later ADR may evaluate Litestream `v0.4+` once it is stable and the restore drill has been validated against it.

## Alternatives Considered

- **LiteFS** — rejected because the primary platform target is Scaleway, not Fly, and LiteFS's FUSE requirement adds a kernel-level dependency that cloud-init on Stardust does not advertise.
- **Periodic SQLite online backups via `sqlite3 .backup`** — rejected (RPO is the backup interval, which conflicts with the ≤ 15 s target).
- **Scaleway Block Volume snapshots** — kept as a defence-in-depth option: nightly snapshot of the root volume via Terraform `scaleway_instance_snapshot`, retained 7 days. Not a replacement for Litestream; it covers the host OS, not the DB file independent of the host.
