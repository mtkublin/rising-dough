# Track F: Tests (T-Q09)

> Read-only audit at `AUDIT_SHA = 9fb18cbca26ef305855efc8fc106d896edc82631`. `src/` and `tests/` are unchanged since that SHA, so every `path:line` is valid there. Repro scripts and recorded output: `docs/plans/quality-audit/repro/F/` (index in section 15). `data/budget.sqlite` was never opened; every run used temp DBs created by the suite.

## Summary

| Severity | Count | IDs |
|---|---|---|
| Critical | 0 | none |
| High | 13 | F-01 to F-10 (Mutmut real gaps), F-12, F-13, F-14 |
| Medium | 10 | F-11, F-15 to F-22, F-27 |
| Low | 4 | F-23 to F-26 |

Totals: 27 findings. F-01 to F-08 and F-11 carry the Mutmut real gaps (T-Q03b) into this track, one finding per module family; F-09 and F-10 are cross-cutting root causes behind about 40 of those rows. The findings that change how the rest of the suite should be read:

- **F-12:** the coverage config excludes every line containing `...`, which silently removes about 790 statements, 16 whole functions and `forecast.monthly_projection` from the report.
- **F-13:** the Plan page (month navigation, Year tab, Forecast tab) is executed by no measured test.
- **F-14:** none of Track A's 16 differential invariants exists as a test.
- **F-15:** four of the five "critical flow" e2e tests contain no UI interaction.

Headline results of this track's own runs:

- **Random-order run:** `pytest -n 2 --random-order --random-order-seed=20261119` (unit, integration, architecture and e2e; visual and smoke are excluded by the default marker): **2645 passed, 17 skipped, 0 failed**, 279 s. No order dependence found. 15 of the 17 skips are permanent "v1 layout superseded" skips (F-25).
- **Prod-DB grep:** no test, fixture, script, justfile target or workflow resolves to `data/budget.sqlite` today. The isolation is by convention, with one environment-dependent hole (F-20).
- **Flake lead:** `tests/e2e/test_ledger_filters.py::test_pagination_keeps_filters` is a test race with a matching product race, a missing `hx-sync` (F-16). `test_landmarks_present[/today]` was not reproduced and is not root-caused (Q-1); it duplicates integration tests, so F-23 removes it.
- **Mutmut "no tests" mutants:** the cause is identified (27 functions only integration tests execute) and the money subset was scored (section 13).

## 1. Coverage statement

**Read in full or in the relevant part:** `tests/conftest.py`, `tests/db_template.py`, `tests/auth_support.py`, all eight `conftest.py` files, `tests/e2e/{test_ledger_filters,test_accessibility,test_add_transaction_flow}.py` and the harness `tests/e2e/conftest.py`, `tests/visual/{conftest,test_snapshots}.py`, `tests/integration/web/{test_app,test_budget,test_security_headers,test_ledger,test_accounts_jpy,test_accessibility}.py` (parts), `tests/integration/test_promotion_flow.py`, `tests/integration/auth/test_auth_service.py` (parts), `tests/integration/web/test_auth_reauth.py` and `test_auth_middleware.py` (parts), `tests/unit/services/{test_reconciliation,test_planned,test_recurring,test_users_admin,test_linked_dedup,test_branch_coverage,test_budget_fx,test_fx,test_rate_limit}.py` (parts). Every `monkeypatch.setattr` / `patch(` / `MagicMock` site in `tests/` (93 lines in 33 files) was listed and the ones that touch money, persistence or authentication were read.

**Applied by script or tool (not by reading):**

- AST scan of all 2175 test functions for assertion shape (`repro/F/weak_assert_scan.py`).
- One full run with per-test coverage contexts, a coverage config without the `...` exclusion, and randomised order (`repro/F/coverage_without_ellipsis_exclusion.txt`, `redundant_candidates.py`, `functions_without_unit_tests.py`).
- Mutmut scoring of the "no tests" money functions (section 13).

**Checklist (plan section 3 Track F):** mutation survivors (sections 2 and 3), gaps and coverage (4, 11), over-mocking (5), weak assertions (6), cross-implementation tests (7), redundant tests (8), fixtures and helpers (9), flakiness (10), prod-DB safety (12), no-tests mutants (13).

**Not done / limits:**

- Mutmut real-gap rows outside the priority modules are rule-defaulted in the baseline (header of `baseline/mutmut.txt`), so F-11 is Medium/Low and not individually proven. I did not write killing tests (read-only audit); I re-read the source for the rows named in this file.
- The visual suite (`tests/visual`) and the smoke suite were not run (opt-in, not part of `just ci`). Their staleness is argued from git dates (F-22).
- E2E tests are not coverage-measured (they run a `uvicorn` subprocess without coverage); I did not instrument it.
- Time-dependent tests (F-21) were classified by reading, not by running with a shifted clock.
- `test_landmarks_present[/today]` did not fail in my loaded full run; no reproduction (Q-1).
- F-16's race was derived from the template and the test constants, not reproduced under an injected delay.

## 2. Mutmut real gaps carried in (priority money modules, High)

Source: `baseline/mutmut-real-gaps.md` (516 rows, 693 mutants; 304 rows in priority modules). Row ids below are the `#` column of that file. Root cause for all: `weak-assertion`. Mitigation for all: write the killing test named in the row (TDD, fails on the mutant), grouped as stated below. One finding per module family.

### F-01 `format_money` renders zero as `-0.00 PLN` without any test failing
- **Severity / confidence:** High / Confirmed (surviving mutant, row 175; the docstring promises the opposite). **Track / root cause:** F / weak-assertion.
- **Location(s):** `domain/money.py:252` (`sign = "-" if value < 0 else ""`, mutant `<= 0`); docstring `domain/money.py:246-249` ("Zero renders without a sign"). Tests: `tests/unit/domain/test_money.py` has no zero case for `format_money`.
- **Description:** Every money value on every page goes through this function. A boundary change flips zero to a signed zero and nothing fails. A related risk is a negative amount that rounds to zero in a currency with fewer decimals.
- **Evidence:** `baseline/mutmut-real-gaps.md` row 175 (`format_money #10`, "No test sits exactly on this boundary value").
- **Impact:** A `-0.00` shown for an empty budget line or a balanced account.
- **Mitigation:** Add `test_format_money_zero` parametrised over PLN, JPY and a zero-amount in each, asserting `"0.00 PLN"`, `"0 JPY"`, and `format_money(-1, "JPY")` as the sign decision.
- **Effort:** S. **Related:** ADR-0008, Track A A-01/A-09 (format and exponent), F-02.

### F-02 `recurring_formula` (71 rows): rounding mode, source-rule lookup and validation unasserted
- **Severity / confidence:** High / Confirmed. **Root cause:** weak-assertion.
- **Location(s):** `services/recurring_formula.py`; rows 234-304 by function: `validate_formula_sources` 279-295 (17), `_source_rule_month_value` 240-254 (15), `_sum_category_in_month` 255-263, `_with_formula_amount` 270-278, `preview` 296-304, `parse_percent_to_bps` 234-236, `_evaluate` 264-265, `compute_formula_amount` 266-267, `resolve_rule_amount` 268-269, `build_formula` 237, `_month_bounds` 238, **`_apply_coefficient` 239** (`services/recurring_formula.py:135`, `rounding=ROUND_HALF_UP` replaced by `None`).
- **Description:** The ROUND_HALF_UP in `_apply_coefficient` is the only HALF_UP in service arithmetic (everything else is HALF_EVEN; Track A concept 8). With `rounding=None` the context default (HALF_EVEN) applies, and no test uses a value that is an exact tie after the coefficient, so the deliberate rounding choice is unpinned. 37 of the 71 rows are "argument dropped or None" (for example `user_id`, `conn`, `active_only` arguments passed through to the repository), 3 are "fixtures have a single contributing item" (a sum of one item cannot tell `sum` from `max`), 2 are "no inactive rule in the fixture".
- **Evidence:** rows listed above.
- **Impact:** A formula-based recurring amount (percent of another rule or category) can be off by one minor unit on ties, or silently include another user's / an inactive source rule, and stay green.
- **Mitigation:** In `tests/unit/services/test_recurring_formula.py`: (1) a tie case, for example 12.5 percent of 100 minor units and 0.5 coefficient on odd amounts, asserting HALF_UP (`2.5 -> 3`, where HALF_EVEN would give 2); (2) a two-user fixture where the second user owns a rule/category with the same names and assert it is not summed; (3) a source category with two items and one inactive source rule; (4) assert the audit-free `preview` output fields.
- **Effort:** M. **Related:** Track A A-17 (override sources), F-09, F-10.

