# ADR-0117: Pre-commit Is the Local Gate; the Full Suite Runs Only in PR CI

- **Status**: Accepted
- **Date**: 2026-11-18
- **Amends**: [ADR-0108](0108-faster-ci-parallel-tests-and-change-based-inner-loop.md) §4 (gates table), [ADR-0097](0097-per-batch-ci-policy-and-fast-precommit-pytest.md) §§1, 2, 5, 7 (item-agent checks, batch CI, single-agent handoff, fast-subset hook)
- **Relates to**: [ADR-0066](0066-orchestrator-mode-skill.md), [ADR-0099](0099-release-and-environment-policy.md), [ADR-0027](0027-frontend-toolchain-hardening.md)

## Context

- ADR-0108 kept a full local `just ci` at two points: single-agent handoff and the orchestrator's batch run on the main work branch. ADR-0097 §5 has the same handoff rule.
- Agent tasks are usually atomic, and every PR to `main` runs the full suite with the 90% coverage gate in GitHub `ci.yml` (and release calls the same workflow, ADR-0099). A local full run before handoff repeats that gate.
- The operator's direction (2026-11-18): agents run only the affected checks; drop the local full-run requirement, because everything an agent needs runs in the pre-commit hooks.
- Two gaps made that untrue before this ADR:
  1. The pre-commit pytest hook ran only the fast subset (`tests/unit`, `tests/architecture`; ADR-0097 §7). Integration and web tests (about 750) never ran on commit.
  2. The e2e suite (Playwright + uvicorn) skips in GitHub CI because CI installs no Chromium. With no local full run, it would run nowhere.
- T-CS02…T-CS04 changed the cost picture: DB-backed tests copy a migrated template, tests run under xdist, and `pytest-testmon` selects affected tests (one-module change: 16 tests in 7 s; no affected tests: 3 s). The full suite takes about 80 s locally with 8 workers.

## Decision

1. **The pre-commit pytest hook runs the affected tests across the whole default selection** — unit, integration, web, architecture and e2e — selected by `pytest-testmon`, under xdist (`PYTEST_WORKERS`, default `auto`), without coverage. It replaces the ADR-0097 §7 fast subset. Recipe: `just test-fast` (name kept for the hook entry; it is no longer a subset).
2. **Fallback**: when the staged files include a path testmon cannot see (the `_unseen-paths` list in the `justfile`: every non-Python file outside `docs/` and Markdown, plus any `conftest.py`), the hook runs the full default selection. Templates are also traced by testmon, but stay on the list for safety.
3. **No local full `just ci` is required anywhere.**
   - Single-agent work: hand off when the commit hooks are green. `just ci` stays available and may be run by choice.
   - Orchestrator: no batch `just ci` on the main work branch. Item agents' checks are the commit hooks; `just lint-changed` / `just test-changed` against the main work branch are available for checking before a commit. Terraform checks still run by hand when Terraform changes (no hook covers them).
4. **The full gate is GitHub CI on the PR to `main`** (`ci.yml`: lint, `mypy --strict`, full suite, 90% coverage) plus the `drill-gate` status (ADR-0099). Unchanged.
5. **e2e stays out of GitHub CI** for now (installing Chromium costs about 30–60 s against the 2-minute job target). Affected e2e tests run on commit through testmon, which tracks the uvicorn subprocess.
6. Unchanged: never `--no-verify`; the `frontend-visual-audit` skill for template / CSS / HTMX changes; the prod-DB rules.

## Consequences

- Agents get the affected unit **and** integration / e2e tests at every commit, in seconds for a typical atomic change, instead of a fixed unit-only subset.
- A commit touching a migration, SQL, a dependency, a `conftest.py` or CI config runs the full suite in the hook: about 80 s with 8 workers, longer with `PYTEST_WORKERS=2` under contention. Such commits are rare.
- Integration regressions that testmon misses, and anything that only shows in the full suite with coverage, surface at PR CI instead of before handoff. Accepted: the PR is the merge point to `main`, and CI runs in about 1.5–2.5 minutes.
- A main work branch can carry a cross-item break until its PR runs CI. Mitigation: the orchestrator may still run `just ci` when a batch looks risky; it is no longer mandatory.
- e2e coverage depends on testmon selection plus anyone choosing to run the suite locally. Revisit (Chromium in CI, or a scheduled e2e workflow) if an e2e regression reaches a PR.
- The first commit in a fresh worktree without `.testmondata` runs the whole default selection once; `just worktree-init` avoids that.

## Alternatives considered

- **Keep the full local run at handoff (ADR-0108 §4 as written).** Rejected by the operator: it repeats the PR gate for atomic tasks.
- **Drop local full runs but keep the unit-only hook.** Rejected: integration and e2e tests would run only in PR CI (e2e not at all).
- **Add Chromium and e2e to GitHub CI now.** Deferred: cost against the 2-minute target; revisit with the evidence above.
- **Run the full suite in the hook on every commit.** Rejected: 80 s+ per commit with parallel agents is the ADR-0097 contention problem again.
