# Faster CI — Tasks

> Plan: [README.md](README.md). Decision: [ADR-0108](../../adr/0108-faster-ci-parallel-tests-and-change-based-inner-loop.md).
> Legend: `[P]` parallel-safe, `[S]` sequential, `→ T-CSxx` depends on upstream task.

---

### ✅ T-CS01 [S] Measure and profile
- **Deliverables**: `docs/plans/ci-speed/baseline.md` with wall times for the GitHub `ci` job (per step, last 5 green runs), local `just ci`, `just test`, the pre-commit hook, `mypy`; `pytest --durations=50` output; the top slow tests grouped by cause (hashing, migrations, sleeps, browser start-up, other).
- **Acceptance**: every test over 1 s has a cause and a proposed fix or a reason to keep it.
- **Validation**: numbers reproducible within ±10% on a second run.

### ✅ T-CS02 [S] Fix slow-test causes → T-CS01
- **Deliverables**: fixes from the T-CS01 list, for example a test-only low-cost password-hasher setting (production default unchanged and asserted by a test), a migrated template DB copied per test instead of migrating each time, removed real sleeps, session-scoped browser where safe.
- **Acceptance**: the full suite passes unchanged in what it asserts; coverage ≥ 90%; serial suite time reduced, recorded in `baseline.md`.
- **Validation**: `just ci`

### ✅ T-CS03 [S] Parallel tests with xdist → T-CS02
- **Deliverables**:
  - A random-order run (`pytest-randomly` or equivalent) over the full suite; every order dependence fixed.
  - `-n $PYTEST_WORKERS --dist loadgroup` in `just test` / `just ci` and in `ci.yml` (`PYTEST_WORKERS=auto` default); `xdist_group` or `worker_id`-derived ports for `tests/e2e/` and `tests/visual/` session resources.
  - Pre-commit pytest hook runs with `-n $PYTEST_WORKERS`.
  - `orchestrator-mode` skill brief sets `PYTEST_WORKERS=2` for item agents (ADR-0097 contention).
- **Acceptance**: full suite green 5 times in a row with `-n auto` and random order; coverage report identical in total to the serial run (±0.1%); no port or file collisions.
- **Validation**: `for i in 1 2 3 4 5; do just ci || break; done`

### ✅ T-CS04 [P] Change-based inner loop → T-CS03
- **Deliverables**:
  - Spike: `pytest-testmon` with our plugins (xdist, pytest-cov, pytest-asyncio, Playwright). Result and the chosen mode (parallel or serial, coverage off) in `baseline.md`.
  - `just lint-changed BASE=<ref>`: `pre-commit run --from-ref "$(git merge-base HEAD "$BASE")" --to-ref HEAD`.
  - `just test-changed BASE=<ref>`: testmon selection, with the ADR-0108 §3 fallback path list (templates, static, `migrations/`, SQL, `pyproject.toml`, `uv.lock`, any `conftest.py`, `tests/fixtures/`, CI config) triggering the full suite.
  - `just worktree-init`: copies `.testmondata` from the main checkout into a new worktree; `.testmondata` gitignored.
  - Pre-commit pytest hook switched to testmon selection over the ADR-0097 §7 fast paths.
- **Acceptance**: a one-module change in `services/` selects its tests and the integration tests that exercise it, and not the rest; a template change runs the full suite; a seeded change to a function used only by one integration test selects that test.
- **Validation**: scripted scenarios in `tests/architecture/test_change_selection.py` or a recorded run log.

### ✅ T-CS05 [P] CI caches → T-CS03
- **Deliverables**: `actions/cache` for `.mypy_cache` keyed on `uv.lock` + `src/**` hash with a restore-key fallback; check the uv cache stays enabled; Playwright browser cache if CI installs browsers.
- **Acceptance**: second run on an unchanged tree shows a cache hit and a shorter `mypy` step; a type error in a changed file is still reported.

### ✅ T-CS06 [S] Docs, policy and measurement → T-CS04, T-CS05, T-CS07
- **Deliverables**:
  - ADR-0097 marked "Amended by ADR-0108"; `orchestrator-mode` skill and agent briefs: item agents run `just lint-changed` + `just test-changed` against `BASE` instead of hand-picked scoped checks; batch CI unchanged.
  - `CLAUDE.md` developer commands updated (`just lint-changed`, `just test-changed`, `just worktree-init`, `PYTEST_WORKERS`); `docs/requirements.md` §3 tooling lines.
  - `baseline.md` "after" column against every target in README.
- **Acceptance**: targets met, or the gap explained with a follow-up task; ADR-0108 flipped to Accepted; `docs/CHANGELOG.md` entry.

### ✅ T-CS07 [S] Pre-commit as the local gate → T-CS04 (ADR-0120)
- **Deliverables**:
  - `just test-fast` (the pre-commit pytest hook): testmon selection over the whole default selection (unit, integration, web, architecture, e2e), xdist, no coverage; staged files on `_unseen-paths` run the full default selection.
  - Policy: no local full `just ci` required — `CLAUDE.md` handoff checklist, `orchestrator-mode` skill (item-agent checks and the batch-CI step), ADR-0097 / ADR-0108 status lines, `docs/requirements.md` §11.2.