### F-03 `forecast` (102 rows): the largest survivor cluster; boundaries, skipped items and FX arguments unasserted
- **Severity / confidence:** High / Confirmed. **Root cause:** weak-assertion.
- **Location(s):** `services/forecast.py`, rows 64-165: `_committed_future_for_category` 92-107 (16), `forecast_monthly` 153-165 (13), `_planned_budget_per_month` 132-143 (12), `forecast` 119-129 (11), `_month_flow_sums` 144-152 (9), `_collect_events` 71-78 (8; row 78 passes `None` for `user_id`), `_collect_budget_overlay` 110-116 (7), `_spent_so_far` 86-91 (6), `_signed_events_for_direction` 64-67, `_iter_months` 82-85, `_rule_outside_window` 79-81, and smaller ones. Causes: 40 "argument dropped or None", 17 "no assertion covers this expression", 12 "no test sits on this boundary" (rows 73, 79, 82, 83, 86, 92, 103, 110, 111, 115, 142, 145), 7 "continue vs break" (70, 77, 102, 109, 112, 137, 149), 6 "sign not asserted".
- **Description:** The forecast tests assert totals for one or two hand-built scenarios. Window edges (`<` vs `<=` on the horizon end, month first/last day), a skipped item before a valid one, and the sign of each leg are never on a boundary. This is the same code where Track A found the double-counting and the FX-ignoring spent figure (A-03, A-04), so the cluster hides exactly the class of bug already present.
- **Evidence:** rows listed above.
- **Impact:** Any change to window handling or FX plumbing in the forecast passes the unit suite.
- **Mitigation:** Add to `tests/unit/services/test_forecast.py`: a horizon-end-day case (item exactly on the last day and one day later), an item skipped by an override followed by a valid item in the same rule, income vs expense vs transit signed legs on one day with the exact day balance, and a two-currency case that asserts the converted amount and the rate date. Use `tests/unit/services/test_linked_dedup.py` as the template for cross-function checks.
- **Effort:** L. **Related:** Track A A-03/A-04/A-12, F-06, F-09, F-10, F-12 (the forecast tests never reach `monthly_projection`).

### F-04 `budget` (53 rows): fiscal-month anchoring, committed window, mean and FX converters unasserted
- **Severity / confidence:** High / Confirmed. **Root cause:** weak-assertion.
- **Location(s):** `services/budget.py`, rows 11-63: `month_summary` 44-63 (20; includes `year_start = date(year, 1, 2)` row 44, `_resolve_period_start(..., None, ...)` rows 43 and 51), `_committed_by_category` 23-30 (8; `end + 1 day` sign row 25, `rule_start > inclusive_end` boundary row 29, `continue` vs `break` row 28), `_resolve_period_start` 39-42, `base_amount_converter` 11-13 and `base_txn_converter` 14-16 (default-currency `.get(account_id, base)` row 12/13/15/16), `fiscal_month_for` 36-38, `_mean_minor` 20-21 (`count <= 0` and `return 0`), `committed_in_window` 31-32, `committed_split_in_window` 33-34, `_month_range` 17 (first day `1` -> `2`).
- **Description:** The budget unit tests use one clean month. The default-currency fallback in both converters (`.get(account_id, base)`) can be dropped or set to `None` unnoticed, which is the missing-account path of A-06. `_mean_minor` returning 1 instead of 0 on an empty set is a visible wrong number.
- **Impact:** Left-per-day and the month summary can shift by a day or a unit without a test noticing; this area already has A-05 (last-day off-by-one).
- **Mitigation:** In `tests/unit/services/test_budget.py` and `test_budget_fx.py`: assert `_month_range` and the fiscal start for the first of the month and for the anchor day; a committed item on the last day and on the day after; an empty set for `_mean_minor` (0) and a one-item set; an account missing from the converter map (assert the policy value, ties to A-06); a transaction exactly on `date_from`.
- **Effort:** M. **Related:** Track A A-05/A-06, F-09, F-10.

### F-05 `recurring` (50 rows): `promote_recurring` audit attribution, override ordering, boundary days
- **Severity / confidence:** High / Confirmed. **Root cause:** weak-assertion.
- **Location(s):** `services/recurring.py`, rows 184-233: `promote_recurring` 211-220 (10; row 220 `user_id=None` in the `write_audit` call at `services/recurring.py:488-496`), `_mk_occurrence` 184-189, `skip_and_advance` 221-226, `generate_occurrences` 190-194 (row 190 line 124 and row 194 line 134 are boundary values), `_apply_single_override` 195-198, `apply_overrides` 199-202, `batch_promote_due` 227-230 (row 228/229 line 611-612 boundary and `continue` vs `break`), `advance_next_due` 205-207, `occurrence_in_month` 208-210, `linked_occurrence_keys` 232-233.
- **Description:** The audit entry written when a recurring rule is promoted can lose its `user_id` with no test noticing, which breaks the attribution rule of ADR-0019 for the most frequent recurring action. Several boundary rows (end of month, end of range) are on a value no test uses.
- **Impact:** Audit entries without a user; an off-by-one in `batch_promote_due` skipping or double-promoting a rule on the boundary day.
- **Mitigation:** In `tests/unit/services/test_recurring.py`: after `promote_recurring`, read the `audit_log` row and assert `user_id`, `entity_type`, `operation` and the prev/new JSON (the integration helper `audit_rows` already exists in `tests/integration/auth/conftest.py:41`); parametrise `batch_promote_due` over a due rule exactly on the cut-off day, one day before and one day after; a skipped rule followed by a valid one (continue vs break).
- **Effort:** M. **Related:** ADR-0019, Track B (audit bypass checks), F-09.

### F-06 `fx` (9 rows): default arguments and the cached lookup are unasserted
- **Severity / confidence:** High / Confirmed. **Root cause:** weak-assertion.
- **Location(s):** `services/fx.py`, rows 166-174: `_fetch_remote` timeout dropped (`:58`, rows 166-167), `_fallback` arguments `from_ccy`, `to_ccy`, `on_date`, `latest.date` set to `None` (`:75-78`, rows 168-171), `get_rate` passes `None` as the date to `_fallback` (`:110`, row 172), `convert` passes `None` as the http client (`:134`, row 173), `convert_cached` returns `None` instead of the repository hit (`:160`, row 174).
- **Description:** These are the arguments of the stale-rate fallback and the cache lookup. Row 174 means `convert_cached` could always miss and no test would fail, because the tests that cover it assert the converted amount only for cases where the native amount is the fallback (see `unit/services/test_budget_fx.py::test_missing_rate_degrades_to_native_amount`, which pins the divergent policy of A-06 instead of detecting it).
- **Impact:** FX amounts silently degrade to native amounts (A-06, G-01) and the test suite cannot tell a working lookup from a broken one.
- **Mitigation:** In `tests/unit/services/test_fx.py`: assert the exact `(rate, date)` returned by the stale fallback; assert that `convert_cached` returns the converted amount for a cached row and that a miss is reported distinctly (not equal to a hit); assert `_fetch_remote` is called with a client that has a base URL (this also covers G-01).
- **Effort:** S. **Related:** Track A A-06, Track G G-01, F-17 (unit tests build the client with `base_url=`).

### F-07 `reconciliation` (8 rows): the caller-supplied `category_id` path has no passing test
- **Severity / confidence:** High / Confirmed. **Root cause:** weak-assertion.
- **Location(s):** `services/reconciliation.py:53` (row 176, `credit_limit_minor <= 0` to `<= 1`), `:100-103` (rows 177-180: `chosen = None`, wrong arguments to `find_by_id`, inverted `if chosen is None`, `category = None`), `:112` (row 181, sign coercion), `:125` and `:128` (rows 182-183). Coverage agrees: `reconciliation.py:100-103` are the four uncovered lines in `baseline/coverage.txt`.
- **Description:** The F-03 feature (reconcile into an expense or income category, ADR-0008 sign coercion) is executed by no test. The code that makes `derive_balance == actual_balance` hold for a chosen category is therefore unprotected, and reconciliation is a priority area.
- **Impact:** Reconciling into a category can store the wrong sign; `derive_balance` then disagrees with the balance the user entered.
- **Mitigation:** Add to `tests/unit/services/test_reconciliation.py` one test per direction (`Direction.EXPENSE` with positive and negative delta, `Direction.INCOME`) that calls `reconcile(..., category_id=...)` and asserts both the stored amount sign and `derive_balance(...) == actual`, plus the unknown category (`MissingSystemCategoryError`). Add the `credit_limit_minor == 1` boundary for `available_to_target_balance`.
- **Effort:** S. **Related:** ADR-0008, `tests/e2e/test_reconcile_flow.py` (default category only).

