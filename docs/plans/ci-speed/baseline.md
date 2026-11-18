# Faster CI — Baseline and Results

> Plan: [README.md](README.md). Tasks: [tasks.md](tasks.md) (T-CS01 baseline, T-CS06 after).

## Method

- **GitHub CI is the absolute reference.** Hosted runners are clean; the developer machine usually runs several agents at once (load average 9–27 on 8 cores while measuring on 2026-11-18), so local wall times are not comparable between runs.
- **Local numbers** are used to rank slow tests and to compare before/after **back-to-back**, as CPU time (user + sys) as well as wall time, with `uptime` recorded next to each figure.
- Branch runs are measured through the draft PR for `feat/ci-speed` (CI runs on each push).

## GitHub `ci` job — last 5 green runs on `main` (2026-11-18)

| Run start (UTC) | Job | `just ci` step | Setup (checkout → sync → npm) |
|---|---|---|---|
| 13:06:42 | 3:36 | 3:16 | ~16 s |
| 13:33:05 | 4:14 | 3:53 | ~16 s |
| 13:33:39 | 5:08 | 4:42 | ~19 s |
| 14:54:44 | 5:10 | 4:50 | ~15 s |
| 15:31:03 | 3:34 | 3:13 | ~16 s |
| **median** | **4:14** | **3:53** | **~16 s** |

Breakdown of the `just ci` step (run 15:31:03):

| Step | Time |
|---|---|
| ruff | 0.1 s |
| sqlfluff | 5.3 s |
| djlint | 2.5 s |
| stylelint | 0.7 s |
| mypy (cold, no cache) | 6.5 s |
| pytest (2,233 passed, 53 skipped, 16 deselected) | 176.9 s |

Run-to-run spread is wide (3:13–4:50 for the same step), so before/after comparisons use the median of several runs.

**Observation:** pytest is ~95% of the step. mypy without a cache is only ~6.5 s, so the mypy cache (T-CS05) has a small ceiling.

Note: the GitHub run skips 37 more tests than a local run (53 vs 16): the e2e suite skips itself because CI does not install Chromium. Local and CI test counts differ for that reason only.

## Local (8 cores, shared machine)

Serial, full default selection (`uv run pytest`, coverage on), pristine `main` @ `da05e10`:

| Run | Load avg (start → end) | Wall | CPU (user + sys) | Result |
|---|---|---|---|---|
| 1, `--durations=60` | ~27 (15-min) | 916 s | 683 s | 2,245 passed, 16 skipped |
| 2, `--durations=0` + fixture timer | 17.5 → 6.9 | 735 s | — | 2,245 passed, 16 skipped |

Docker Desktop was switched off part-way through the session, so local figures are compared only back-to-back, never across runs at different times.

### Reproducible subset (A/B reference for T-CS02…)

`pytest --no-cov tests/unit tests/integration tests/architecture`, run alternately against pristine `main` and the branch:

| Run | Load avg at start | Wall | CPU (user + sys) |
|---|---|---|---|
| main #1 | 15.7 | 173.2 s | 158.9 s |
| main #2 | 5.0 | 175.1 s | 160.7 s |

Spread between the two `main` runs: 1% wall, 1% CPU — within the ±10% reproducibility bar.

## Where the time goes (run 2)

By directory and phase, top entries:

| Directory | Phase | Total | Tests |
|---|---|---|---|
| `integration/web` | setup | 345 s | 677 |
| `integration/web` | call | 119 s | 386 |
| `e2e` | setup | 82 s | 15 |
| `unit/services` | setup | 38 s | 427 |
| `e2e` | call | 26 s | 15 |
| `integration/startup` | call | 18 s | 17 |
| `integration/auth` | setup | 15 s | 43 |
| `unit/deploy` | call | 12 s | 51 |

Fixture setup (inclusive; nested fixtures double-count):

| Fixture | Calls | Mean | Total |
|---|---|---|---|
| `client` (web) | 524 | 392 ms | 205 s |
| `_migrated` (web) | 642 | 127 ms | 82 s |
| `live_server` (e2e) | 15 | 4.9 s | 73 s |
| `conn` (unit/integration) | 731 | 94 ms | 69 s |
| `anon_client` (web) | 70 | 476 ms | 33 s |

