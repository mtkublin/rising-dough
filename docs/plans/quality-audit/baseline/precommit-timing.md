# T-Q15b: local pre-commit wall time, before and after (ADR-0130 section 8)

Rule: no meaningful local regression (ADR-0108, ADR-0120). Method: one staged change, `uv run pre-commit run -c <config>` (staged files only, no commit), `PYTEST_WORKERS=2`, each case run twice back to back, all hooks warm (environments installed). "Before" uses the `.pre-commit-config.yaml` of `audit/quality` 406b033 (`-c` file); "after" uses the T-Q15b config (adds the `lint-imports` hook, bumps sqlfluff/djlint pins, adds pyyaml stubs to the mypy hook). Both ran against the same working tree (merged T-Q15a + T-Q15b), so the difference is the hook stack only. Load = 1-minute load average printed by `uptime` at the start of each run (8-core Mac shared with other agent sessions; the first measurements were taken at 8 to 12, the src runs at 3 to 9).

## Results (wall seconds)

| Case | Before (4 runs) | After (4 runs) | Load |
|---|---|---|---|
| (a) docs-only (one line in `docs/CHANGELOG.md`) | 7.9, 7.7, 7.9, 7.5 | 7.3, 7.3, 8.1, 7.4 | 7.5 to 12 |
| (b) src-only (one docstring line in `src/budget_planner/domain/money.py`) | 44.9, 7.7, 44.7, 7.8 | 44.3, 8.0, 45.0, 8.1 | 3 to 8.5 |

Runs are listed in execution order (two before/after blocks of two runs each). (b) alternates 45 s then 8 s in both configs: run 1 re-runs the testmon-selected tests that the previous run left unrecorded, run 2 finds them recorded. The pattern is identical before and after, so it is testmon state, not the new hook.

## Cost of the added hook

`lint-imports` (import-linter, 5 contracts, 120 modules): 0.25 s wall measured alone (3 runs). It only runs when `src/**/*.py` or `pyproject.toml` is staged (docs-only commits skip it). No meaningful regression, so it stays a local hook; nothing moved to CI-only.

## Not added locally

The always-on `architecture-guards` hook was not added (G0 experiment pending, ADR-0130 section 2). `just guards` runs `tests/architecture` in about 7 s with 2 workers; the guards run inside the pytest suite (CI, and locally whenever testmon or the unseen-paths fallback selects them).

## Notes

- With the "before" config, the mypy hook fails on the merged tree (no `pyyaml`/`types-pyyaml` stubs in its environment, T-Q15a handoff 2); that is why the "before" src runs report rc=1. Timing is unaffected.
- A dependency or `pyproject.toml` change selects the full suite (about 2 to 10 minutes depending on machine load; observed at load 100 to 200 from other sessions). Expected, unchanged by this task.
- CI side: the new `pre-commit run --all-files` step adds mypy (second run besides `just ci`), sqlfluff, djlint, bandit, detect-secrets, the hygiene hooks and `lint-imports`. Its runner time is not measured yet; `ci.yml` `timeout-minutes` was raised from 15 to 20 as headroom until the first PR run reports it.
