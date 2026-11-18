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

### ◻ T-CS05 [P] CI caches → T-CS03
- **Deliverables**: `actions/cache` for `.mypy_cache` keyed on `uv.lock` + `src/**` hash with a restore-key fallback; check the uv cache stays enabled; Playwright browser cache if CI installs browsers.
- **Acceptance**: second run on an unchanged tree shows a cache hit and a shorter `mypy` step; a type error in a changed file is still reported.

### ◻ T-CS06 [S] Docs, policy and measurement → T-CS04, T-CS05, T-CS07
- **Deliverables**:
  - ADR-0097 marked "Amended by ADR-0108"; `orchestrator-mode` skill and agent briefs: item agents run `just lint-changed` + `just test-changed` against `BASE` instead of hand-picked scoped checks; batch CI unchanged.
  - `CLAUDE.md` developer commands updated (`just lint-changed`, `just test-changed`, `just worktree-init`, `PYTEST_WORKERS`); `docs/requirements.md` §3 tooling lines.
  - `baseline.md` "after" column against every target in README.
- **Acceptance**: targets met, or the gap explained with a follow-up task; ADR-0108 flipped to Accepted; `docs/CHANGELOG.md` entry.

### ◻ T-CS07 [S] Pre-commit as the local gate → T-CS04 (ADR-0117)
- **Deliverables**:
  - `just test-fast` (the pre-commit pytest hook): testmon selection over the whole default selection (unit, integration, web, architecture, e2e), xdist, no coverage; staged files on `_unseen-paths` run the full default selection.
  - Policy: no local full `just ci` required — `CLAUDE.md` handoff checklist, `orchestrator-mode` skill (item-agent checks and the batch-CI step), ADR-0097 / ADR-0108 status lines, `docs/requirements.md` §11.2.
- **Acceptance**: a one-module service change selects its unit **and** integration tests at commit; a migration / `conftest.py` / dependency change runs the full default selection at commit; a docs-only commit runs no tests.
- **Validation**: recorded hook runs in `baseline.md`.