- **Acceptance**: a one-module service change selects its unit **and** integration tests at commit; a migration / `conftest.py` / dependency change runs the full default selection at commit; a docs-only commit runs no tests.
- **Validation**: recorded hook runs in `baseline.md`.

### ✅ T-CS08 [S] GitHub job reliably under 2 min → T-CS06
- **Context**: after T-CS01…T-CS07 the `ci` job median is 2:15 (1:32–2:38) with pytest at 61–118 s on the same commit; local targets are met (`baseline.md`).
- **Deliverables**: `--durations=30` under xdist on the runner (several runs) to separate runner variance from slow tests; then the cheapest fix among: per-worker load balance (`--dist load` vs `loadgroup`, `--maxworkers`), the FastAPI per-app route-state cost (~70–100 ms per web test, T-CS01), or splitting lint + typecheck into a parallel job (ADR-0108 alternative, deferred). A new ADR if the job layout changes.
- **Acceptance**: median of 5 runs under 2:00.
- **Findings** (`baseline.md` "T-CS08 — runner profile"): median 2:04 over 4 attempts of one commit. The spread is the runner CPU (68–102 s pytest). The largest avoidable cost is FastAPI's lazy route state on each new app's first request (~87 ms CPU per web test).
- **Result**: step 1 landed (median of 5 runs 1:56; the slowest CPU still 2:12–2:15). Step 2 (sharding) was declined by the operator on 2026-11-18; revisit if the median drifts above 2:00.
- **Step 1**: cache `get_typed_signature` in `tests/conftest.py` (test process only; production unchanged), measure 4 attempts. If the median stays ≥ 2:00, step 2 is to shard pytest over two parallel jobs and combine coverage (needs an ADR: new job layout and required-check names).

### ✅ T-CS09 [S] Path-filtered Terraform checks are no longer required → ADR-0121
- **Context**: PR #23 had no Terraform changes, so the path-filtered `terraform.yml` never posted its three required checks and the PR stayed blocked. The operator removed them from the `protect-main` ruleset by hand on 2026-11-18 (no bypass, no drill gate rerun).
- **Deliverables**: ADR-0121; `github-settings.md` §3 lists the actual required checks; CHANGELOG line.
- **Acceptance**: a PR without Terraform changes is mergeable once `drill-gate`, `just ci`, the lock check and the security scans pass.

### T-CS20 [S] Measure billable CI minutes per job → ADR-0151
- **Context**: ADR-0151 rests on an estimate (~20k–40k billable min/month); the full fetch was stopped by the API rate limit on 2026-11-27.
- **Deliverables**: `baseline.md` section "Billable minutes": 30 days of jobs, each rounded up to a whole minute, per workflow and job, peak concurrent jobs per hour; fetched under the rate limit (resumable cache, ≤ 4,000 calls/h).
- **Acceptance**: ADR-0151 Context and Consequences updated with the measured numbers before the ADR is accepted.

### T-CS21 [P] Trim CI minutes → ADR-0151
- **Deliverables**: `concurrency` with `cancel-in-progress` on PR workflows; no duplicate push + pull_request runs on the same commit; path filters where the check is not required (ADR-0121); Security scans on PRs that change dependencies or the image, plus the weekly schedule.
- **Acceptance**: required checks unchanged; T-CS20 numbers re-measured over 7 days show the saving.

### T-CS22 [S] Runner host: `terraform/ci-runner` + `ci-runner.yml` → ADR-0151, T-CS20
- **Deliverables**: separate Scaleway project and scoped API key; Terraform stack `terraform/ci-runner` (`DEV1-L`, Flex IPv4, security group with no inbound, cloud-init: Docker, unattended-upgrades, two ephemeral-workspace runner processes with label `rd-ci`); hosted `ci-runner.yml` (environment `ci-runner`, `main`-only) that mints a one-hour registration token and applies, weekly and on dispatch; `ci_environments.toml` entry; Scaleway billing alert.
- **Acceptance**: a dispatched rebuild registers two online runners; the old host is destroyed; no long-lived GitHub credential on the host.
- **Validation**: ADR-0108 job times re-measured on the runner (5 runs of `ci`, `e2e`).

### T-CS23 [S] Move secret-free workflows behind `vars.CI_RUNS_ON` → T-CS22
- **Deliverables**: `runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '"ubuntu-latest"') }}` in `ci.yml`, `e2e.yml`, `security.yml`, `visual.yml`, `lock-check.yml`, `a11y-perf.yml`, `mutation.yml`; guard test: a job using that expression has no `environment:`, no `secrets.*` other than `GITHUB_TOKEN`, no `id-token: write`; `docs/requirements.md` §3.6 runner line.
- **Acceptance**: with the variable unset every job runs on `ubuntu-latest` (green); with it set the same jobs run on `rd-ci` (green); deleting the variable falls back within one run.

### T-CS24 [S] Operator: go private → T-CS23
- **Deliverables**: GitHub Pro; Actions spending limit (~$25); set `CI_RUNS_ON`; switch visibility; `scripts/check_github_settings.py` run; `prod` / `prod-restore-read` reviewers and `protect-main` / release-tag rulesets confirmed enforced; CHANGELOG line.
- **Acceptance**: a PR merges with all required checks green on the runner; a release from `main` passes the `prod` approval.
