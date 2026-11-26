# ADR-0151: Capacity and Scaling Strategy per Distribution Stage

- **Status**: Accepted
- **Date**: 2026-11-26
- **Relates to**: [ADR-0003](0003-database-sqlite-only-v1.md), [ADR-0029](0029-sqlite-connection-threading.md), [ADR-0032](0032-v3-remote-deployment-scaleway-stardust-warsaw.md), [ADR-0034](0034-v3-sqlite-replication-litestream.md), [ADR-0061](0061-v3-multi-user-admin-bootstrap-and-data-isolation.md), [ADR-0068](0068-user-scoping-static-check-policy.md), [ADR-0071](0071-production-startup-migrations.md), [ADR-0081](0081-v4-field-level-encryption-scope-and-query-model.md), [ADR-0099](0099-release-and-environment-policy.md), [ADR-0111](0111-terraform-declared-host-state.md), [ADR-0118](0118-local-ssd-root-volume.md), [ADR-0145](0145-nbp-table-a-daily-fx-refresh-in-app-task.md), [ADR-0152](0152-python-upgrade-and-native-arm64-dev-interpreter.md), [ADR-0153](0153-native-hot-paths-via-pyo3.md)
- **Plan**: [`docs/plans/scaling/`](../plans/scaling/README.md) (T-SC01..T-SC16). Requirements: [`requirements.md` §13](../requirements.md#13-capacity-and-performance-added-2026-11-26).
- **Origin**: operator discussion 2026-11-26 (performance only; sign-up, email and GDPR are out of this ADR's scope and stay deferred).

## Context

The app runs on one Scaleway STARDUST1-S (shared vCPU, about 1 GB RAM, 10 GB local SSD, `terraform/main.tf`). One uvicorn process with no `--workers` (`Dockerfile`), sync handlers on the anyio threadpool, a SQLite connection per request (ADR-0029), WAL with `busy_timeout = 5000`, Litestream to Object Storage (`sync-interval: 10s`, `snapshot-interval: 24h`, 30-day retention), Caddy in front. Rate limits and sessions live in SQLite; the NBP FX refresh is an in-app task (ADR-0145). Static files are served by Starlette `StaticFiles` (`web/app.py`) and the Jinja environment leaves `auto_reload` at its default `True` (`web/templating.py`). Monitoring is three UptimeRobot monitors: `/health`, `/health/fx`, `/health/replication`.

The operator's distribution plan:

| Stage | Who | Users |
|---|---|---|
| 1 | Friends and family | ≤ 10 |
| 2 | Invited finance-oriented influencers and similar, once stage 1 feedback is in, the app is stable and most of the backlog is live | ≤ 100 |
| 3 | Open registration | unknown; marketing-driven spikes expected |

Nothing has been load-tested. All capacity figures below are estimates until T-SC05 measures them.

## Decision

### 1. Where each stage breaks first

- **Stages 1–2 fit the current stack.** The main risks are correctness on real data from people who are not the operator (non-PLN currencies, varied habits), isolation between users, and first impressions (errors, downtime on deploy, slow pages). Load is not the risk.
- **The database is not the throughput bottleneck at any realistic size.** A budget app writes little. Short WAL transactions on one writer cover far more than the expected write rate, and the data stays in the low GB (roughly 10k users × 1–2k rows a year). Long write transactions (imports, bulk reconciles) can queue other writers behind `busy_timeout` and are fixed in code, not by changing the database.
- **SQLite blocks multi-host, not speed.** It is embedded: the file must sit on the same host as the app, and network filesystems break its locking. The first time we need two app hosts (HA or CPU), SQLite has to go (§6).
- **CPU breaks first on one host,** from per-request Python work (view models, Jinja, SVG charts, aggregation). v4 adds decryption (+50 ms p95 budget, ADR-0081 §3) and bans cross-request plaintext caches, so it lowers the ceiling and removes caching as a lever.

### 2. Scaling order: vertical first, multi-host last

1. Cheap serving fixes (§3).
2. Measure: a k6 load baseline on an explore drill plus a py-spy profile (never against prod).
3. Fix what the profile shows: N+1 queries, missing indexes, native hot paths (ADR-0153).
4. A bigger instance, then 2–4 uvicorn workers. Workers require the in-app FX refresh (ADR-0145) to run once per host (a lock or a host timer), not once per worker. Rate limits and sessions already work across processes.
5. A warm standby (§5).
6. Multi-host with Postgres only when a §6 trigger fires.

**No split into microservices.** Splitting app, database and Litestream across hosts is impossible with SQLite and adds failure points without removing the single host. Litestream is already a sidecar. The app stays a modular monolith.

**Aggregates are not moved into SQL.** Aggregates convert at historical FX rates per transaction date through `FxConverter.to_base`; SQL aggregation would duplicate the FX owner (canonical-modules rule) and is undone by v4 T-E10, which moves aggregation to Python over decrypted rows.

### 3. Cheap serving fixes (now)

- **Jinja `auto_reload` follows the environment**: `auto_reload = (settings.env == "dev")`. Dev keeps hot template edits (uvicorn `--reload` watches `.py` only). Tests and production load each template once per process. A release is a new container with an empty in-memory cache, so nothing goes stale (no on-disk bytecode cache; read-only root). The template count (125) stays under Jinja's default `cache_size` (400); raise it if it grows past that.
- **Caddy serves `/static`** with `file_server` and a long `Cache-Control: public, max-age=31536000, immutable`, with a cache-busting version per release in each asset URL (content hash or release version), so a deploy never serves stale CSS or JS. The app no longer spends CPU on static assets.
- **Caddy holds requests across an app restart** with `lb_try_duration` (and a short `lb_try_interval`) on the `reverse_proxy` block, so a restart shows a slow request instead of a 502.
- **Python upgrade** (3.15, fallback 3.14) together with a native arm64 dev interpreter: ADR-0152.

### 4. Deployments

- **Now**: `lb_try_duration` (§3). Downtime per deploy at stage 1 is seconds and invisible.
- **Before stage 2**: migrations follow **expand/contract** (each release's schema works with the previous release's code), on top of the ADR-0071 N-1 rule. This makes two app versions on one schema safe.
- **Before stage 3**: **same-host blue/green**. The new container starts next to the old one on the same `/data` volume (WAL allows two processes on one host), passes readiness, and Caddy switches its upstream; the old one drains and stops. Canary is the same mechanism with a weighted split. The host agent (ADR-0111) owns the switch.

### 5. Recovery: replicas and point-in-time restore are both needed

- A **replica** (warm standby restoring continuously from Litestream) covers host and disk loss: RPO about 10 s, RTO minutes plus a DNS or upstream switch.
- A replica copies logical damage (a bad migration, a buggy deploy, a bad bulk edit) within seconds. Only **point-in-time restore** (Litestream, 30 days) undoes it. Keep both.
- Restore time is the latest snapshot plus WAL replay since then. Lower `snapshot-interval` from 24 h to 1–6 h before stage 2 so replay stays short as the DB grows.

### 6. Postgres (managed, Scaleway RDB): not now; decide before v4 Phase 3

Postgres is justified when one of these fires first:

- two or more app hosts are needed (HA with fast failover, or CPU beyond the biggest sensible single box);
- zero-downtime deploys across hosts become a requirement;
- we prefer managed backup, PITR and failover to running Litestream;
- heavy analytical queries start competing with app traffic.

Costs to weigh: every query gains a network hop (about 0.5–1 ms), so query patterns that are free in-process with SQLite need an audit first; SQL moves off the sqlite dialect; the Litestream investment (drills, restore, replication probe, v4 erasure ledger) is replaced; tests lose the fast temp-SQLite DBs.

**Timing**: v4 Phase 3 (T-E08) rebuilds every money table for encrypted columns with the SQLite table-rebuild pattern. Moving to Postgres after it means doing that schema work twice, so the decision (T-SC12) is taken before T-E08 starts, from the T-SC05 and T-SC06 evidence.

### 7. Scaling the box up and down

- On prod's local SSD (ADR-0118) a resize is most likely a new instance plus a Litestream restore: minutes of downtime per resize. The STARDUST1-S quota is one per organisation, so the bigger box comes from another family (PLAY2/PRO2); check that quota ahead of need.
- A runbook for scale-up and scale-down is rehearsed on a drill until it is routine (T-SC10). Evaluate moving the root volume to block storage (SBS) so a resize becomes stop, change type, start (T-SC11).

### 8. Stage 3 spikes: pre-scale, keep the first hit static, queue only as a last resort

- **Marketing spikes are mostly predictable.** A campaign has a date: scale up before it and down once traffic settles (§7). This is the primary answer.
- The landing and sign-up pages are served as static files by Caddy, so a spike hits static files, not Python.
- A **load-triggered registration queue** (existing sessions always served; new sign-ups above a latency or CPU threshold are captured and activated later) is a documented last resort, not planned work. The operator considers delaying registration a product cost to avoid.
- Autoscaling (stateless app nodes plus Postgres) is revisited only if stage 3 shows sustained growth rather than bursts.

### 9. Monitoring additions

- **Host health heartbeat**: the host agent checks available memory (< ~15 %), disk use (> ~80 %), sustained CPU (> ~80 % for 10 min), CPU steal time and OOM kills, and pings an UptimeRobot heartbeat (push) monitor only while all are healthy. No new vendor; alerts land where the current three do. Sustained thresholds only: a single spike on one vCPU is normal. High steal with low usage means "move to a dedicated instance type", not "optimise the code".
- **Trends**: Scaleway Cockpit or node_exporter plus a free Grafana tier, for capacity planning (metrics carry no personal data).
- **Error tracking**: page 5xx and unhandled exceptions are alerted, since `/health` can be green while a page fails (Sentry or GlitchTip with PII scrubbing, or a log-based 5xx-rate alert; chosen in T-SC03).
- **Response-time alert** on the UptimeRobot `/health` monitor.

### 10. Isolation between users

v4 (ADR-0079..0083) defends against the operator and infrastructure, not against app-level access across users. It does help with read bugs: field ciphertext is bound to its owner (`aad = "bp/f/v1|<table>.<column>|u:<user_id>"`, ADR-0080) and decrypted with the owner's key, so a scoping bug cannot leak amounts, names or descriptions. It does not stop metadata leaks (dates, counts, FK graph, currency, colour) or **writes** on another user's row (soft delete, overwrite). Before stage 1, a test generated from the route list asserts that every route taking an id from the path or form returns 404, with no DB change, when the id belongs to another user, for both reads and writes (T-SC04). It adds to the ADR-0068 static check and the existing second-user tests.

### 11. Deferred until a measurement asks for them

ETag/304 conditional responses keyed on a per-user data version; smaller HTMX swaps; a minijinja engine switch; uvicorn workers before the bigger box. Each needs a profile or load-test finding before it is planned.

## Consequences

- Stages 1 and 2 need no architecture change: a few cheap serving and monitoring tasks, a measurement baseline and rehearsed runbooks.
- The k6 baseline (T-SC05) doubles as the "v3 baseline" that v4 T-E13 measures against.
- Postgres has a decision date (before T-E08) and written triggers instead of an open question.
- Stage 3 readiness is a separate gate: full load test, scalability plan, blue/green, warm standby.

## Alternatives considered

- **Microservices** (app, DB, replication split): rejected, see §2.
- **Fixed registration cap or waitlist by default**: rejected by the operator as a product cost; kept only as a load-triggered last resort (§8).
- **Full rewrite in Rust or C**: rejected; the Python-only prevention regime (ADR-0130) and test suite would not carry over. Targeted native hot paths instead (ADR-0153).
- **SQL aggregation now**: rejected, see §2.
- **Postgres now**: rejected until a §6 trigger fires; decided before v4 Phase 3.