Breakdown of one web `client` setup on an idle-ish machine (micro-benchmark, mean of 10):

| Piece | Time |
|---|---|
| `apply_migrations` on a fresh file | ~100–130 ms |
| Copying a migrated file instead | ~1 ms |
| `create_app` | <1 ms |
| TestClient enter (lifespan) | ~2 ms |
| **First request on a new app** (priming `GET /healthz`) | **~70–100 ms** |
| Later requests on the same app | ~4 ms (404), ~17 ms (`/ledger`) |

The first-request cost is FastAPI 0.161 building per-route dependency state (`_populate_api_route_state` → `get_dependant`) for ~560 routes, once per app instance. A shared Jinja environment does not change it.

## Slow tests by cause

115 test phases took ≥ 1 s in run 2. Run 2 overlapped with other local runs for a while (the `integration/web/test_accessibility.py` setups at 2–3 s fall in that window), so the table groups by cause rather than by exact duration.

| Cause | Where | Typical cost | Decision |
|---|---|---|---|
| Every migration applied per test | ~1,500 DB-backed tests (`integration/web`, `unit/services`, `unit/repositories`, `integration` `conn`) | 100–130 ms each | **Fix (T-CS02):** migrate a template once per process, copy per test |
| FastAPI per-app route state | every new app, ~650 web tests | 70–100 ms each | **Follow-up candidate.** Only fixable by sharing one app across tests (weakens isolation) or patching FastAPI internals (against the "tools' own mechanisms" guardrail). xdist divides it by worker count. |
| Web fixture setup under contention | `integration/web/test_accessibility.py`, `test_accounts.py` | 1–3 s in run 2 | Not a cost of its own: same `client` fixture as above, inflated by load. Re-check after T-CS02. |
| uvicorn subprocess + browser context per test | 15 `e2e` tests | ~4.9 s setup | Keep for now: real-server journeys are the point. Not run in GitHub CI (no Chromium). Revisit with xdist groups in T-CS03. |
| Real subprocess / signal handling | `integration/startup/*`, `integration/web/test_graceful_shutdown.py`, `unit/deploy/test_prod_db_seed.py` | 1–4 s | Keep: the process boundary is what they test. |
| Whole-repo static scan | `architecture/test_user_id_filter.py` | ~1.5 s | Keep: one test. |
| Large-page parsing | `integration/web/test_accessibility.py` calls (BeautifulSoup over full pages) | 1–4 s in run 2 | Re-check without load after T-CS02. |
| Parquet export | `integration/web/test_planned.py::test_export_parquet` | ~7 s first call (pyarrow import) | Keep: one-off import cost per process. |

No real `sleep`-driven tests over 1 s were found. Password hashing is already at bcrypt cost 4 in tests.

## Findings for later tasks

- **Order dependence (T-CS03):** `integration/web/test_no_values_in_logs.py::test_ledger_search_sentinel_absent_from_logs` fails when `tests/unit` runs before it (reproduced on pristine `main`). A unit test leaves logging / structlog configured so the app's log lines don't reach the test's handler. It passes in the default `testpaths` order, which is why CI is green.

## T-CS02 results

### Migrated template DB copied per test

`tests/db_template.py` + `migrated_template` / `migrated_db` fixtures in `tests/conftest.py`; the four per-test migration fixtures now copy the template. `tests/unit/db/test_db_template.py` proves a copy equals a fresh migration (schema, seed rows with timestamps masked, `schema_migrations` checksums, WAL mode), that tests never share a copy, and that a second fixture in the same test never wipes the first one's rows.

Same subset as above, alternating with the `main` runs:

| Run | Load avg at start | Wall | CPU (user + sys) |
|---|---|---|---|
| branch #1 | 8.1 | 122.6 s | 111.9 s |
| branch #2 | 5.9 | 114.6 s | 107.6 s |
| **change vs `main` (mean)** | | **−32%** | **−32%** |

