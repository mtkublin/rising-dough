# T-Q03a — Mutmut spike

AUDIT_SHA `9fb18cbca26ef305855efc8fc106d896edc82631`. Tool: `mutmut` 3.7.0 (run ad hoc, nothing committed). Raw survivors: [mutmut-spike-survivors.txt](mutmut-spike-survivors.txt).

## Decision: GO (with a scope change for T-Q03b)

- Domain finished in seconds, so the 15-minute bar is met trivially. But `domain` is tiny for mutation purposes (77 mutants, all in `money.py` and `categories.py`; the rest is frozen dataclasses). It yielded only 3 survivors.
- The real signal is in `services`: a probe run produced 7,043 mutants in about 18 min wall time, with useful survivors (spot-check below). T-Q03b should therefore treat `services` as the main scope.
- Cosmic Ray evaluation not needed.

## Setup needed (becomes a Phase 4 setup item)

1. **libcst pin.** `uv run --with 'mutmut>=3'` alone fails on this dev machine (macOS x86_64): mutmut 3.8.x pulls `libcst` 1.9.0, which has no wheel here and tries to build from Rust. Constraining `--with 'libcst<1.9'` resolves mutmut 3.7.0. Linux CI is likely fine, but pin or constrain in the committed setup.
2. **`[tool.mutmut]` in pyproject** (temporary, reverted):
   ```toml
   [tool.mutmut]
   paths_to_mutate = ["src/budget_planner/domain/"]      # services run: ".../services/"
   tests_dir = ["tests/unit/domain/"]                   # services run: domain + services + repositories
   pytest_add_cli_args = ["--no-cov", "-p", "no:cacheprovider"]
   also_copy = ["tests/", "src/budget_planner/", "migrations/"]
   ```
   3.7.0 prints deprecation warnings: `paths_to_mutate` -> `source_paths`, `tests_dir` -> `pytest_add_cli_args_test_selection`. Use the new names with the version that gets pinned.
3. **`also_copy` is mandatory**, for two reasons found the hard way:
   - mutmut only copies the mutated files into `mutants/src/budget_planner/...`. That partial package shadows the real one, so `budget_planner.config` etc. fail to import (`ModuleNotFoundError`). Fix: also copy `src/budget_planner/`.
   - File entries like `tests/conftest.py` in `also_copy` crash (`FileNotFoundError` because the parent dir is not created); copy the directory `tests/` instead.
   - `tests/db_template.py` reads `migrations/` relative to the repo root, so `migrations/` must be copied too.
4. **Run from the project root**, `PYTEST_WORKERS=2`, `--max-children 4` (other agents were running).
5. **Test selection is path-based, not marker-based.** `tests/unit/deploy/*` read `terraform/...` via relative paths and break in `mutants/` (`FileNotFoundError: mutants/terraform/variables.tf`). Selecting `tests/unit` as a whole fails at collection. Use explicit dirs (`domain`, `services`, `repositories`); do not select `tests/unit/deploy` (or copy `terraform/`).
6. pyproject `addopts` (`--cov...`, `-m "not visual and not smoke"`) is inherited by mutmut's pytest runs; `--no-cov` in `pytest_add_cli_args` is enough, `--cov-fail-under` does not trip.

## Marker check

`unit` is NOT applied automatically. `pytest -m unit --collect-only` collects 53 of 2,670 tests (only explicitly marked ones), while `tests/unit` collects 1,644 and `tests/unit/domain` 53. So `-m unit` is not a usable selector; use directory paths. (The `unit` marker description says "default" but nothing applies it.) Note for plan §11 / Track F.

## Safety check (prod DB)

Result: no path from the `mutants/` copy to `data/budget.sqlite`.
- `grep` for `budget.sqlite`, `BUDGET_DATABASE_URL`, `database_url`, `Settings(`, `get_connection`, `sqlite3`, `data/` over `tests/conftest.py`, `tests/db_template.py`, `tests/fixtures`, `tests/unit/**` and `src/budget_planner/domain`: every hit builds `Settings(_env_file=None, database_url=<tmp_path or migrated_db>)`; `test_config.py` only asserts defaults as strings; `test_prod_db_seed.py` checks text only; `test_production_assertions.py` uses `tmp_path / "budget.sqlite"`.
- The default (`data/budget.sqlite`, relative `Path("data")/...` in `config.py`) is never used by unit tests; the domain tests (the first run) touch no DB, config or Settings at all, and `domain/` imports no db/config.
- `data/budget.sqlite` is gitignored and absent from this worktree (`data/` holds only `demo.sqlite`); `mutants/` contained no `data/` directory.
- The services run uses DB-backed fixtures (`migrated_db` template copies under `tmp_path`); the template is built from `migrations/` into a temp dir. Nothing was run with `BUDGET_DATABASE_URL` set. Residual risk is a service test that builds `Settings()` without a URL from a cwd that has a `data/` dir; none was found by grep.

