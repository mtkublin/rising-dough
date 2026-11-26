# Capacity and Performance — Tasks

> Plan: [README.md](README.md). Decisions: [ADR-0151](../../adr/0151-capacity-and-scaling-strategy-per-distribution-stage.md), [ADR-0152](../../adr/0152-python-upgrade-and-native-arm64-dev-interpreter.md), [ADR-0153](../../adr/0153-native-hot-paths-via-pyo3.md).
> Legend: `[P]` parallel-safe, `[S]` sequential, `→ T-SCxx` depends on upstream task. Templates, CSS or HTMX swaps changed → `frontend-visual-audit` at 1440 / 1024 / 375 before ✅ (CLAUDE.md).

---

## Now

### ◻ T-SC01 [P] Jinja `auto_reload` follows the environment (ADR-0151 §3)
- **Deliverables**: `web/templating.py` `build_jinja_env` passes `auto_reload=(settings.env == "dev")`; a comment notes the `cache_size` (400) headroom over the template count.
- **Acceptance**: unit test asserts `auto_reload` is `True` for `dev` and `False` for `test` and `production`; editing a template under `just dev` still shows on refresh (manual check, noted in the handoff).

### ◻ T-SC02 [P] Caddy serves `/static` with immutable caching (ADR-0151 §3)
- **Deliverables**:
  - Static assets get a per-release version in their URL (content hash or release version) through one template helper; every template reference uses it.
  - `Caddyfile.tpl`: `handle /static/*` with `file_server` from a read-only mount of the image's static directory and `Cache-Control "public, max-age=31536000, immutable"`; the app's `StaticFiles` mount stays for `just dev` only.
  - `reverse_proxy` gains `lb_try_duration 30s` and `lb_try_interval 250ms`.
- **Acceptance**: on a drill, `/static/*` responses carry the immutable header and are not in the app access log; a deploy changes asset URLs; a request sent during an app restart returns 200 after the restart, not 502.
- **Validation**: drill explore run; `frontend-visual-audit` (asset URLs change in templates).

### ◻ T-SC07 [S] Native arm64 dev toolchain (ADR-0152 §1)
- **Deliverables**: arm64 `uv` first on `PATH`; managed interpreters, `.venv` (main checkout and active worktrees) and pre-commit hook environments rebuilt on arm64; `docs/` developer setup note updated (no arch-specific key in `.python-version`).
- **Acceptance**: `uv --version` reports `aarch64-apple-darwin`; `file .venv/bin/python` reports arm64; hooks green.
- **Note**: a first native-uv install failed on 2026-11-26; operator retries.

### ◻ T-SC08 [S] Python upgrade probe and switch → T-SC07 (ADR-0152 §2–§5)
- **Deliverables**: branch with `uv lock --python 3.15`; every pin moved in one change (`requires-python`, `.python-version`, `Dockerfile`, workflows, ruff `target-version`, mypy `python_version`); ADR-0067 caps revisited; ADR-0152 accepted naming the version; `requirements.md` §3.1 and §3.6 updated.
- **Acceptance**: full CI, e2e and a drill gate green on the new version; if a dependency blocks 3.15, the same on 3.14 with the blocker and a revisit date recorded in ADR-0152.

## Before stage 1

### ◻ T-SC03 [P] Error tracking and response-time alert (ADR-0151 §9)
- **Deliverables**: choice recorded (Sentry or GlitchTip with PII scrubbing, or a log-based 5xx-rate alert); 5xx and unhandled exceptions alert the operator; UptimeRobot response-time alert on `/health`.
- **Acceptance**: a forced 500 on a drill raises an alert within 5 min and carries no request body, query string or financial values.

### ◻ T-SC04 [P] Cross-user route test from the route list (ADR-0151 §10)
- **Deliverables**: a test generated from the app's routes: for every route taking an entity id from the path or form, user B's id under user A's session returns 404 and leaves the DB unchanged (row count and `audit_log` unchanged), for GET and every mutating method. Routes without an entity id are listed as exempt with a reason.
- **Acceptance**: a new route with an id parameter and no case fails the test; a seeded scoping bug in one repository function is caught.