GitHub `ci` job (pytest line in the log; the runner is noisy, so medians):

| Commit | Job | pytest | Coverage |
|---|---|---|---|
| baseline: 5 runs (4 on `main` branches + `8d24a84` docs-only) | median 4:47 | 177 / 215 / 242 / 257 / 263 s, **median 242 s** | — |
| `da8437d` (template DB) | 4:03 | **195.5 s** (−19% vs median, 1 sample) | 94.65% |

GitHub `ci` job on `1f7a073` (4 xdist workers on the 4-vCPU public-repo runner):

| Commit | Job | pytest | Coverage |
|---|---|---|---|
| `1f7a073` (template DB + xdist) | **1:56** | **70.8 s** (−71% vs median 242 s) | 94.65% |

### Five consecutive `just ci` runs, `-n auto` + random order (first attempt)

Seeds 1111 and 2222 green. Seed 3333 failed one e2e test (`test_passkey_journey.py::test_stale_session_reauths_with_passkey`, Playwright 30 s navigation timeout) at **load average 123**, while the T-CS04 testmon spike ran in parallel in another worktree. Attempt discarded as not representative; repeated below on a quieter machine.

## T-CS04 results — change-based inner loop

### Spike: pytest-testmon 2.3 with our plugins

| Question | Result |
|---|---|
| xdist | Works: selection and data writes are correct with `-n 2` / `-n 4`. |
| pytest-cov | Testmon stops recording under coverage, so the inner loop runs `--no-cov`. Gates keep coverage. |
| `-m` in `addopts` | Testmon turns selection off when `-m` is given; `--testmon-forceselect` keeps both. |
| Jinja templates | Seen: compiled templates carry the template filename, so testmon fingerprints them and reruns the tests that render a changed template. The fallback still covers templates (static files, CSS and any path not traced). |
| Subprocesses (uvicorn in e2e) | Tracked by default. |
| Chosen mode | Parallel (`-n $PYTEST_WORKERS`), coverage off. |

### Recipes

- `just lint-changed [BASE]` — `pre-commit run --from-ref $(git merge-base HEAD BASE) --to-ref HEAD`, pytest hook skipped. 2.5 s on a docs + justfile diff.
- `just test-changed [BASE]` — testmon selection; full suite when the diff against BASE (committed, staged, unstaged and untracked) has a path testmon cannot see. The one fallback list is `_unseen-paths` in the `justfile`: every non-Python file outside `docs/` and Markdown, plus any `conftest.py`.
- `just test-fast` — the pre-commit pytest hook: ADR-0097 §7 fast subset through testmon; staged files on the fallback list run the whole subset.
- `just worktree-init` — copies `.testmondata` from the main checkout (`.testmondata*` gitignored).

`just` takes recipe arguments by position: `just test-changed main`, not `BASE=main`.

### Selection scenarios (recorded run log, `just test-changed HEAD` on `358c493`)

| Scenario | Selected | Time |
|---|---|---|
| No change after a full run | 0 ("no tests ran") | 5–6 s |
| One function body in `services/ledger_totals.py` | 16: its 4 unit tests + 11 `integration/web/test_ledger.py` + 1 `test_transactions.py` (the routes that call it) | 7 s |
| Template `ledger/_table.html` | Full suite via the fallback (2,249) | 78 s |
| After reverting that template | 51 tests that render it (testmon sees the template) | 13 s |
| Docs-only change | 0 | 5 s |
| `services/income.py::next_anchor_date`, exercised by exactly one integration test | 50: 49 unit + `integration/web/test_budget_left_daily_spend.py::test_left_daily_spend_card_renders_number_and_caption` | 6 s |

### Pre-commit pytest hook

| Run | Wall |
|---|---|
| First run, no `.testmondata` (whole fast subset, 4 workers) | 14.9 s |
| No affected tests | 2.9 s |

Target "pre-commit hook on a small diff under 15 s" and "`just test-changed` on a one-module diff under 30 s": met (3–7 s).

### Five consecutive `just ci` runs, xdist auto + random order (acceptance, T-CS03)