### F-08 `balance` (10 rows): the include-deleted choice and the account filter are unasserted
- **Severity / confidence:** High / Confirmed. **Root cause:** weak-assertion.
- **Location(s):** `services/balance.py:69` (row 1, `_directions_by_id` include-deleted), `:81` (rows 2-3, `TransactionFilter(account_or_dest=None)`), `:98`, `:102`, `:129`, `:133` (rows 4-7, soft-deleted account and `account_id` set to `None`), `:147` (row 8, `>` to `>=`), `:156` and `:158` (rows 9-10, `AccountStats.account_id` / `base_balance` set to `None`).
- **Description:** The mutants that drop the account filter or the live/deleted choice survive because the balance tests use one account and no soft-deleted account or category. Row 8 is an equivalent mutant (same date either way) and should move to `mutmut-equivalent.md`: its test `tests/unit/services/test_branch_coverage.py:49` was written to close a coverage branch (its docstring says so) and asserts `last_txn_date` and `txn_count`, which cannot distinguish the two operators.
- **Impact:** A transaction on another account counted into a balance, or a transaction of an archived category dropped from it, passes.
- **Mitigation:** In `tests/unit/services/test_balance.py`: two accounts, a transaction on each, assert each balance and `AccountStats.account_id`/`base_balance`; a soft-deleted category and a soft-deleted account referenced by an existing transaction (assert whichever behaviour ADR-0019 prescribes, and that it equals `account_planned` and forecast, see F-10).
- **Effort:** S. **Related:** Track A A-10/A-11, F-10.

### F-09 Cross-cutting: `user_id` and `conn` passed as `None` are accepted silently in 14 money-path rows
- **Severity / confidence:** High / Confirmed (rows). **Track / root cause:** F / weak-assertion (a `scoping-gap` detector is missing).
- **Location(s):** rows 5, 7, 22, 30, 43, 51, 60, 78, 101, 104, 105, 126, 138, 220 (for example `services/forecast.py:277`, `services/budget.py:308`, `:451`, `:501`, `:548`, `services/recurring.py:496`, `services/balance.py:102`, `:133`).
- **Description:** In each row a call that passes `user_id` (or `conn`) to a repository or to another service is mutated to pass `None`, and the suite stays green. The user-scoping test in `tests/architecture/test_user_id_filter.py` checks that SQL carries a `user_id` predicate; it does not check that every caller passes the right id. Service tests run with a single user (`USER_ID = 1`), so a `WHERE user_id = NULL` that returns nothing is indistinguishable from "no data". The only multi-user tests are `tests/unit/repositories/test_user_isolation.py` (repository level) and the D-01 repro.
- **Impact:** A refactor that drops the user id on a service-to-service call returns empty or cross-user data and every service unit test still passes. This is the same class as Track D D-01.
- **Mitigation:** Add a two-user fixture to `tests/unit/services/conftest.py` (user 2 owns data with the same names and overlapping ids and dates) and run each money service (`balance`, `budget`, `forecast`, `analytics`, `recurring`, `planned`, `upcoming`, `today`) against user 1 asserting that user 2's rows never appear; one parametrised test per service function is enough.
- **Effort:** M. **Related:** ADR-0061, Track D D-01, F-10.

### F-10 Cross-cutting: fixtures never contain a deleted or inactive row, so `include_deleted` / `active_only` are never asserted (26 rows)
- **Severity / confidence:** High (priority modules) / Confirmed. **Root cause:** weak-assertion.
- **Location(s):** `include_deleted` rows: 1, 4, 6 (`balance`), 11, 14, 24 (`budget`), 125, 132, 163 (`forecast`), 213, 219, 224 (`recurring`), 328, 335, 342, 347 (`analytics`, Medium), 428 (`planned`, Medium). `active_only` rows: 27 (`budget:300`), 76, 101, 150 (`forecast`), 227 (`recurring`), 255, 284 (`recurring_formula`), 311 (`account_planned`), 371 (`categories`).
- **Description:** The repository layer has the tests (`tests/unit/repositories/test_branch_coverage.py` covers `include_deleted` and `active_only` for categories, budgets, recurring), but the mutants sit at the service call sites that choose the flag. The choice differs between modules (A-11: forecast counts archived categories in one place and not in another), and nothing pins it.
- **Impact:** Archived categories or inactive rules counted (or not) inconsistently between budget, forecast and analytics.
- **Mitigation:** Add one shared fixture `world_with_tombstones` (a soft-deleted category with a transaction, an archived account, an inactive recurring rule) in `tests/unit/services/conftest.py` and assert, for each flagged call site, the expected inclusion. Decide the intended policy once (see Track A A-11) and encode it as the expected value.
- **Effort:** M. **Related:** Track A A-11, F-08, F-09.

### F-11 Non-priority modules: 213 rows rule-defaulted (Medium/Low)
- **Severity / confidence:** Medium (money-adjacent) and Low / Probable (rule-defaulted, not individually proven). **Root cause:** weak-assertion.
- **Location(s):** by module, rows in `baseline/mutmut-real-gaps.md`: `analytics` 322-358 (37, Medium), `users` 488-516 (29), `planned` 403-429 (27), `upcoming` 471-487 (17), `replication_health` 440-454 (15, Low), `today` 458-470 (13, includes `_div_round_half_even` zero denominator row 458 and `_pace_tag_for` rows 462, 466), `preferences` 430-438 (9, Low), `export` 375-382 (8, Low), `account_planned` 310-316, `income` 388-394, `password_change` 398-402, `fortune` 383-387, `_passwords` 305-308, `accounts` 317-321, `audit` 359-362, `audit_tail` 363-369, `categories` 370-374, `ledger_totals` 395-397, `retention` 455-457, `rate_limit` 439, `_promotion` 309.
- **Description:** Same shapes as F-02 to F-10. The two with direct user impact: `analytics` (37 rows, including `_trailing_12_months`, `_twelve_month_averages`, `_period_bounds`, and the rows 328-347 include-deleted choices), and `today._pace_tag_for` / `_div_round_half_even` (the on-track / tight / over-limit tag and the per-day number on the Today page).
- **Impact:** Wrong labels or averages that no test pins.
- **Mitigation:** Fix after F-02 to F-10, module by module, using the "suggested killing test" column; start with `analytics` and `today`. Re-triage the sampled rows first (the baseline sampled about a third).
- **Effort:** L. **Related:** Track A A-02 (analytics ignores FX), A-16.

## 3. Mutmut triage notes

- Row 8 (`balance:147`, `>` to `>=`) is equivalent (F-08). The baseline's equivalent list should gain it.
- Of the 693 real-gap mutants, 418 sit in priority modules. The dominant cause is "argument dropped or None" (about 55 percent of priority rows), meaning the tests assert results that tolerate the wrong argument, not that they miss branches. That is a strong signal that the service tests are example-based single-scenario tests; adding a second user, a second currency and a tombstone row (F-09, F-10, F-03) removes most of them at once.

## 4. Coverage measurement and gaps

Baseline: `baseline/coverage.txt` (total 94.70 percent, 7741 statements). The plan asks for modules under 85 percent: `web/routers/dev_components.py` 64.29 (dev route, 404 in production), `web/routers/plan.py` 54.24, `web/routers/settings.py` 76.79, `services/reauth.py` 70.89, `web/today_data.py` 73.75, `web/routers/today.py` 80.95, `web/routers/ledger.py` 82.76, `web/routers/recurring.py` 83.51, `web/routers/planned.py` 84.28. `web/app.py` is 85.37. The baseline was produced with the repository's own coverage config, which hides code (F-12).