## Numbers

| Run | Mutated | Tests | Mutants | Killed | Survived | Timeout | Suspicious | No tests | Wall time |
|---|---|---|---|---|---|---|---|---|---|
| A (spike scope) | `domain` | `tests/unit/domain` (53) | 77 | 74 | 3 | 0 | 0 | 0 | 7 s (measured, incl. stats and mutant generation; 28 s with services+repositories tests added) |
| B (probe) | `services` | `tests/unit/{domain,services,repositories}` | 7,043 | 5,099 | 943 | 6 | 0 | 995 | about 1,093 s (18.2 min), measured; `--max-children 4`, shared machine |

- Domain: 74/77 killed = 96.1%. Mutants by file: `money` 69, `categories` 8. Nothing generated for `accounts`, `planned`, `recurring`, `transactions`, `request_ctx` (dataclass `as_dict`/properties/classmethods are not mutated by mutmut 3.7, so those methods are invisible to this score).
- Services: 5,099 / (7,043 - 995 no-tests) = 84.3% of testable mutants killed; 72.4% of all. Survivors by module: forecast 156, recurring_formula 141, recurring 105, budget 85, users 65, analytics 61, planned 35, replication_health 28, reconciliation 27, fx 23, balance 23, upcoming 22.
- "No tests" (995): mostly `auth` (535) and `reauth` (237), which are covered by integration tests only; also budget 95, balance 65, forecast 51. These are not survivors: they need the integration suite or are untested by unit tests.
- Test breakage from the copy: only the path-relative ones listed in setup (deploy tests reading `terraform/`, `db_template` reading `migrations/`, partial-package shadowing). No absolute-path fixture failures.

## Survivor spot-check (12)

| # | Mutant | Class |
|---|---|---|
| 1 | `domain.money.format_money`: `sign = "-" if value <= 0` (zero would render `-0.00 PLN`) | Real gap: no test formats zero |
| 2 | `domain.money.format_money`: `partition("XX.XX")` | Equivalent (no match leaves the whole string in `whole`; re-assembly gives identical output for every input) |
| 3 | `domain.categories.normalise_color`: `ValueError(None)` | Low value (message text) |
| 4 | `services.forecast._anchor_balances`: `as_of_date=None` | Real gap: anchor balance date not asserted |
| 5 | `services.forecast._anchor_balances`: `as_of_date` argument dropped | Real gap (same area as 4) |
| 6 | `services.reconciliation.available_to_target_balance`: `credit_limit_minor <= 1` | Real gap: boundary of 1 minor unit |
| 7 | same function: error message `"XX...XX"` | Low value (message) |
| 8 | `services.recurring._mk_occurrence`: `rule_id=None` | Real gap: occurrence `rule_id` not asserted |
| 9 | `services.recurring.apply_overrides`: log string mutated | Low value (log text) |
| 10 | `services.recurring.advance_next_due`: `hard_end < from_date` instead of `<=` | Likely equivalent (empty range yields no occurrences either way); confirm in T-Q03b |
| 11 | `services.recurring.promote_recurring`: `dest_account_id=None` | Real gap: transfer promotion destination not asserted |
| 12 | `services.recurring.batch_promote_due`: `continue` -> `break` after a skipped rule | Real gap: rules after a skipped one are not covered |

Tally: 7 real gaps (1, 4, 5, 6, 8, 11, 12), 2 equivalent-or-likely (2, 10), 3 low value (3, 7, 9). The survivors are useful: the money-path and recurring items are in the plan §2.1 priority areas. Low-value survivors are string-mutation noise, so a Phase 4 exclusion (`do_not_mutate` for logger/message strings is not automatic in 3.7; consider post-filtering the results) is worthwhile.

## Estimate for T-Q03b

- Scope: `domain` + `services` is about 7,120 mutants; about 20 min wall time per full run with 4 children (unit tests only), and mutmut caches results between runs, so re-runs after test additions are incremental.
- Setup cost: the config above, plus the libcst constraint if run locally on x86_64 macOS. Add `repositories` later (deferred by plan) only after the services baseline; expect the same order of magnitude.
- Triage effort is the dominant cost: 946 survivors. Suggest triage by priority module first (reconciliation, balance, fx, budget, recurring, recurring_formula, forecast = about 560 survivors), sample the long tail, and auto-classify message/log-string mutants as low value with a filter on the diff text. Estimate 3 to 4 h for the baseline and triage, as in the plan (S).
- Also record the 995 "no tests" mutants separately: `auth`/`reauth` need integration tests to be scored (about 3 min suite, so it would not run per-mutant).
- Phase 4 notes: bump to `source_paths` naming; decide whether to pin mutmut (3.7.0) and libcst; keep `tests/unit/deploy` out of mutation runs; add a result post-filter for string mutants.