| Run | Seed | Load avg at start | pytest | Coverage |
|---|---|---|---|---|
| 1 | 7777 | 7.2 | 75.4 s | 94.65% |
| 2 | 15554 | 13.5 | 84.2 s | 94.65% |
| 3 | 23331 | 29.9 | 84.6 s | 94.65% |
| 4 | 31108 | 41.5 | 83.8 s | 94.65% |
| 5 | 38885 | 40.6 | 79.4 s | 94.65% |

All green (2,249 passed each), including the e2e suite, with other agents loading the machine.

## T-CS05 results — CI caches

- `actions/cache@v4` for `.mypy_cache`: key `mypy-<os>-py3.12-<hash uv.lock>-<hash src/**/*.py, tests/**/*.py, pyproject.toml>`, restore-key `mypy-<os>-py3.12-<hash uv.lock>-` (newest cache for the same dependencies).
- uv cache: already on (`astral-sh/setup-uv` `enable-cache: true`, keyed on `uv.lock`).
- Playwright browsers: CI installs none (e2e skips there), so no cache.
- Local check of the incremental cache: warm `mypy src tests` 0.8 s; an injected type error in `services/ledger_totals.py` is still reported against the warm cache.

GitHub CI cache check on `f219ff6`:

| Run | mypy cache | mypy | pytest | Job |
|---|---|---|---|---|
| first | miss, saved | 11.6 s | 103 s | 2:34 |
| rerun, same commit | **hit** | **0.3 s** | 61 s | 1:32 |

## T-CS07 results — pre-commit is the local gate (ADR-0120)

Hook runs (`pre-commit run pytest-fast --verbose` on a staged change, 8 cores):

| Staged change | Hook ran | Time |
|---|---|---|
| One function body in `services/ledger_totals.py` | 16: 4 unit + 12 integration (`test_ledger.py`, `test_transactions.py`) | 9.2 s |
| A `conftest.py` | full default selection via the fallback: 2,249 | 68.8 s |
| Docs only | none ("no tests ran") | 6.3 s |
| The ADR-0120 commit itself (`justfile`, YAML, docs) | full default selection via the fallback | ~70 s |

## T-CS06 — results against the targets

Local `just ci`, back-to-back, pristine `main` vs the branch (shared venv, `UV_NO_SYNC=1`; the `main` runs report 0% coverage because the venv imports `src` from the branch worktree, so they traced nothing — their coverage overhead is lower than a real run's, which makes the ratio conservative):

| Run | Load avg at start | Wall | CPU (user + sys) |
|---|---|---|---|
| main #1 | 17.4 | 401.7 s | 389.7 s |
| branch #1 | 5.1 | 107.6 s | 553.5 s |
| main #2 | 26.7 | 311.0 s | 310.2 s |
| branch #2 | 2.1 | 84.7 s | 486.5 s |
| **mean** | | **356 s → 96 s (3.7×)** | |

GitHub `ci` job with xdist (4 workers):

| Commit | Job | pytest |
|---|---|---|
| `1f7a073` | 1:56 | 70.8 s |
| `f219ff6` | 2:34 | 103.1 s |
| `f219ff6` rerun | 1:32 | 60.9 s |
| `d7e7047` | 2:38 | 117.9 s |
| **median** | **2:15** | **87 s** |

| Target (README) | Baseline | After | Status |
|---|---|---|---|
| GitHub `ci` job under 2 min | median 4:47 (pytest median 242 s) | median 2:15 (1:32–2:38; pytest 61–118 s) | **Not met reliably** — 2 of 4 runs under 2:00. Gap: runner-to-runner pytest variance (61–118 s on the same commit). Follow-up T-CS08. |
| Local full `just ci` ≥ 3× faster | 356 s | 96 s | **Met: 3.7×** |
| Pre-commit hook on a small diff < 15 s | 30 s (unit-only subset, serial) | 6–9 s (affected tests across the whole suite) | **Met** |
| `just test-changed` on a one-module diff < 30 s | — | 6–7 s | **Met** |
| Coverage gate unchanged, 90%, full suite | 94.65% | 94.65% (serial, xdist 4, xdist 8, CI) | **Met** |