### F-12 The coverage config excludes every line containing `...`, which drops about 790 statements and 16 whole functions from the report
- **Severity / confidence:** High / Confirmed. **Track / root cause:** F / weak-assertion (a measurement defect that makes the gate unreliable).
- **Location(s):** `pyproject.toml:194` (`"\\.\\.\\."` in `[tool.coverage.report] exclude_lines`, intended for `...` stub bodies); affected definitions, for example `services/balance.py:42` (`signed_legs`), `services/budget.py:603` (`yearly_grid`), `services/password_change.py:89` (`validate_new_password`), `services/rate_limit.py:149,155,164,169,178,187,196` (all rule factories), `services/accounts.py:104` (`last_checked`), `web/routers/budget.py:88` (`_rules_rows`), `web/routers/ledger.py:222`, `web/charts.py:80`, `web/ledger_types.py:18`, `repositories/webauthn.py:65` (16 functions whose first line contains `tuple[X, ...]`), plus other lines whose parameters contain `Form(...)` / `Query(...)`.
- **Description:** coverage.py matches `exclude_lines` against each source line, and when the matching line starts a function or compound statement, the whole body is excluded. Any `def f(...) -> tuple[X, ...]:` therefore disappears from the report, together with its body. I computed the difference with and without the pattern over all of `src/budget_planner`: **790 additional statements** are counted (7741 to 8531) and the report gains **49 more missed statements** (337 to 386); the total moves from 94.70 to 94.49 percent. The percentage barely changes because the hidden code is mostly executed, but the per-line "Missing" list the plan and the baseline rely on is blind to it. The biggest hidden areas: `web/routers/planned.py` 90 statements, `web/routers/budget.py` 82, `web/routers/accounts.py` 81, `web/routers/transactions.py` 69, `services/forecast.py` 67, `services/recurring.py` 56, `services/analytics.py` 45, `web/routers/categories.py` 45.
- **Evidence:** `repro/F/coverage_without_ellipsis_exclusion.txt` (full report with the pattern removed; same run as the random-order run), method in section 15. Per-file extra missed statements: forecast +8, accounts router +7, `today_data` +7, budget router +6, planned router +5, ledger router +4, transactions router +4, `services/budget` +3.
- **Impact:** A regression in a hidden function (for example a rate-limit rule or `validate_new_password`) cannot lower the coverage gate. New code written with a `tuple[X, ...]` return type is invisible to the 90 percent gate.
- **Mitigation:** Delete the `"\\.\\.\\."` line from `exclude_lines` in `pyproject.toml` and, if stub bodies need excluding, use the anchored pattern `"^\\s*\\.\\.\\.$"`. Re-run the gate and add tests for the 49 newly missed statements (they are listed by the diff in the repro file). Effort S for the config line, M for the new tests.
- **Effort:** S (config) + M (tests). **Related:** ADR-0108, F-13.

### F-13 The Plan page (non-current months, Year tab, Forecast tab) and `forecast.monthly_projection` are executed by no coverage-measured test
- **Severity / confidence:** High / Confirmed (coverage and caller search). **Root cause:** weak-assertion (missing tests on a money page).
- **Location(s):** `web/routers/plan.py:87-94`, `:126-133`, `:145-171` (non-current month: anchor day capped at 28, committed zeroed; Track A concept 5), `:180-193` (Year tab), `:195-222` (Forecast tab, the only caller of `services/forecast.py:932` `monthly_projection`); `services/forecast.py:932-975`. Tests: `tests/integration/web/test_forecast.py:92`, `tests/integration/web/test_plan_analytics.py:33` only fetch the default and `?tab=analytics` views. `tests/e2e/test_override_tier_toggle.py:58,68` visits `/plan?tab=year`, and `tests/e2e/test_set_budget_flow.py:62` visits `/budget?year=2026&month=10`, but e2e is not coverage-measured (section 11).
- **Description:** `monthly_projection` (a 12-month end-balance series, with a hard-coded `value_major=... / 100.0`, A-01 class, and a fresh `httpx.Client(timeout=5.0)` created inside the function, G-01 class) is hidden by F-12 *and* has no test at all: `functions_without_unit_tests.py` finds it has zero executing contexts of any kind. `routers/plan.py` is 54 percent covered, `complexity E (31)` per `baseline/radon-cc.txt`, and re-implements the period logic Track A flagged (A-05). The mutmut "no tests" count for `forecast` (51 mutants) is exactly this function.
- **Impact:** The Plan Forecast tab, month navigation and the Year tab can render wrong numbers or a 500 and no Python-level test notices; they are the pages where A-05 and A-13 live.
- **Mitigation:** Add integration tests in `tests/integration/web/test_plan.py` (new): GET `/plan?tab=forecast` on a seeded world and assert the series length, the first and last month label, and one end-balance value; GET `/plan?month=...` for a past and a future month and assert the committed figure is zero and the period bar dates; GET `/plan?tab=year&year=...`. Add a unit test for `monthly_projection` with a `MockTransport` client injected (this requires the injectable client the G-01 mitigation introduces).
- **Effort:** M. **Related:** Track A A-05, A-01, Track B (`plan` complexity), Track G G-01, F-12.

## 5. Over-mocking and vacuous tests

All 93 `monkeypatch.setattr` / `patch(` / `MagicMock` lines were listed. 55 are in `tests/unit/deploy/` (shell-script and CI tooling; the fakes replace network or subprocess, which is appropriate). 9 pin the bcrypt cost (F-24). The remainder were read:

- **Fault injection in persistence tests (appropriate when the failure follows a write):** `tests/unit/services/test_planned.py:323` and `tests/integration/test_promotion_flow.py:107` patch `planned_repo.stamp_promotion` to raise after `transactions_repo.create`, so a rollback is observable. `tests/unit/services/test_recurring.py:790` patches `recurring_repo.set_next_due` the same way. These are sound.
- **Spies that wrap the real function (appropriate):** `tests/integration/auth/test_auth_service.py:93` (spy that still calls the real `verify_password` to prove the dummy verify runs for unknown emails), `tests/integration/web/test_ledger.py:446` (makes any network call fail to prove `/ledger` never fetches FX; sound).
- **Stubbing the verifier (limits what is proven):** `tests/integration/auth/test_auth_service.py:259,282,380,403,427,454` replace `verify_registration_response` / `verify_authentication_response`; `tests/integration/web/test_auth_passkey.py:87,105,118,132,146,216,236,251` replace `authenticate_passkey_finish` / `register_passkey_finish` wholesale; `tests/integration/web/test_auth_reauth.py:348,384` replace the passkey parse and verify. The cryptographic verification itself is exercised only by the Chromium virtual authenticator in `tests/e2e/test_passkey_journey.py` (13 UI interactions) and by one real-verifier negative test (`test_auth_service.py::test_register_finish_invalid_response_and_unknown_user`). This is a deliberate trade-off, not a defect, but it makes the e2e passkey test the only protection of the happy path (section 11).
- **Reaching for `MagicMock(spec=Request)`** at `tests/integration/web/test_app.py:102` to test a one-line helper: harmless.

