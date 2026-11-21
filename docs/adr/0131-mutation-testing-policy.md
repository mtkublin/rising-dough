# ADR-0131: Mutation Testing Policy

- **Status**: Accepted
- **Date**: 2026-11-20
- **Relates to**: [ADR-0130](0130-prevention-regime-and-full-architectural-compliance.md), [ADR-0120](0120-pre-commit-is-the-local-gate.md), [ADR-0108](0108-faster-ci-parallel-tests-and-change-based-inner-loop.md), requirements §8.2
- **Inputs**: `docs/plans/quality-audit/baseline/mutmut.txt`, `mutmut-spike.md`, `mutmut-equivalent.md`, `mutmut-exclusions.md`, `mutmut-real-gaps.md`; `prevention.md` control M

## Context

- Coverage (90% gate) measures executed lines, not whether tests would notice a wrong result. The audit's test findings (Q-015 to Q-020, Q-055) are weak assertions that coverage cannot see.
- Requirements §8.2 says adopting Mutmut needs its own ADR in the prevention pass. This is that ADR.
- A spike and a full baseline ran during the audit (T-Q03b) with mutmut 3.7.0.

## Decision

1. **Tool: Mutmut 3.7.0.** It ran end to end on this codebase in the spike and baseline, supports pytest and a per-function mutant model, and has a results API usable for filtering. Cosmic Ray and pytest-gremlins were not evaluated because the spike met the bar (the cost of a comparison was not justified).
2. **Pins.** `mutmut==3.7.0` as a dev dependency and `[tool.uv] constraint-dependencies = ["libcst<1.9"]`: libcst 1.9 has no macOS x86_64 wheel, and mutmut 3.8 pulls it. Upgrades are a deliberate change, not drift.
3. **Scope: `src/budget_planner/domain/` and `src/budget_planner/services/`.** `repositories` is deferred. Web, db and infrastructure code are out of scope.
4. **Not a merge gate.** Reasons: measured wall time of 34.9 min on a loaded machine and 18.2 min on a quiet one (no GitHub-runner measurement yet), equivalent-mutant noise, and the survivors are mostly missing tests (Q-015 to Q-020) that must be written first. It is tracked as a score.
5. **Weekly scheduled job** (`mutation.yml`: `schedule` and `workflow_dispatch`, `permissions: contents: read`, action SHAs pinned like `ci.yml`, no secrets). It **fails only if a score drops more than 2 points below the recorded baseline** for domain or services. The job is advisory for merges.
6. **Baseline (T-Q03b, mutmut 3.7.0).** Domain 96.1% killed (74 of 77). Services 84.3% of testable (5,098 killed, 944 survived, 6 timeout); 72.4% of all. Per priority module, killed % of testable: reconciliation 69.0, recurring_formula 71.8, `_promotion` 61.1, preferences 71.1, recurring 83.7, forecast 85.6, balance 86.5, fx 86.8, budget 87.7. 995 mutants are "no tests" (auth 535, reauth 237, budget 95, balance 65, forecast 51, rate_limit 12) because 27 functions run only under the integration suite, which is deferred.
7. **Target scores** (proposed in prevention.md, accepted): priority money modules at least 90% of testable, services overall at least 88%, domain at least 95%; adjustable after the first remediation wave. Targets are goals tracked by the weekly job, not gates.
8. **Equivalent and low-value mutants.**
   - 50 equivalent mutants (`baseline/mutmut-equivalent.md`) are marked `# pragma: no mutate -- equivalent: <reason>` on the line.
   - 204 low-value message and log-string mutants (`baseline/mutmut-exclusions.md`) are removed by a post-filter in `just mutate-report` (logger and raise messages, `XX...XX` string mutations). Contract strings (status, kind, action, entity type, error `code=`) stay mutated.
   - A survivor is either a test to write, an equivalent (marked), or low value (filtered); nothing is silently ignored.
9. **Configuration.** `[tool.mutmut]` with `source_paths` as above, `pytest_add_cli_args = ["--no-cov", "-p", "no:cacheprovider"]`, `pytest_add_cli_args_test_selection` set to **explicit test directories** (`tests/unit/domain`, `tests/unit/services`, `tests/unit/repositories`) because `-m unit` selects only 53 tests (the marker is not applied automatically), and `also_copy = ["tests/", "src/budget_planner/", "migrations/"]` (all three are mandatory: partial-package shadowing, `tests/conftest.py` entries crash, `db_template` reads `migrations/`). `tests/unit/deploy` is **never** selected: it reads `terraform/` by relative path and breaks under `mutants/`. Use the 3.7 option names (`source_paths`, not the deprecated `paths_to_mutate` and `tests_dir`).
10. **Recipes.** `just mutate` (`PYTEST_WORKERS=2`, `--max-children 4`, run in the background), `just mutate-report` (survivors by module, post-filtered), `just mutate-clean`. `.gitignore` gains `mutants/` and the mutmut cache.

## Consequences

- A mutation score becomes a visible trend, so a test that cannot fail shows up even at 94% coverage.
- A run is long; it runs weekly and on demand, never in pre-commit or PR CI.
- Mutmut 3.7 does not mutate dataclass methods and properties, and the integration-only functions score as "no tests"; the score understates those areas until integration-backed runs are added.
- Pins must be revisited when libcst ships a macOS x86_64 wheel for 1.9 or the dev platform changes.

## Alternatives considered

- Cosmic Ray, pytest-gremlins: not evaluated (see Decision 1).
- Mutation score as a merge gate: rejected for now (Decision 4); revisit after runner timing and after Q-015 to Q-020 close.
- Nightly job: deferred; weekly first.
