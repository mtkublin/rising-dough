# ADR-0097: Per-Batch CI in Orchestrator Mode; Fast Pre-commit Pytest

- **Status**: Accepted
- **Date**: 2026-11-06
- **Amends**: ADR-0066 (orchestrator mode)
- **Relates to**: ADR-0027

## Context

In orchestrator mode every change was tested three times: full `just ci` in the item worktree, the pre-commit fast pytest subset, and full `just ci` on the main work branch after every merge. Parallel agents' pytest runs contended for CPU, and commits hung in the pre-commit pytest hook around `tests/integration/web/test_accessibility.py`. The hook's `-m "not integration and not e2e and not visual"` still collected `tests/integration/**`, because many integration tests lack the `integration` marker (1508 tests, about 205 s under contention).

## Decision

1. **Item agents** run only checks scoped to their area (relevant test files or dirs, linters, terraform checks) plus the pre-commit hooks on commit. They do not run full `just ci`.
2. **The orchestrator** runs one full `just ci` on the main work branch per batch of merges, not per merge. Failures go to a fix agent.
3. **Docs-only** items and batches skip full CI; the pre-commit hooks suffice.
4. GitHub `ci.yml` on push remains the safety net.
5. **Single-agent work** outside orchestrator mode keeps the rule: `just ci` green before handoff.
6. On pre-commit pytest stalls caused by parallel agents: wait until no other pytest runs (`pgrep -fl pytest`), then retry. Never `--no-verify`.
7. **Pre-commit pytest hook** is restricted by path to the fast directories: `pytest -q tests/unit tests/architecture -m "not integration and not e2e and not visual" --no-cov`. Rejected alternative: auto-marking everything under `tests/integration/` in a `conftest.py`; it would be implicit, and `addopts` and `just test` do not select by `integration`, so path selection is simpler and cannot silently change what the full suite runs.

## Consequences

- Hook runtime: 1508 tests, 205 s (under contention) before; 974 tests, 31 s after.
- Full suite unchanged: `pyproject.toml` addopts (`--cov-fail-under=90`, `-m "not visual and not smoke"`), `just test`/`just ci` and `ci.yml` still run `tests/integration` and the 90% gate.
- Integration regressions are caught at the batch `just ci` or GitHub CI, not at commit time.