### ◻ T-SC05 [S] Load baseline and profile on a drill (ADR-0151 §2)
- **Deliverables**: k6 scenarios (login, `/today`, `/ledger`, `/budget`, `/overview`, `/forecast`, a mutation mix) against a seeded explore drill; py-spy flame graphs of 2–3 heavy pages under load; `docs/plans/scaling/baseline.md` with requests per second at p95 targets, CPU, memory and steal per page.
- **Acceptance**: numbers reproduce within ±10 % on a second run; the file is the reference for v4 T-E13 ("v3 baseline").

### ◻ T-SC09 [P] Host health heartbeat (ADR-0151 §9)
- **Deliverables**: host agent check for available memory, disk use, sustained CPU, CPU steal and OOM kills; it pings an UptimeRobot heartbeat monitor only while all are under threshold; trend collection (Scaleway Cockpit or node_exporter plus a free Grafana tier) chosen and documented.
- **Acceptance**: on a drill, filling the disk past the threshold or a forced OOM stops the heartbeat and raises an alert; the heartbeat URL is a secret, never in plan output (ADR-0098).

## Before stage 2

### ◻ T-SC06 [S] Fix what the profile shows → T-SC05
- **Deliverables**: N+1 queries and missing indexes from the T-SC05 profile fixed (`tests/query_counting.py` bounds tightened); long write transactions shortened; the list of CPU-bound pure functions handed to T-SC13.
- **Acceptance**: re-run of T-SC05 recorded in `baseline.md` with the change per page.

### ◻ T-SC10 [S] Scale-up and scale-down runbook (ADR-0151 §7)
- **Deliverables**: `docs/plans/v3/runbooks/` entry for resizing prod (target families and quota check, restore path, DNS or upstream switch, verification); rehearsed twice on a drill.
- **Acceptance**: two drill rehearsals with measured downtime and zero lost rows recorded.

### ◻ T-SC11 [S] Block-storage root volume evaluation → T-SC10 (ADR-0151 §7)
- **Deliverables**: compare local SSD and SBS for resize time, disk latency under the T-SC05 load and cost; decision recorded as an amendment to ADR-0118.
- **Acceptance**: measured numbers from a drill on both volume types.

### ◻ T-SC15 [S] Expand/contract migrations and a shorter snapshot interval (ADR-0151 §4–§5)
- **Deliverables**: migration rule (each release's schema works with the previous release's code) added to the ADR-0071 text as an amendment and to the migration review checklist; Litestream `snapshot-interval` lowered to a measured value between 1 h and 6 h.
- **Acceptance**: restore time on a drill recorded before and after the snapshot change.

## Before v4 Phase 3

### ◻ T-SC12 [S] Postgres decision → T-SC05, T-SC06 (ADR-0151 §6)
- **Deliverables**: an ADR (accept or reject Postgres) weighing the ADR-0151 §6 triggers against the measured baseline; if accepted, the migration plan lands before T-E08.
- **Acceptance**: decided before T-E08 starts.

## After the profile

### ◻ T-SC13 [S] PyO3 pilot: SVG charts → T-SC06, T-SC08 (ADR-0153 §1–§5)
- **Deliverables**: Rust crate built with maturin in the image and CI; native `web/charts.py` hot path behind the Python facade; Hypothesis oracle test asserting byte-equal SVG; `cargo fmt`, `clippy -D warnings`, `cargo test` in hooks and CI; build time and image size change recorded.
- **Acceptance**: oracle test green on generated inputs; measured CPU gain on the chart pages in `baseline.md`; ADR-0153 accepted or rejected from the result.

### ◻ T-SC14 [P] Further native ports → T-SC13 (ADR-0153 §6)
- **Deliverables**: one item per candidate the profile backs (recurring expansion, forecast roll-ups, formula evaluator, v4 batch decrypt), each with an oracle test.
- **Acceptance**: each port shows a measured gain; ports without a gain are not merged.

## Before stage 3

### ◻ T-SC16 [S] Stage 3 readiness (ADR-0151 §4, §5, §8)
- **Deliverables**: full load test with spike scenarios and a written scalability plan; same-host blue/green in the host agent; warm standby restoring from Litestream with a failover runbook; landing and sign-up pages served statically by Caddy; pre-scale runbook for campaigns.
- **Acceptance**: a drill deploy under load drops no request; a failover rehearsal meets RPO ≤ 10 s and a recorded RTO.