### F-19 `test_rollback_on_failure` in reconciliation is vacuous: it fails the only write, so no rollback is tested
- **Severity / confidence:** Medium / Confirmed (read of the unit under test). **Root cause:** weak-assertion.
- **Location(s):** `tests/unit/services/test_reconciliation.py:137-150` patches `reconciliation.transactions_repo.create` to raise; `services/reconciliation.py:118-130` performs exactly one write (`transactions_repo.create`) and no other statement writes before it. After the failure there is nothing to roll back, so `before == after` holds with or without a transaction.
- **Description:** The name promises atomicity; the test would pass if `reconcile` had no transaction handling at all. The twin tests for promotion (`test_planned.py:319`, `test_recurring.py:781`) are valid because the failing call comes after an earlier write.
- **Impact:** False assurance about atomicity of the reconcile path (which also writes an audit row inside `create`).
- **Mitigation:** Patch `audit_svc.write_audit` (or the repository's audit call) to raise instead, so the transaction row has been inserted when the failure occurs, then assert zero transactions and zero audit rows. If the audit write happens inside `create`, patch the audit helper that `create` calls.
- **Effort:** S. **Related:** ADR-0019, F-05.

## 6. Weak assertions beyond Mutmut

`repro/F/weak_assert_scan.py` (AST scan of 2175 test functions; output `weak_assert_scan.out`):

| Shape | Count |
|---|---|
| Tests whose only assertions are `status_code == N` | 141 (all in `tests/integration/web` or `tests/integration/startup`) |
| Status code and `is not None` only | 13 |
| `is not None` only | 0 |
| Truthy-only (`assert x`) | 4 |
| No assertion and no `raises` | 7 |

Money-valued `assert x is not None` outside those sets is common (240 `is not None` lines overall) but nearly all precede a field assertion; I did not find a bare `assert balance`/`assert amount` on a money value.

### F-18 141 HTTP tests assert only the status code; success paths do not check persistence
- **Severity / confidence:** Medium / Confirmed. **Root cause:** weak-assertion.
- **Location(s):** per file: `tests/integration/web/test_recurring.py` 24, `test_budget.py` 17, `test_categories.py` 14, `test_planned.py` 11, `test_accounts.py` 11, `test_settings_users.py` 10, `test_transactions.py` 6, `test_auth_rate_limit.py` 6. Success-path examples: `tests/integration/web/test_budget.py:83-85` (`test_set_recurring`) and `:103-105` (`test_set_one_off`) post an amount and assert only `200`; `test_budget.py:60-63` (`test_set_default`) at least checks the `HX-Trigger` header. Rejection-path examples: `test_budget.py:73-80` (`422` without proving nothing was written).
- **Description:** A handler that returns `200` and writes nothing (or writes the wrong tier) passes. The set-budget e2e flow (`tests/e2e/test_set_budget_flow.py`) covers only the default tier, so the recurring and one-off setters have no assertion on the stored value anywhere.
- **Impact:** Budget write regressions are not detected at the HTTP layer.
- **Mitigation:** For each success-path test add one read-back assertion through the repository (`budgets_repo.get_*` for the tier) or the rendered value; for each rejection test assert the repository row count is unchanged. Start with `test_budget.py`, `test_recurring.py`, `test_accounts.py`.
- **Effort:** M. **Related:** F-04.

### F-26 Tests with no meaningful assertion
- **Severity / confidence:** Low / Confirmed. **Location(s):** no assertion in the test body: `tests/integration/web/test_fab.py:23`, `tests/unit/deploy/test_host_release.py:430`, `tests/unit/repositories/test_transactions.py:80` (`test_soft_delete_missing_is_noop`), `tests/unit/web/test_production_assertions.py:47`. The scan also flags `tests/integration/web/test_auth_middleware.py:150,157,169` (they assert through `_assert_rejected_and_cleared`) and the truthy-only `tests/unit/services/test_rate_limit.py:56,63` (assert `.allowed`) and `test_replication_health.py:69,90`; I read these and they are fine (scan false positives).
- **Description / mitigation:** Add an explicit assertion to the four (for example the row count in `test_soft_delete_missing_is_noop`, the absence of the element in `test_fab`). Effort S.

## 7. Missing cross-implementation (differential) tests

Track A executed 16 invariants as scripts under `repro/A/`; none was turned into a test. I searched `tests/` for each. The only cross-implementation test is `tests/unit/services/test_linked_dedup.py:84` (`test_linked_row_in_window_counted_once_everywhere`), which compares `budget.committed_in_window`, `forecast._collect_events` (a private function) and `account_planned.planned_net_by_account`; it does not reach `forecast._collect_budget_overlay`, which is where A-04 double-counts.

| Track A invariant | Result in Track A | Test in `tests/` |
|---|---|---|
| INV-1 budget spent == ledger == analytics (with a foreign-currency expense) | FAIL (A-02) | none (analytics tests are PLN-only: `tests/unit/services/test_analytics_bundle.py`) |
| INV-2 balance == SQL oracle; fortune == today_data == forecast day 0 | FAIL (A-07) | none (`tests/unit/services/test_fortune.py` alone) |
| INV-3a/b/c budget vs forecast spent / committed / overdue | FAIL (A-03, A-04, A-12) | partial (`test_linked_dedup`, events only) |
| INV-4 source-leg sign parity across balance / forecast / account_planned | PASS | none |
| INV-5 amount parsers agree | FAIL (A-08) | none (`tests/unit/domain/test_money.py`, `tests/integration/web/test_forms.py` test parsers separately) |
| INV-6 exponent table / Today renders JPY | FAIL (A-01, A-09) | partial (`tests/integration/web/test_accounts_jpy.py` covers `/accounts` only; no `/today`) |
| INV-7 period window and left-per-day divisor | FAIL (A-05) | none |
| INV-8a `resolve_budget` == `yearly_grid` | PASS | none (`yearly_grid` runs only in integration tests) |
| INV-8b display-tz today == host today | FAIL by construction (A-13) | none |
| INV-9 archived category scope | FAIL (A-11) | none |
| INV-10 missing FX degrades identically | FAIL (A-06) | pins the budget policy only (`tests/unit/services/test_budget_fx.py:133`, `:183`) |

### F-14 None of Track A's differential invariants exists as a test; 8 of the 10 failing ones will regress or stay open unguarded
- **Severity / confidence:** High / Confirmed. **Root cause:** missing-invariant-test.
- **Location(s):** table above.
- **Description:** The audit found that the app's wrong-number defects all sit between modules, and the unit tests are per module with single-currency PLN data (the demo DB is all-PLN; Track A needed an added EUR account to see 7 of the 10 failures). `tests/unit/services/test_budget_fx.py:133` and `:183` even assert the budget-side degrade-to-native-amount policy as correct, cementing the divergence of A-06.
- **Impact:** Fixing A-01 to A-13 without these tests leaves no guard against the next divergence; the remediation tasks would each be verified by hand.
- **Mitigation:** Add `tests/integration/invariants/` with one file per Track A script (`inv_01` to `inv_10`), reusing the multi-currency seed from `repro/A/harness.py` as a conftest fixture (PLN + EUR + JPY accounts, one cached rate, one archived category, one linked planned row). Land each test with `xfail(strict=True)` pointing at the Track A finding id and flip it when the finding is fixed. Effort L.
- **Effort:** L. **Related:** Track A section 4, Phase 4 `duplicate-logic` control.

## 8. Redundant-test candidates (ADR-0108 section 2)

Method: per-test coverage contexts (`--cov-context=test`) over the whole suite, then for each test the number of lines no other test covers (`repro/F/redundant_candidates.py`, output `redundant_candidates.out`). Of 1885 tests with Python coverage, **1560 (83 percent) have zero unique lines**. The metric does not discriminate: well-factored tests share production lines, and (a) e2e and HTML tests are scored on Python lines only, but their value is in templates, JS and CSP, which coverage does not see (templates are in the `omit` list), (b) schema and parametrised boundary tests have identical coverage but different inputs. Checked by hand:

- 14 e2e tests in `tests/e2e/test_csp_buttons.py` have identical coverage; each drives a different button and form under the production CSP, so they are not redundant.
- 19 tests in `tests/unit/db/test_core_schema.py` have identical coverage; they assert distinct SQL CHECK constraints (the Python line is the same `execute`). Not redundant.
- 10 tests in `tests/unit/services/test_recurring.py` (`test_quarterly_year_boundary`, `test_yearly_feb_29`, `test_monthly_end_of_month_clamp`, ...) have identical coverage and distinct boundary inputs. Keep.

Two candidates survive the hand check.

### F-23 Two duplicated tests can be removed (Low)
- **Severity / confidence:** Low / Confirmed (read both). **Root cause:** weak-assertion (redundancy; no defect).
- **Location(s):** (1) `tests/e2e/test_accessibility.py:24-31` (`test_landmarks_present`, 4 browser tests) repeats the static-HTML facts already asserted without a browser by `tests/integration/web/test_accessibility.py:53-60` (`test_semantic_landmarks`: `main#main`, an `h1`) and `:75-78` (`test_flash_live_regions_present`: the two flash regions). `main#main`, the flash regions and the `h1` are server-rendered in `templates/base.html:40-56` and `today/index.html:11`, so a browser adds nothing, costs about 4 browser page loads, and is the test that flaked in the known lead (section 10). (2) `tests/integration/test_promotion_flow.py:95-125` and `tests/unit/services/test_planned.py:319-333` patch the same function (`planned_repo.stamp_promotion`), raise the same exception and assert the same absence of a partial transaction and an unstamped planned row.
- **Mitigation:** Delete the e2e `test_landmarks_present` (keep `test_skip_link_focuses_first` and `test_tab_reaches_primary_nav`, which need a browser) and keep the integration promotion test (it asserts through raw SQL, the unit test asserts through the repository) or the unit one, not both. Effort S.
- **Related:** F-16.

Recommendation for the ADR-0108 section 2 criterion: line-level contexts are too coarse for this suite. A usable redundancy criterion needs the per-test mutant kill set (Mutmut `mutmut tests-for-mutant` style data); a test is a removal candidate only if its kill set is contained in another test's and it also covers no template or JS behaviour. I did not attempt that here (it needs the full Mutmut result store, which the baseline did not commit).

## 9. Fixtures, helpers and the harness

### F-17 The web test client hides transport-level bugs: CSRF is attached to every request, `https` is forced, and unit tests give the FX client a `base_url` production never sets
- **Severity / confidence:** Medium / Confirmed. **Root cause:** weak-assertion (test infrastructure that masks defects).
- **Location(s):** `tests/integration/web/conftest.py:45-70` (`_CSRFAwareTestClient`: sets `base_url="https://testserver"` and re-attaches the CSRF header to every unsafe request from the cookie jar); `tests/e2e/conftest.py:217` (`context.set_extra_http_headers({CSRF_HEADER_NAME: token, ...})`, Track E E-08: every browser request gets the header, even raw `fetch`); `tests/unit/services/test_fx.py:20-24`, `test_forecast.py:34-47`, `test_forecast_monthly.py:36-47`, `test_forecast_next_due.py:41`, `tests/integration/conftest.py:229,243`, `tests/integration/test_fx_fetch_flow.py:37` (all build `httpx.Client(transport=MockTransport(...), base_url="https://api.frankfurter.app")`); production builds clients without `base_url` at `web/today_data.py:124`, `web/routers/forecast.py:49`, `services/forecast.py:950` (Track G G-01).
- **Description:** Each helper silently supplies what the production code lacks. The FX unit tests are the direct reason G-01 (live FX fetch can never succeed) survived: a client with a base URL always works. The CSRF-aware client means a router that forgets the token (or a JS `fetch` that does not send it) passes every integration and e2e test except `tests/integration/web/test_csrf.py`, which uses raw clients. The forced `https` base URL hides `Secure` cookie and scheme-dependent behaviour on plain HTTP.
- **Impact:** CSRF regressions on a new endpoint are found only by `test_csrf.py`'s enumerated routes; the FX defect shipped.
- **Mitigation:** (1) Make the FX client a single factory (`services/fx.py`, the G-01 mitigation) and have tests inject a transport into the same factory so the production `base_url` is exercised. (2) Add a route-enumerating test to `tests/integration/web/test_csrf.py` that iterates every POST/PUT/PATCH/DELETE route of the app (the D-track `repro/D/route_table.py` shows how) with a raw client and asserts `403` without the header. (3) Keep the CSRF-aware client but name it as such in test docstrings.
- **Effort:** M. **Related:** Track E E-08, Track G G-01, Track D.

### F-24 Fixture and setup duplication
- **Severity / confidence:** Low / Confirmed. **Root cause:** weak-assertion (maintainability of tests).
- **Location(s):** the `conn` fixture is written three times with the same shape (Settings, `get_connection`, yield, close): `tests/integration/conftest.py:54`, `tests/unit/services/conftest.py:17`, `tests/unit/repositories/conftest.py:23`. The bcrypt-cost patch `monkeypatch.setattr(_passwords, "DEFAULT_ROUNDS", ...)` is repeated in 10 places with values 4, 5 and a `FAST_ROUNDS` constant: `tests/integration/auth/conftest.py:18`, `tests/integration/web/conftest.py:89`, `tests/integration/startup/{test_startup_migrate.py:41,test_set_password_cli.py:24,test_lifespan.py:30}`, `tests/unit/services/{test_passwords.py:33,77,test_users.py:36,test_users_admin.py:40,test_password_change.py:28}`. `Settings(_env_file=None, database_url=f"sqlite:///{...as_posix()}")` is hand-built in 36 places although `tests/db_template.py` exposes `sqlite_url`. `make_user` / `seed_login_user` exist in `tests/auth_support.py:25` and `tests/integration/auth/conftest.py:22` and a third `_seed_user` in `tests/unit/repositories/test_user_isolation.py:40`.
- **Mitigation:** Move `conn` and an autouse fast-bcrypt fixture to `tests/conftest.py` (one definition; integration keeps its own template-copy variant under a different name), and route every URL through `sqlite_url`. The last change also removes the F-20 exposure. Effort S.

## 10. Flakiness

Random-order run: seed `20261119`, `-n 2`, `--random-order` (pytest-random-order, which is what `pyproject.toml` lists; the plan named `pytest-randomly`, which is not installed): **2645 passed, 17 skipped, 0 failed**, 279 s, all e2e included. One run is not proof of absence; no order dependence was observed.

Sleeps and fixed timeouts: no `time.sleep` in test bodies; only readiness polls in `tests/e2e/conftest.py:80-84`, `tests/visual/conftest.py:102-105`, `tests/integration/web/test_graceful_shutdown.py:35-40` and subprocess `timeout=` arguments. Those are sound.

### F-16 `test_pagination_keeps_filters` races two in-flight HTMX responses; the product has no `hx-sync`
- **Severity / confidence:** Medium / Probable (root cause derived from the template and the test; not reproduced under controlled delay). **Root cause:** `htmx-contract` (product) plus a test that cannot wait on the right condition.
- **Location(s):** test: `tests/e2e/test_ledger_filters.py:73-81` (`_open_filtered`), `:109-114` (`test_pagination_keeps_filters`); constants `:13-16` (`_PAGE_SIZE = 50`, `_ROWS_A = 51`, 3 Beta rows). Product: `templates/ledger/index.html:25-29` (the filter form `hx-trigger="change, submit"`, target `#ledger-table`, `outerHTML`) and `templates/ledger/_table.html:386-389` (the "Older" button, `hx-include="#ledger-filters"`, same target); `grep -rn hx-sync templates/` returns nothing.
- **Description:** (1) The test selects category Alpha and waits for `to_have_count(_PAGE_SIZE)` (50 rows). The *unfiltered* ledger already shows 50 rows (Alpha 51 + Beta 3 = 54 rows, page size 50), so the wait is satisfied immediately by the stale unfiltered table, before the filtered response arrives. (2) The test then clicks "Older". `hx-include="#ledger-filters"` is evaluated at click time, so the request already carries the Alpha filter and page 2, and returns 1 row. (3) The earlier filter-change request is still in flight. Both responses swap `#ledger-table` with `outerHTML`, and htmx does not order them: if the page-1 filtered response (50 rows) lands after the Older response (1 row), the final table has 50 rows and `to_have_count(_ROWS_A - _PAGE_SIZE)` times out. On an idle machine the filtered response wins the race by a wide margin; under load the order flips. This matches the report that it fails under load and passes on retry.
- **Evidence:** structural (template and test constants as cited). The same missing `hx-sync` means a real user who changes a filter and clicks "Older" quickly can see the stale page overwrite the newer one. No `hx-sync` anywhere in the templates (E track's matrix does not list it). The full suite did not fail under 2 workers.
- **Impact:** A flaky e2e test, and a latent UX race (stale response overwrites the newer one) on every `hx-get` that two controls can trigger.
- **Mitigation:** Product: add `hx-sync="#ledger-table:replace"` (or `hx-sync="this:replace"` on the form and the button) so the newer request aborts the older. Test: after `select_option`, wait for the filtered response with `page.expect_response(lambda r: "/ledger/table" in r.url and "category_id=" in r.url)` (as `test_search_keeps_other_filters` does) before clicking "Older"; do not use a count that equals the unfiltered page size as the sync point.
- **Effort:** S. **Related:** Track E (HTMX contract), F-23.

### F-21 Time-dependent tests that can fail at the end of the month or in the Warsaw midnight window
- **Severity / confidence:** Medium / Probable (read, not run with a shifted clock). **Root cause:** `clock`.
- **Location(s):** `tests/integration/web/test_budget.py:561-565` (a planned item dated `datetime.now(UTC).date() + 1 day`, asserted to appear as "unbudgeted committed 35000" and `data-committed == "0"` on `/budget`): on the last day of a month the item falls into the next month, outside the committed window, and the first assertion fails; between 22:00 or 23:00 UTC and midnight the server's display zone (Europe/Warsaw) is already on the next day, so "tomorrow in UTC" is "today" there. `tests/integration/web/test_accounts.py:209,424,459` use `date.today()` (host zone) while the router computes today in the display zone (`web/routers/accounts.py:46`, Track C C-08). 23 sites in `tests/` call the real clock (Track C); no `freezegun` / `time-machine` is installed; the visual suite freezes at 10:00 UTC (`tests/visual/frozen_server.py:23`), so the divergence window is never exercised. `tests/unit/repositories/test_recurring.py:100,124,151` and `tests/integration/web/test_recurring.py:757` also compute from the real date.
- **Description:** These tests pass on 29 of 30 days and during 22 of 24 hours. They are a time bomb for CI on the last day of a month.
- **Mitigation:** Inject a fixed date into those tests the way `tests/integration/web/test_accounts_jpy.py:29` and `test_accounts_planned.py:29` do (`monkeypatch.setattr("...accounts._today", lambda: TODAY)`), and derive the dates from that constant; add one test class that runs the budget page with the clock set to 23:30 UTC (this requires the single injected clock of Track C).
- **Effort:** S per test, M for the shared clock fixture. **Related:** Track C C-08, A-13, ADR-0007.

### F-25 Fifteen permanently skipped tests for the pre-redesign layout
- **Severity / confidence:** Low / Confirmed. **Location(s):** `tests/integration/web/test_accounts.py:40,196,227,247,261,369,401,438,471,575` (10 tests, "v1 accounts card layout superseded by Rising Dough table"), `tests/integration/web/test_settings.py:25,42,58,97` (4, "v1 drawer shape"), `tests/e2e/test_credit_card_journey.py` (1, "re-enable after Phase 7"). The random-order run reports 17 skips: these 15, `tests/unit/deploy/test_ci_ssh_key_drill_only.py:49` (empty parameter set) and `tests/unit/deploy/test_prod_db_seed.py:188` (`shellcheck` not installed).
- **Description / mitigation:** Dead tests keep coverage claims and docs alive for behaviour that no longer exists. Delete them or rewrite them for the new layout; ADR-0051 Phase 7 is the stated re-enable point. The `shellcheck` skip means `scripts/prod_db_seed.sh` (a prod script) is not linted locally. Effort S.

## 11. Gaps: critical flows, snapshots, e2e

Critical flows from the plan:

| Flow | E2E test | UI driven? | Notes |
|---|---|---|---|
| Add transaction | `tests/e2e/test_add_transaction_flow.py` | no: `page.request.post` for account, category and transaction; the page only reads | the add-transaction slide-over form is opened and submitted in `tests/e2e/test_csp_buttons.py:56-80` |
| Reconcile | `tests/e2e/test_reconcile_flow.py` | no: 4 `request.post`, 0 clicks | default category only (F-07) |
| Promote recurring | `tests/e2e/test_recurring_promote_flow.py` | no: 5 `request.post`, 0 clicks | |
| Set budget | `tests/e2e/test_set_budget_flow.py` | no: 4 `request.post`, 0 clicks | default tier only (F-18) |
| Login / passkey | `tests/e2e/test_passkey_journey.py` | yes (13 interactions, virtual authenticator) | password login is only the harness `request.post` (`e2e/conftest.py:200-210`) plus `integration/web/test_auth_login.py` |

### F-15 Four of the five "critical flow" e2e tests are API tests run in a browser; no test submits the add, reconcile, promote or budget forms through the UI
- **Severity / confidence:** Medium / Confirmed. **Root cause:** weak-assertion (coverage of flows).
- **Location(s):** `tests/e2e/test_add_transaction_flow.py:19-68`, `test_reconcile_flow.py:19-65`, `test_recurring_promote_flow.py:26-100`, `test_set_budget_flow.py:19-62`, `test_credit_card_journey.py` (skipped, F-25); `tests/e2e/test_csp_buttons.py` is the only suite that clicks form buttons, and it asserts CSP-compatibility and that the form submits (a sampling of forms: add slide-over, planned, recurring, account, category).
- **Description:** These tests post forms with Playwright's HTTP client (which attaches the CSRF header from the harness) and then load the page to check the result. HTMX wiring, `hx-include`, the modal and slide-over markup, and the client-side validation are not on the path. The reconcile modal and the promote modal (`partials/recurring/_promote_modal.html`, `partials/planned/_promote_modal.html`) are never opened by any test.
- **Impact:** The ledger-filter incident (F-16) and the E-track HTMX contract findings (E-01) are exactly the class this suite cannot detect for these four flows.
- **Mitigation:** Rewrite the four tests to drive the visible forms (`page.get_by_role(...).click()` / `fill`) for the one happy path each, and keep `request.post` only for seeding. Effort M.
- **Related:** Track E E-01, F-17.

### F-22 The visual suite is opt-in, byte-exact, silently creates missing baselines, and its baselines predate the last template change
- **Severity / confidence:** Medium / Confirmed. **Root cause:** `config-drift` (a gate that does not run).
- **Location(s):** `justfile:78-84` (`test-visual` "Opt-in; not part of `just ci`"); `pyproject.toml:159-160` (`-m "not visual and not smoke"` in `addopts`); `.github/workflows/*.yml` has no visual job; `tests/visual/test_snapshots.py:105-109` (a missing baseline is written and the test `pytest.skip`s: it can never fail on an absent file); `:116` (`filecmp.cmp(..., shallow=False)`, a byte comparison of PNGs); `git log`: baselines last changed 2026-11-06 (`e064b25`), templates and CSS last changed 2026-11-18 (`54bfd6a`). 15 baselines for 5 routes (`/today`, `/ledger`, `/accounts`, `/budget`, `/plan`) at 3 viewports.
- **Description:** A suite that is not run automatically gives no regression signal, and the repository's frontend rule (CLAUDE.md "Frontend validation") relies on a manual skill instead. Byte-exact PNG comparison across machines and Chromium versions is brittle, which is probably why it is opt-in. I did not run it (not part of the gate).
- **Impact:** Visual regressions reach `main`; baselines that nobody reviews drift.
- **Mitigation:** Run the visual job in a scheduled/nightly workflow on a pinned Playwright image, compare with a perceptual threshold (for example Playwright's `to_have_screenshot(max_diff_pixel_ratio=...)`) instead of byte equality, make a missing baseline a failure in CI, and refresh baselines in the same PR as a template change (a pre-commit check that the baselines directory changes when `templates/` changes).
- **Effort:** M. **Related:** ADR-0027 section 4, Track H1 (CI), CLAUDE.md frontend rule.

## 12. Prod-DB safety

Searched `tests/`, `justfile`, `.github/`, `scripts/`, `.pre-commit-config.yaml`, `pyproject.toml`, `docker-compose.yml`, `Dockerfile*` for `budget.sqlite`, `data/budget` and for `Settings()` / `create_app()` / `get_connection()` calls without an explicit `database_url`.

**Verdict: no test, fixture, script, workflow or pre-commit hook resolves to `data/budget.sqlite` today.** All DB-touching tests use `tmp_path`, the session template copy (`tests/db_template.py`), or a `live_server` temp file; `tests/e2e/conftest.py:106`, `tests/visual/conftest.py:89` and `tests/integration/web/test_graceful_shutdown.py:48` set `BUDGET_DATABASE_URL` for their server subprocesses. The mentions in `justfile:26-62,202-210` and `scripts/prod_db_seed.sh:17` are the documented operator recipes (they are never called by a test; `tests/unit/deploy/test_prod_db_seed.py:94` asserts on the script text only). The mutmut copy tree under a scratchpad has no `data/` directory.

### F-20 Prod-DB isolation depends on `BUDGET_ENV=test` being set by default and on convention; there is no tripwire
- **Severity / confidence:** Medium / Confirmed for the mechanism, Probable that it can fire (not reproduced, to avoid touching the file). **Root cause:** `scoping-gap` (test isolation).
- **Location(s):** `tests/conftest.py:19` (`os.environ.setdefault("BUDGET_ENV", "test")`: a shell that exports `BUDGET_ENV=dev` wins); `config.py:20-21,45` (default `database_url` is the relative path `sqlite:///data/budget.sqlite`, resolved against the current directory); `services/users.py:231-233` (in the `test` env without credentials the lifespan does not open the DB; in any other env it opens it); `web/app.py:134-139` (lifespan calls `bootstrap_admin_at_startup`); tests that enter the lifespan with default settings: `tests/integration/web/test_app.py:111-117` (`TestClient(app)` as a context manager with `Settings(_env_file=None, base_currency="EUR")`, no `database_url`).
- **Description:** Today the default test environment makes that test side-effect free. If a developer runs the suite from a checkout that has `data/budget.sqlite` with `BUDGET_ENV=dev` exported (or with `BUDGET_PLANNER_ADMIN_EMAIL` and `BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD` set in the shell), `bootstrap_admin_at_startup` opens the prod file through `get_connection` (which also runs `PRAGMA journal_mode = WAL`) and may call `bootstrap_admin`, a write. The suite's design relies on every test remembering to pass a temp `database_url`; `tests/unit/services/test_users.py:113` and 25 other `Settings(_env_file=None)` constructions only avoid it by not opening a connection.
- **Impact:** Violation of the CLAUDE.md "prod DB hands off" rule by a routine `pytest` run in an unusual shell. Not triggered in this audit.
- **Mitigation:** Add an autouse session fixture in `tests/conftest.py` that sets `BUDGET_DATABASE_URL` to a path under a session temp directory (and unsets `BUDGET_PLANNER_ADMIN_*`), plus a guard that makes `db.connection.get_connection` raise when the resolved path equals the repository's `data/budget.sqlite` while `PYTEST_CURRENT_TEST` is set. Replace `os.environ.setdefault` by an unconditional assignment of `BUDGET_ENV=test`. Add an architecture test that greps `tests/` for `budget.sqlite` outside the allowlisted text assertions.
- **Effort:** S. **Related:** CLAUDE.md "Databases", ADR-0069 section 1, F-24.

## 13. Mutmut "no tests" mutants

The 995 unscored mutants of T-Q03b (`auth` 535, `reauth` 237, `budget` 95, `balance` 65, `forecast` 51, `rate_limit` 12) come from **27 functions that no `tests/unit` test executes** (they are covered only by `tests/integration`, whose directory Mutmut's T-Q03b scope left out). `repro/F/functions_without_unit_tests.py` lists them from the per-test contexts: `budget.yearly_grid`; `balance.sparkline_points`, `balance.balance_series`; `forecast.monthly_projection` (no test of any kind, F-13); the two rate-limit rule factories for password change and reauth; 14 functions in `auth` (`authenticate_password`, `load_session_user`, `register_passkey_finish`, `authenticate_passkey_finish`, `sign_count_regressed`, `revoke_*`, `logout`, ...); 6 in `reauth`.

### Scoring done (money subset)

Method: a copy of the audit tree in a scratch directory (`[tool.mutmut]` added there only; no repo file changed), mutmut 3.7 with `--with 'libcst<1.9'`, `--max-children 2`, shared lock held, `tests_dir = tests/unit/services + tests/integration` (minus `integration/startup` and `test_graceful_shutdown.py`, which need the repo's `deploy/` tree), and only the mutants of the five functions below selected with name globs (`budget_planner.services.<module>.x_<function>__mutmut_*`). Rate: 0.64 mutants/s.

| Function | Mutants | Killed | Survived | Killed % |
|---|---|---|---|---|
| `budget.yearly_grid` | 95 | 57 | 38 | 60.0 |
| `balance.sparkline_points` | 40 | 14 | 26 | 35.0 |
| `balance.balance_series` | 25 | 16 | 9 | 64.0 |
| `rate_limit.password_change_rules` | 6 | 5 | 1 | 83.3 |
| `rate_limit.reauth_rules` | 6 | 5 | 1 | 83.3 |
| **Total scored** | **172** | **97** | **75** | **56.4** |

The 75 survivors were **not triaged** into real gap, equivalent and low value (not enough time; the sample reads below are by inspection of the code only). They are recorded as results, not as individual rows. For comparison the services baseline killed 84.3 percent of testable mutants.

Not scored: `forecast.monthly_projection` (51 mutants): no test executes it, so every mutant would survive by construction (F-13); `auth` (535) and `reauth` (237): 772 mutants, about 20 minutes at the measured rate but needing the `integration/auth` and `integration/web/test_auth_*` selection and an operator-quiet machine; **not done**. Recipe for a later run: same config as above with `source_paths = ["src/budget_planner/services/auth.py", "src/budget_planner/services/reauth.py"]` and `mutmut run "budget_planner.services.auth.*" "budget_planner.services.reauth.*"`.

### F-27 `balance.sparkline_points` and `balance_series` are only tested through the HTML card, and the tests that did so are among the skipped v1 tests; `yearly_grid` kills only 60 percent
- **Severity / confidence:** Medium / Confirmed (scored mutants; the explanation of the survivors is by reading the code). **Root cause:** weak-assertion.
- **Location(s):** `services/balance.py:166-188` (`sparkline_points`, pure function, no unit test), `:191-217` (`balance_series`); callers `web/routers/accounts.py:70-86` only; tests `tests/integration/web/test_accounts.py:229-244` (monkeypatches `balance_service.balance_series` by plain assignment) which sits next to the skipped v1 card tests (`:227` is in the skip list, F-25). `services/budget.py:603` `yearly_grid` (38 survivors of 95; also hidden from the coverage report by F-12).
- **Description:** `sparkline_points` maps values to SVG coordinates with `round(..., 2)` and a flat-series special case; 26 of its 40 mutants (arithmetic and rounding in the coordinate maths, the `span == 0` branch) survive because no test asserts the returned string. `balance_series` survivors are the inclusive/exclusive date ends. `yearly_grid` is the budget grid page's data; its only equality check against `resolve_budget` is Track A's script (INV-8a, F-14).
- **Impact:** A wrong or inverted chart and an off-by-one day in the card; for `yearly_grid` a wrong monthly budget figure.
- **Mitigation:** Unit tests in `tests/unit/services/test_balance.py`: `sparkline_points([1, 3, 2])`, a flat series, fewer than two points (`""`), exact expected strings; `balance_series(days=3, today=...)` asserting the three `(date, balance)` pairs including the end date; for `yearly_grid` a parametrised test over default / recurring / one-off tiers asserting every month cell against `resolve_budget`.
- **Effort:** S. **Related:** F-12, F-13, F-14, F-25.


## 14. Questions for Phase 3

1. **Q-1.** `tests/e2e/test_accessibility.py::test_landmarks_present[/today]` is reported to fail under load. The facts it asserts are static HTML (`templates/base.html:40-56`, `today/index.html:11`) and `count()` does not wait, so a DOM-timing cause is unlikely. Remaining suspects: the 30 s default navigation timeout of `page.goto` under the Python route handler in `e2e/conftest.py:218-228` (`route.fetch` on every request), and the `page` fixture's teardown assertion on CSP or htmx-target errors raised by the `/today/afford` request still in flight (`today/index.html:63`). It did not fail in my loaded full run. Operator: can you capture a Playwright trace of one failure (`--tracing retain-on-failure`)? F-23 deletes the test anyway.
2. **Q-2.** F-10: which policy is intended for archived categories and inactive rules in each service (include or exclude)? Track A A-11 asks the same question; the tests cannot be written until it is answered.
3. **Q-3.** Is `Europe/Warsaw` the only supported display zone? F-21 and Track C C-08 depend on it for the frozen-clock tests.
4. **Q-4.** Should the baseline's equivalent list receive `balance:147` (F-08)? It was classified as a real gap.
5. **Q-5.** F-12: the 49 newly visible missed statements are not individually triaged. A re-run of the coverage gate after the fix may drop the total near 94.5 percent, still above 90.

## 15. Repro index (`docs/plans/quality-audit/repro/F/`)

| File | What it shows |
|---|---|
| `weak_assert_scan.py`, `weak_assert_scan.out` | AST scan of 2175 test functions: 141 status-only, 13 status/not-None only, 7 no-assert, 4 truthy-only (section 6) |
| `coverage_without_ellipsis_exclusion.txt` | Full `coverage report -m` of the random-order run with the `...` exclusion removed (F-12) |
| `redundant_candidates.py`, `redundant_candidates.out` | Per-test unique-line analysis (section 8) |
| `functions_without_unit_tests.py`, `.out` | The 27 services functions only integration tests execute (section 13) |

Commands used (all with `PYTEST_WORKERS`-equivalent `-n 2`, under the shared lock):

```sh
# random-order run + per-test contexts + coverage without the ... exclusion (one run)
pytest -n 2 --dist loadgroup -o addopts="" -m "not visual and not smoke" --strict-markers \
  -p no:cacheprovider --random-order --random-order-seed=20261119 \
  --cov=src/budget_planner --cov-config=<covrc without the \.\.\. line> --cov-context=test --cov-report= -q -ra
# then: coverage report --rcfile=<covrc> -m ; python redundant_candidates.py <data> ; python functions_without_unit_tests.py <data> <root>
```

The coverage config used for that run was `pyproject.toml`'s `[tool.coverage]` with only the `"\\.\\.\\."` pattern removed, `branch = true`, the same `omit`.
