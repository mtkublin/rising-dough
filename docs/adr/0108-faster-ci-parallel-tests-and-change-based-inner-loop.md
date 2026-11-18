# ADR-0108: Faster CI — Parallel Tests, Change-Based Inner Loop, Full Suite at the Gates

- **Status**: Proposed
- **Date**: 2026-11-16
- **Amends**: [ADR-0097](0097-per-batch-ci-policy-and-fast-precommit-pytest.md) (item-agent "scoped checks" and the pre-commit pytest hook), [ADR-0018](0018-ci-single-matrix-row.md) (CI job steps and caches)
- **Relates to**: [ADR-0066](0066-orchestrator-mode-skill.md), [ADR-0099](0099-release-and-environment-policy.md), [ADR-0106](0106-ui-behaviour-test-harness.md)

## Context

- The GitHub `ci` job takes about 4.5 minutes. Setup is about 15 s; the rest is `just ci` (ruff, sqlfluff, djlint, stylelint, `mypy --strict`, then about 2,000 tests with coverage and a 90% gate).
- `pytest-xdist` is already a dev dependency but nothing passes `-n`, so the suite runs on one core. Developer machines have 8 cores; GitHub-hosted runners have 2–4.
- Locally every check runs over the whole repo even when a branch touches three files. Orchestrator item agents run "scoped checks" (ADR-0097) chosen by hand, which is inconsistent and sometimes misses affected tests.
- The coming work is test-heavy (quality-audit remediation, UI test harness, redesign), so CI time is paid many times over.

The operator's direction: run checks only on what a branch changed against its base (main for a long-running feature branch, the feature branch for an orchestrator item branch), preferring the tools' own mechanisms over custom logic; and parallelise the tests.

## Decision

### 1. Parallel tests everywhere

- `pytest-xdist` with `-n auto` in GitHub CI and in `just test` / `just ci`. `pytest-cov` combines worker data, so the 90% gate is unchanged.
- Tests that share a session resource (live server, browser, fixed ports in `tests/e2e/` and `tests/visual/`) use `xdist_group` with `--dist loadgroup`, or per-worker ports derived from `worker_id`.
- **CPU cap for parallel agents.** In orchestrator mode several agents run tests at once (the ADR-0097 contention problem). Local recipes read `PYTEST_WORKERS` (default `auto`); the orchestrator brief sets it to `2` for item agents.
- A random-order run (`pytest-randomly` or `-p random_order`) is part of the rollout to flush out order dependence before `-n auto` becomes the default.

### 2. Fix slow tests before (and alongside) parallelism

- Profile with `--durations=50`. Typical outliers are fixed at the source: password hashing at production cost in fixtures (use a low-cost test hasher setting), migrations run per test instead of copying a migrated template DB, real sleeps or timeouts, Playwright started per test.
- **Slimmer suite.** The quality audit's Mutmut baseline and per-test coverage contexts (`--cov-context=test`) give candidates for redundant tests: tests that cover nothing and catch no mutant that other tests don't. Candidates go to Track F (T-Q09) as findings. Deleting them is remediation, never automatic.

### 3. Change-based checks in the inner loop, using the tools' own mechanisms

The base ref is the merge-base of `HEAD` and the branch's parent: `origin/main` for feature branches, the main work branch for orchestrator item branches (named in the agent brief as `BASE`).

- **Lint and format:** `pre-commit run --from-ref "$(git merge-base HEAD "$BASE")" --to-ref HEAD`, exposed as `just lint-changed`. No custom file selection.
- **Type checking:** `mypy --strict` stays whole-repo, because checking only changed files misses errors in their callers. Speed comes from the incremental cache: `.mypy_cache` is persisted in CI (`actions/cache`) and reused locally.
- **Tests:** `pytest-testmon` selects the tests affected by the changed code, from its record of which code each test runs. Exposed as `just test-changed`. It is not a gate (§4).
- **Fallback to the full suite.** `just test-changed` runs the full suite when the diff touches anything testmon cannot see: templates, static files, `migrations/`, SQL, `pyproject.toml`, `uv.lock`, any `conftest.py`, `tests/fixtures/`, or CI config. This list lives in one place in the `justfile`. *Implemented (T-CS04) as the general rule "any non-Python file outside `docs/` and Markdown, plus any `conftest.py`": the deploy tests also read Terraform, shell and cloud-init files that a named list would miss.*
- **Testmon data per worktree.** A new worktree has no testmon data and would run everything. `just worktree-init` copies `.testmondata` from the main checkout at creation; stale entries only cause extra tests to run, never fewer. No shared live data file between concurrent agents.
- If the spike (T-CS04) shows testmon is incompatible with xdist or the coverage plugin in our setup, the inner loop runs the selected tests serially and without coverage; the selected set is small.

### 4. Gates always run the full suite

| Where | What runs |
|---|---|
| Pre-commit hook | changed-file lint (pre-commit's own diff) + `pytest` fast subset via testmon (ADR-0097 §7 paths), `-n $PYTEST_WORKERS` |
| Orchestrator item agent before handoff | `just lint-changed` + `just test-changed` against `BASE` (replaces hand-picked "scoped checks") |
| Orchestrator batch CI on the main work branch | full `just ci`, parallel (ADR-0097 §2 unchanged) |
| Single-agent work before handoff | full `just ci`, parallel |
| GitHub `ci.yml` (PR to `main`, `release.yml` call) | full `just ci`, parallel, with uv and mypy caches |

GitHub CI only runs at release gates (ADR-0099), so change-based selection is **not** used there.

## Consequences

- Expected: GitHub `ci` job from about 4.5 to under 2 minutes; local full `just ci` several times faster on 8 cores; item-agent checks down to seconds for small diffs. Measured before and after in T-CS06.
- Order-dependent or port-sharing tests surface during the rollout and must be fixed first.
- Item agents get a mechanical, repeatable definition of "scoped checks" instead of a judgement call.
- Two new dev dependencies at most (`pytest-testmon`, a random-order plugin). No custom selection logic beyond the fallback path list.
- Risk: testmon misses an affected test. Mitigated by the fallback list and by the full suite at every gate.

## Alternatives considered

- **Changed-file selection in GitHub CI as well.** Rejected: GitHub CI runs only at the release gates, where a full run is required.
- **`pytest-picked` (run test files changed in git).** Rejected as the primary tool: it ignores tests affected by changes in `src/`. Acceptable fallback if testmon is unusable.
- **Splitting CI into several parallel jobs (lint / typecheck / test shards).** Deferred: more setup time per job and more workflow surface; xdist inside one job gets most of the gain. Revisit if the suite grows past about 5 minutes again.
- **mypy on changed files only.** Rejected: unsound for a strict, whole-program type check.
