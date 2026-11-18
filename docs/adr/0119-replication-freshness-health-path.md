# ADR-0119: A Replication Freshness Health Path for the External Monitor

- **Status**: Accepted
- **Date**: 2026-11-18
- **Relates to**: ADR-0033 §5, ADR-0034 §3, ADR-0078 §3, ADR-0111, ADR-0114
- **Task**: T-D144

## Context

Prod WAL replication stalled from 2026-11-07 to 2026-11-18 (`cannot determine replica position: lz4: bad magic number`, ADR-0114) and nobody noticed for 11 days. `/health` (process up) and `/ready` (`PRAGMA integrity_check`) stayed green the whole time, because neither looks at the replica. The external monitor (UptimeRobot, T-D44) can only see a non-2xx status or a missing keyword on a public URL. We need a public path that is non-2xx when the replica is stale.

Facts used for the decision:

- Litestream writes a WAL segment only when the DB changes, and a snapshot every `snapshot-interval: 24h`. An idle replica therefore still gets an object at least once a day while Litestream works.
- Litestream 0.3.14 `litestream generations` lists, per generation, the time bounds of the objects that are in the replica (it lists the bucket, so it proves objects arrived). It needs no decryption.
- The Prometheus endpoint (`addr:`) of 0.3.x exposes counters (`litestream_sync_count`, `litestream_sync_error_count`, `litestream_replica_operation_total`) that reset when the process restarts. They carry no "time of the newest object", so a stall that survives a restart cannot be told from a quiet DB without keeping state outside Litestream.

## Decision

1. **Signal: newest object in the bucket.** A new compose service `litestream-probe` (same pinned image `litestream/litestream:0.3.14`, same credentials, config and age key mounts as `litestream`) runs `litestream generations` every 5 minutes and writes a small status file. It takes the newest `end` timestamp over all generations (snapshot or WAL, whichever is newer) and the id of the generation that holds it. No new secret, no new IAM permission (the replicate credential already lists the bucket), no new host unit, no change to the host agent. The probe is a managed-file script plus a compose service, so it reaches prod through `bp-config` (ADR-0111).
2. **Status file.** `/var/lib/budget-planner/replication/status.json`, written atomically, world readable, no secrets:
   `{"checked_at": "<UTC ISO>", "newest_object_at": "<UTC ISO>|null", "generation": "<hex>|null", "error": "<code>|null"}`. The host dir is mounted read-write into the probe and read-only into the app.
3. **Endpoint: `GET /health/replication`** in `web/routers/health.py`, public, no auth (ADR-0033 §5; added to the auth, must-change-password exempt sets), no DB access. The decision is a pure function in `services/replication_health.py`. Responses:

   | Case | Status | `status` field |
   |------|--------|----------------|
   | newest object younger than the threshold, probe fresh | 200 | `ok` |
   | no status file path configured (dev, prod-sim) | 200 | `disabled` |
   | newest object older than the threshold | 503 | `stale` |
   | probe has not reported for more than 15 min (probe died or never ran) | 503 | `probe_stale` |
   | the probe reports an error, or no object in the bucket | 503 | `probe_error` / `no_objects` |
   | file missing or unparsable | 503 | `missing` / `unreadable` |

   The body carries `status`, `newest_object_at`, `age_seconds`, `max_age_seconds`, `generation`, `checked_at`. No bucket credentials, key ids or paths. It is fail closed: any unknown state is 503.
4. **Threshold: 26 h** (`BUDGET_REPLICATION_MAX_AGE_HOURS`, default 26, range 2 to 720): the 24 h snapshot interval plus a 2 h margin. The probe heartbeat limit is a constant of 15 min (three probe intervals).
5. **Wiring.** Terraform sets `BUDGET_REPLICATION_STATUS_FILE=/replication/status.json` on the app (compose template) and delivers the probe script as a managed file (`litestream-replication-probe.sh`, restarts `litestream-probe`). Everything is inside `bp-config` and the compose file: **no VM replacement**; `bootstrap.yaml.tpl` is untouched.
6. **External monitor.** UptimeRobot gets a second monitor: plain HTTP(s) status-code monitor (no keyword monitor), `https://budget.rising-dough.eu/health/replication`, 5 min, "up" = HTTP 2xx. Confirmed by the user 2026-11-18: the path returns 503 when replication is stale, missing or unreadable and 200 when fresh, so the status code alone carries the signal. Same alert contact as `/health`.
7. **Drill.** The drill runs the same templates and replicates into the drill bucket, so the path works there: 503 until the first snapshot exists (about a minute after start), then 200. The drill smoke only polls `/ready` and is unchanged, so no gate depends on this path. Drill, not prod, proves the probe parsing the first time (see Consequences).
8. **Caddy / CSP / rate limit.** The path is a JSON response served by the app through the existing catch-all `reverse_proxy`. The CSP is only added to `text/html` responses, security headers apply as for `/health`. The Caddyfile has no rate limit, and the app limits only auth routes (ADR-0072), so a 5 min poll is not throttled.

## Consequences

- A stall is visible within the threshold plus one monitor interval (about 26 h worst case, instead of 11 days). It is not a tight alarm: a stall that starts right after a snapshot, with an idle DB, shows up after about 26 h. A tighter rule (compare the DB WAL mtime with the newest object) was rejected for now: Litestream itself touches the WAL, so it would flap. Follow-up if the delay proves too long.
- The format of `litestream generations` was read from the 0.3.14 source, not run in this change. The probe parses the last column of each data row (the `end` timestamp). If the format differs, the probe reports `error` and the path answers 503 `probe_error` right after the release, so a parsing mistake is loud, never a silent green. The release check (runbook, restore.md) reads the path once by hand.
- One more container (small, sleeps between runs) and one more status file. Rejected: a systemd timer on the host (needs the agent to manage units and a host S3 client, i.e. new tooling and the credential outside Docker); the Prometheus endpoint (see Context); the local Litestream meta dir (does not prove upload).
- A manual backup copy next to `/data/backups` is outside the prune rule of `startup_migrate`; the runbook says to delete it (ADR-0078 §4 ceiling).
