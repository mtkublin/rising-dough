# Track B — Layering and architecture (T-Q05)

`AUDIT_SHA = 9fb18cbca26ef305855efc8fc106d896edc82631`. All `path:line` cites are valid at this SHA (paths are under `src/budget_planner/` unless written in full). Read-only audit: nothing in `src/`, `tests/` or config was changed. Repros run on a scratch DB (`/tmp/audit-B.sqlite`, copied from `data/demo.sqlite` and migrated to the current schema, because the demo file lags the schema); `data/budget.sqlite` was never opened.

Cross-references: duplication of validation/parsing/FX code is Track A; clocks, silent fallbacks, N+1 and concurrency are Track C; template and HTMX contracts are Track E. This track records only the layering aspect and points to them.

## 1. Coverage statement

Read in full: `repositories/_shared.py`, `repositories/recurring.py` (mutation + override parts), `services/recurring.py` (orchestrators), `services/planned.py` (promotion), `services/reconciliation.py`, `services/accounts.py`, `web/routers/plan.py`, `web/routers/recurring.py` (all handlers listed in section 4), `web/routers/ledger.py` (hydrate, summary, index), `web/routers/planned.py` (undo, create), `web/routers/transactions.py` (create, update), `web/routers/accounts.py` (create, reconcile, snapshot), `web/routers/budget.py` (create_override).
Classified exhaustively from tooling plus targeted reads (nothing sampled): every SQL site outside `repositories/` and `db/migrate.py` (21 hit lines, table 2.1), every `PLC0415` (37, table 2.2, with a script that tests whether a top-level import would create a cycle), every `PLR0917` (32, table 2.3, with a script that dumps each signature), every function > 50 lines or complexity C or worse (table 2.4).
Whole-tree AST scripts (output in section 6): non-frozen dataclasses (none), classes outside DTO/Protocol/framework use, module-level mutable state, mutation of function parameters.
Checked by grep across all of `src/`: `commit()` / `rollback()` outside the transaction helper (none), `executescript` (none), every public mutation helper in `repositories/` (does it use `mutate`), every SELECT in `repositories/` against soft-deletable tables (does it filter `deleted_at`).
Not read line by line: `routers/auth.py` body beyond `login_password` (its 7 `PLR0917` handlers were classified from signatures; it delegates to `services.auth`, no business logic seen), `routers/settings*.py`, `routers/today.py`, `routers/forecast.py`, `routers/analytics.py`, `services/budget.py`, `services/forecast.py` bodies, `web/charts.py`. For those, table 2.4 gives a layer verdict from the layer they live in and the baseline numbers, marked "by location". Sections 4 and 5 list only what I verified.

## 2. Classification tables

### 2.1 SQL outside `repositories/` and `db/migrate.py` (every hit line)

| # | Site | What | Verdict |
|---|---|---|---|
| 1-6 | `db/connection.py:53-57,74` | `PRAGMA` journal/synchronous/autocheckpoint/busy_timeout/secure_delete/foreign_keys | legitimate (connection factory) |
| 7 | `db/startup_migrate.py:98` | `VACUUM INTO ?` backup | legitimate (ops, not entity data) |
| 8 | `domain/enums.py:40` | `UPDATE = "update"` enum member | false positive of the grep |
| 9 | `services/users.py:112` | `PRAGMA table_info(users)` schema probe at bootstrap | legitimate |
| 10 | `web/app.py:59` | `PRAGMA wal_autocheckpoint` startup assertion | legitimate, but a `web -> db` edge (B-15) |
| 11 | `web/routers/health.py:64` | `PRAGMA integrity_check` readiness probe | legitimate, but a `web -> db` edge (B-15) |
| 12 | `services/accounts.py:35` | `SELECT ... FROM account_snapshots JOIN accounts WHERE a.user_id = ? GROUP BY` | user-scoped, read-only. Does not filter `a.deleted_at` although its docstring says "non-deleted accounts"; harmless because the only caller joins to `accounts_repo.list_all` (live). Belongs in a repository (B-14) |
| 13 | `services/accounts.py:63` | `SELECT account_id, MAX(operation_date) FROM transactions WHERE user_id=? AND category_id=? AND deleted_at IS NULL` | user-scoped and soft-delete-aware. Belongs in a repository (B-14) |
| 14 | `web/routers/planned.py:140` | `SELECT prev_json FROM audit_log WHERE entity_type='planned_transaction' AND entity_id=? AND operation='update' ORDER BY id DESC LIMIT 1` | **user-scoping risk** (no `user_id` predicate; B-11) and **audit replay by "latest row"** (B-03) |
| 15 | `web/routers/planned.py:155` | `UPDATE planned_transactions SET promoted_to_txn_id=?, updated_at=...` | **audit-log bypass**: raw write in a router, no `mutate`, no `audit_log` row (B-03, confirmed). Soft-delete not involved. User-scoped (`AND user_id = ?`). |
| 16 | `web/routers/recurring.py:501` | `SELECT prev_json FROM audit_log WHERE entity_type='recurring_rule' AND entity_id=? ORDER BY id DESC LIMIT 1` | **user-scoping risk** (B-11) and **audit replay by "latest row"** with no `operation` filter (B-03) |

The baseline counted 21 hit lines in 9 files. The table covers all of them: rows 1-6 are 6 lines, 7-11 are 5 lines, rows 12, 13, 14, 15 and 16 are 5 queries that the grep counted as 10 lines (each `execute(` plus its SQL literal). No other `.execute(` exists outside `repositories/`, `db/`, and the six files above. `conn.commit()`, `conn.rollback()`, `executescript` and `.cursor()` do not occur outside `db/migrate.py` (and there only in a comment).

Verdict totals: legitimate 11 (rows 1-11), belongs in repository 2 (12-13), audit-log bypass 1 (15), unscoped read 2 (14, 16).

### 2.2 `PLC0415` suppressions (37; "cycle?" = whether a top-level import of that target would create a cycle in today's graph)

| # | Site | Target | Verdict |
|---|---|---|---|
| 1 | `web/app.py:238` | `importlib` | unnecessary (stdlib) |
| 2 | `web/routers/recurring.py:419` | `json` | unnecessary |
| 3 | `web/routers/recurring.py:482` | `repositories.{recurring,transactions}` | unnecessary: the module already imports `repositories` at line 26 |
| 4 | `web/routers/recurring.py:486` | `repositories._shared.transaction` | unnecessary; also a private-module import from a router (B-04) |
| 5 | `web/routers/recurring.py:511` | `json` | unnecessary |
| 6 | `web/routers/plan.py:116` | `calendar` | unnecessary |
| 7 | `web/routers/plan.py:117` | `dataclasses` | unnecessary |
| 8 | `web/routers/plan.py:119` | `repositories.recurring` | unnecessary (and a router-to-repository import, B-04) |
| 9 | `web/routers/plan.py:120` | `services.preferences` | unnecessary |
| 10 | `web/routers/plan.py:233` | `calendar` | unnecessary (duplicate of #6) |
| 11 | `web/routers/planned.py:70` | `json` | unnecessary |
| 12 | `web/routers/planned.py:123` | `repositories.transactions` | unnecessary |
| 13 | `web/routers/planned.py:124` | `repositories._shared.transaction` | unnecessary |
| 14 | `web/routers/planned.py:151` | `json` | unnecessary |
| 15 | `web/routers/planned.py:184` | `web.routers.ledger.render_table_for` | unnecessary for cycle reasons (ledger does not import planned); symptom of a misplaced helper (router-to-router import, B-12) |
| 16 | `web/routers/transactions.py:195` | `web.routers.ledger.render_table_for` | same as #15 |
| 17 | `web/routers/today.py:216` | `web.routers.recurring._EMPTY_TERM_INPUT, _formula_source_candidates` (private names) | unnecessary for cycle reasons; misplaced helpers (B-12) |
| 18 | `web/routers/health.py:53` | `db.connection.get_connection` | unnecessary; the comment cites a cycle through `web.app`, which does not exist today. Hides a `web -> db` edge (B-15) |
| 19 | `db/migrate.py:223` | `json` | unnecessary (comment says "keeps top-level imports lean": deliberate but pointless) |
| 20 | `services/forecast.py:495` | `services.balance` | unnecessary: `balance` does not import `forecast` |
| 21 | `services/recurring.py:384` | `repositories.{categories,recurring,transactions}` | **real cycle** for `recurring` (`repositories.recurring -> services.recurring`); `categories` and `transactions` alone would be fine |
| 22 | `services/recurring.py:389` | `repositories._shared.transaction` | unnecessary (`_shared` imports no service) |
| 23 | `services/recurring.py:390` | `services.audit` | unnecessary |
| 24 | `services/recurring.py:391` | `services._promotion` | unnecessary |
| 25 | `services/recurring.py:408` | `services.recurring_formula.resolve_rule_amount` | **real cycle**: `recurring_formula` imports `services.recurring` and `services.recurring` re-exports `recurring_formula` at module bottom (line 635, `E402`) |
| 26 | `services/recurring.py:515` | `repositories.recurring` | **real cycle** (as #21) |
| 27 | `services/recurring.py:516` | `repositories._shared.transaction` | unnecessary |
| 28 | `services/recurring.py:517` | `services.audit` | unnecessary |
| 29 | `services/recurring.py:603` | `repositories.recurring` | **real cycle** (as #21) |
| 30 | `services/recurring.py:604` | `repositories._shared.transaction` | unnecessary |
| 31 | `services/recurring.py:616` | `domain.enums.OverrideState` | unnecessary (inside a loop body; `OverrideState` is already imported at module top as used elsewhere in the file) |
| 32 | `services/recurring_formula.py:166` | `repositories.recurring` | **real cycle** (as #21) |
| 33 | `services/recurring_formula.py:167` | `services.recurring` | **real cycle** (`services.recurring <-> recurring_formula`) |
| 34 | `services/recurring_formula.py:213` | `repositories.recurring` | **real cycle** (as #21) |
| 35 | `services/recurring_formula.py:336` | `services.recurring` | **real cycle** (as #33) |
| 36 | `services/recurring_formula.py:392` | `repositories.recurring` | **real cycle** (as #21) |
| 37 | `services/recurring_formula.py:475` | `repositories.categories` | unnecessary (no cycle; probably copied from the neighbours) |

Totals: real cycle 9 (#21, 25, 26, 29, 32-36), unnecessary 28, deliberate lazy import for a good reason 0. Two real root edges explain all nine: `repositories/recurring.py:31` imports `services.recurring.first_due_on_or_after`, and `services/recurring.py:635` (module bottom, `E402`) imports `services.recurring_formula`. The comment at `services/recurring.py:380-383` is correct about the first edge. A third group (#22-24, 27, 28, 30) sits in the same functions and was copied along with the real ones.

### 2.3 `PLR0917` suppressions (32). "Swap risk" = two or more adjacent positional parameters of the same type that would not be caught by mypy if swapped.

FastAPI route handlers (24) are called by the framework by keyword, never positionally, so no swap can happen at a call site. `PLR0917` has no signal there; see B-08 for the config fix.

| # | Site | Positional params | Swap risk |
|---|---|---|---|
| 1 | `web/routers/auth.py:344` `login_password` | request, email, password, next_path (all `str` after `request`), conn, settings, ctx, limit | no (handler); email/password are `str` form fields but keyword-bound |
| 2 | `auth.py:392` `login_passkey_finish` | request, next_path, conn, settings, ctx, limit | no (handler) |
| 3 | `auth.py:494` `register_passkey_finish` | request, conn, settings, ctx, user, limit | no (handler) |
| 4 | `auth.py:556` `revoke_session` | request, handle, conn, settings, ctx, user | no (handler) |
| 5 | `auth.py:632` `_reauth_success` | request, conn, settings, user, ctx, response, *method | no: all distinct types |
| 6 | `auth.py:669` `reauth_password` | request, password, next_path, conn, settings, ctx, user, limit | no (handler) |
| 7 | `auth.py:729` `reauth_passkey_finish` | request, next_path, conn, settings, ctx, user, limit | no (handler) |
| 8 | `web/routers/recurring.py:810` `add_override` | rule_id, request, year, month, amount, conn, user_id (`int,int,int`) | no (handler) |
| 9 | `recurring.py:1016` `promote_submit` | rule_id, request, operation_date, amount, description (`str,str,str`), conn, user_id | no (handler) |
| 10 | `web/routers/accounts.py:186` `create_account` | 5 `str` form fields in a row | no (handler) |
| 11 | `accounts.py:279` `update_account` | account_id, request, name, type, is_liability, credit_limit | no (handler) |
| 12 | `accounts.py:445` `reconcile_submit` | account_id, request, 3 `str` | no (handler) |
| 13 | `web/routers/categories.py:79` `create_category` | request, name, direction, color, clear_color | no (handler) |
| 14 | `categories.py:150` `update_category` | category_id, request, name, color, clear_color | no (handler) |
| 15 | `web/routers/planned.py:220` `create_planned` | category_id, account_id (`int,int`), amount, description, dest_account_id (`str` x3) | no (handler) |
| 16 | `planned.py:338` `update_planned` | planned_id, request, ..., category_id, account_id | no (handler) |
| 17 | `planned.py:484` `promote_submit` | planned_id, request, 3 `str` | no (handler) |
| 18 | `web/routers/budget.py:235` `create_override` | category_id, tier, month, year, amount (`str` x5) | no (handler) |
| 19 | `budget.py:348` `set_recurring` | category_id, month (`int,int`), amount | no (handler) |
| 20 | `budget.py:403` `set_one_off` | category_id, year, month (`int,int,int`), amount | no (handler) |
| 21 | `web/routers/transactions.py:167` `limit_preview` | request, account_id, category_id, amount (`str` x3) | no (handler) |
| 22 | `transactions.py:238` `create_txn` | 7 form fields incl. category_id, account_id (`int,int`) | no (handler) |
| 23 | `transactions.py:358` `update_txn` | txn_id, request, ..., category_id, account_id | no (handler) |
| 24 | `web/routers/settings_password.py:122` `change_password` | 3 `str` passwords + `next_path` | no (handler) |
| 25 | `services/forecast.py:433` `_collect_budget_overlay` | conn, user_id, **today, end_date** (`date,date`), directions_by_cat, **primary_account_id** (`int`) | **yes**: `today`/`end_date` and `user_id`/`primary_account_id`. One call site (`forecast.py:588`), correct order |
| 26 | `forecast.py:530` `forecast` | conn, **user_id**, http, today, **horizon_days**, base_currency, *include_budget_overlay | **yes** (`user_id`/`horizon_days` are both `int`). Call sites `forecast.py:814`, `web/routers/forecast.py` OK today |
| 27 | `forecast.py:778` `forecast_monthly` | conn, **user_id**, http, today, **horizon_months**, base_currency | **yes** (same pair). Call site `forecast.py:951` OK |
| 28 | `services/recurring.py:641` `expand_unpromoted` | conn, user_id, rule, overrides, **window_start, window_end** (`date,date`) | **yes**. 5 call sites (`forecast.py:276,764`, `account_planned.py:108`, `recurring.py:657`...) all positional and correct today |
| 29 | `services/reconciliation.py:62` `reconcile` | conn, **user_id, account_id, actual_balance_minor** (`int,int,int`), today, note, category_id | **yes, highest consequence**: swapping `account_id` and `actual_balance_minor` writes an adjustment on a different account. Single caller `routers/accounts.py:492` (positional, correct) |
| 30 | `services/budget.py:408` `_resolve_period_start` | conn, **user_id**, today, **year, month** (`int,int,int`), anchor_category | **yes**. Call sites `budget.py:451,501` correct |
| 31 | `services/recurring_formula.py:322` `rt_expand` | conn, user_id, rule, overrides, **range_start, range_end** (`date,date`) | **yes**. 3 call sites (`forecast.py:387`, `budget.py:307`, `recurring.py:657`) correct |
| 32 | `services/fx.py:119` `convert` | conn, http, amount_minor, on_date, **from_ccy, to_ccy** (`str,str`) | **yes** (swap silently inverts the rate direction). No caller in `src/` (only tests: `tests/unit/services/test_fx.py`, `tests/integration/test_fx_fetch_flow.py`); the production path uses `convert_cached`. Dead in prod, Track G candidate |

Summary: swap risk yes 8 (rows 25-32), no 24. In all 8 service signatures the user-scoping `user_id: int` sits next to other ints, which ADR-0061 §5 made the first positional parameter on purpose; the noqa comments cite that ADR. No call site swaps today.

### 2.4 Files over 800 lines and functions over 50 lines or complexity C or worse

Two files exceed 800 lines.

| File | Lines | Business-logic leak? | Split proposal |
|---|---|---|---|
| `web/routers/recurring.py` | 1115 | **Yes.** Form parsing, cadence/date validation, transit and currency validation (`_resolve_dest_account` 149-179), fixed-vs-formula amount resolution (`_resolve_amount_inputs` 181-240), "stop date in the past means insert inactive" (`create_rule` 357), "shorten stop date deactivates" (`update_rule_handler` 713), audit replay and rule rewrite (`recurring_batch_undo` 470-545), direct repository and `db_transaction` orchestration | Keep only HTTP concerns (`recurring_routes.py`, ~350 lines). Move parsing (`_parse_*`, `_parse_terms_from_form`, `_formula_prefill`) to `web/forms/recurring.py`. Move validation/amount resolution/activation rules to `services/recurring_rules.py` (`create_rule_checked`, `update_rule_checked`, `undo_batch`). Overrides and promote handlers to `recurring_overrides_routes.py`. Target: no file > 400 lines |
| `services/forecast.py` | 978 | No (service layer). It is four things in one module | `forecast_events.py` (128-300 events from persisted and recurring), `forecast_overlay.py` (303-485 budget overlay), `forecast_daily.py` (488-620 `forecast`, `_build_day`), `forecast_monthly.py` (621-978 `forecast_monthly`, `monthly_projection`, `_month_flow_sums`) with the dataclasses in `domain/forecast.py` |

Functions over 50 lines (41 per `baseline/sizes.txt`) and C-or-worse blocks (33 per `baseline/radon-cc.txt`), merged. "Leak" = business logic that belongs in a service sits in the router.

| Function | Lines | CC | Leak? | Split proposal |
|---|---|---|---|---|
| `web/routers/plan.py:68 plan` | 184 | E 31 | **yes** (section 4.2) | one handler per tab plus `services/plan_view.py` (fiscal month override, anchor-day clamp, month shift, totals rebuild) |
| `services/budget.py:454 month_summary` | 147 | C 19 | no (service) | extract per-row builders; split totals from period resolution |
| `services/recurring.py:356 promote_recurring` | 143 | C 17 | no (service) | `_resolve_promotion_inputs` (pure) + `_apply_promotion` (the single transaction) |
| `services/forecast.py:778 forecast_monthly` | 128 | - | no | see forecast split |
| `routers/recurring.py:269 create_rule` | 119 | C 16 | **yes** | see recurring split |
| `routers/recurring.py:633 update_rule_handler` | 108 | C 18 | **yes** | see recurring split; shares ~50 lines with `create_rule` (Track A) |
| `web/charts.py:144 line_area`, `297 grouped_bars`, `437 horizontal_bars`, `519 sparkline` | 102/101/62/67 | C 17/16 | no (SVG view-model builders; presentation) | by location; leave for Track E |
| `services/recurring_formula.py:485 preview` | 93 | - | no | split parse/evaluate/format |
| `services/forecast.py:530 forecast` | 89 | C 11 | no | see forecast split |
| `routers/transactions.py:238 create_txn` | 80 | C 16 | **yes**: transit/currency/amount validation inline | `services/transactions.py:create_checked` (B-02) |
| `routers/ledger.py:140 _hydrate_recurring_rows` | 80 | D 29 | **yes**: filter predicate chain, override precedence, formula amount | filtering into `services/ledger.py` (`filter_rules`), row assembly stays |
| `db/migrate.py:134 _backfill_recurring_next_due`, `:280 apply_migrations`, `:86 _split_sql_statements` | 79/72 | C | no (db layer) | by location |
| `routers/transactions.py:358 update_txn` | 77 | C 12 | **yes**: dest validation missing (B-02) | `services/transactions.py:update_checked` |
| `repositories/recurring.py:428 upsert_override` | 71 | - | no | by location |
| `routers/recurring.py:470 recurring_batch_undo` | 70 | C 12 | **yes** (SQL, audit replay) | `services/recurring.py:undo_batch` (B-03) |
| `routers/recurring.py:1016 promote_submit` | 69 | C 13 | **yes**: decimal parse, positivity | fold into a shared form-amount parser (Track A) and call `recurring_svc` |
| `services/reconciliation.py:62 reconcile` | 69 | - | no, but missing invariant (B-02) | add validation |
| `services/recurring.py:501 skip_and_advance` | 68 | - | no | fine after cycle fix |
| `routers/planned.py:220 create_planned` | 67 | C 13 | **yes** | `services/planned.py:create_checked` |
| `routers/accounts.py:279 update_account` | 67 | - | **yes** (by location, not read) | service |
| `routers/accounts.py:445 reconcile_submit` | 65 | - | **yes**: parse, available-credit mode, two commits (B-07) | `services/reconciliation.py:reconcile_and_snapshot` |
| `routers/planned.py:338 update_planned` | 64 | C 11 | **yes** | service |
| `services/forecast.py:710 _month_flow_sums` | 66 | C 15 | no | forecast split |
| `services/budget.py:253 _committed_by_category` | 63 | C 12 | no | by location |
| `routers/budget.py:170 new_override_form`, `:235 create_override` | 62/59 | C 12/12 | **yes**: tier dispatch, month/year bounds, decimal parse | `services/budget.py:set_override(tier, ...)` |
| `routers/accounts.py:186 create_account` | 62 | C 11 | **yes** | service |
| `routers/planned.py:484 promote_submit`, `:112 planned_batch_undo` | 61/60 | -/- | **yes** (undo has raw SQL, B-03) | service |
| `routers/recurring.py:181 _resolve_amount_inputs` | 59 | - | **yes** (formula build + validation + compute) | `services/recurring_rules.py` |
| `routers/recurring.py:810 add_override` | 58 | - | **yes** (year/month bounds, amount) | service |
| `services/forecast.py:654 _planned_budget_per_month` | 54 | - | no | forecast split |
| `services/auth.py:416 authenticate_passkey_finish` | 54 | - | no | by location |
| `routers/today.py:42 today` | 52 | - | by location: likely view assembly | not read |
| `services/recurring_formula.py:191 _sum_category_in_month`, `:384 validate_formula_sources` | 52/- | -/C 16 | no | by location |
| `services/income.py:43 next_anchor_date` | 51 | - | no | by location |
| `logging.py:96 configure` | 51 | - | no | by location |
| `routers/recurring.py:149 _resolve_dest_account` | 32 | C 12 | **yes** (transit, currency) | `services/transactions.py` (shared with B-02) |
| `routers/settings.py:52 drawer` | - | C 19 | **yes**: category grouping per tab | `services/categories.py:grouped` (by location) |
| `routers/ledger.py:395 index` | - | C 11 | partial: `planned_total_minor` sum in router | service |
| `web/auth_cookies.py:219 safe_next` | - | C 13 | no (open-redirect guard, correctly pure) | leave |
| `services/recurring.py:107 generate_occurrences`, `services/budget.py:603 yearly_grid` | - | C 12/11 | no | leave |
| `repositories/planned.py:68`, `transactions.py:69 _append_filter_clauses` | - | C 14/16 | no (SQL builder) | leave; it is a flat if-chain |
| `db/startup_migrate.py:102 prune_backups`, `web/middleware/auth.py:145 AuthRequiredMiddleware` | - | C 12/11 | no | leave |

Router functions: 20 of the 41 long functions and 16 of the 33 C+ blocks are in `web/routers/`.

## 3. Thin-web summary

| Router | Lines | Direct repository calls | Domain logic in the router (verified) | Findings |
|---|---|---|---|---|
| `recurring.py` | 1115 | yes, 6 repos incl. writes | validation, activation rules, audit replay, raw `db_transaction` | B-03, B-04, B-09 |
| `plan.py` | ~300 | 1 (lazy) | fiscal month, anchor day, totals rebuild, year handling | B-05 |
| `ledger.py` | 491 | yes (reads) | recurring-summary arithmetic, rule filtering, override precedence | B-01, B-04 |
| `planned.py` | 586 | yes incl. writes | raw SQL, audit replay, validation | B-03, B-04 |
| `transactions.py` | 507 | yes incl. writes | transit and currency validation, missing on update | B-02, B-04 |
| `accounts.py` | 509 | yes incl. writes | reconcile orchestration (two commits), available-credit mode | B-07, B-04 |
| `budget.py` | 428 | yes incl. writes | tier dispatch, bounds | B-04 |
| `auth.py` | 760 | webauthn/sessions reads only | none seen in `login_password`; thin | none |

## 4. Thin-web check: router logic with locations

### 4.1 `web/routers/recurring.py`

- `148-179` `_resolve_dest_account`: transit needs a destination, same currency, different account. Duplicate of the logic in `transactions.py:263-283` and `planned.py:244-251`, but with different rules (see B-02).
- `181-240` `_resolve_amount_inputs`: formula term build, source validation, snapshot compute, `Decimal` parse, `<= 0` check, `to_minor_units`. Money rule in the router.
- `357-372` `create_rule`: "end date in the past means `active=False` on insert" (ADR-0063) is an activation rule decided in the router; `assert c is not None ...` as control flow after validation.
- `633-740` `update_rule_handler`: "if `rule.next_due > end`, patch `active=False`" (`713`) is a second copy of the same rule on update.
- `470-545` `recurring_batch_undo`: raw SQL (`501`), `json.loads` of audit payload, rewrite of `next_due` and `last_promoted_date` through an audit-free helper (`522`), `db_transaction` opened in the router (`486`, `495`).
- `810-868` `add_override`: year/month bounds with magic numbers (`1900 <= year <= 9999`, `831-838`), comma-to-dot amount handling (`amount.replace(",", ".")`, not present in the sibling handlers: Track A).
- `1016-1085` `promote_submit`: `Decimal` parse, positivity, currency exponent.
- Private helpers imported by other routers: `_EMPTY_TERM_INPUT`, `_formula_source_candidates` (`today.py:216`).

### 4.2 `web/routers/plan.py:68` (`plan`, 184 lines, CC E 31)

- `88-94` month/year query parsing; `year` has no bounds. `GET /plan?tab=budget&year=0&month=5` raises `ValueError` from `date.replace` (`132-135`: `today_d.replace(year=year, month=month, ...)`) and returns HTTP 500 (repro `b_router_logic.py`, output in `b_router_logic.out`).
- `96-98` `_shift_month` closure doing month arithmetic.
- `115-178` fiscal-cycle logic: anchor day from the first active monthly rule of the anchor category, `max(1, min(28, rule.day_of_month))`, then recomputation of `committed_minor`, `unbudgeted_committed_minor`, `remaining_minor` and `days_until_next_income` via `dataclasses.replace` on a service result. This rewrites a service's output in the router, so the Budget tab for a non-current month shows numbers that no service test covers.
- `194-222` forecast tab: horizon whitelist, NOW/END/PEAK summary (max over projection).
- `223-250` analytics tab: period whitelist loop, second month-end calculation (`238-239`, duplicates `131-135`).
- `ctx["spend_total_minor"] = sum(...)` and `year_column_totals` / `year_grand_total` sums at `179-193`: aggregation in the router.

### 4.3 `web/routers/ledger.py`

- `140-221` `_hydrate_recurring_rows`: filter chain (`164-178`), override precedence (`180-195`: `override_on_next_due.amount_override` over `formula_amount`) is the same precedence as `recurring_svc.promote_recurring`; two copies (Track A).
- `343-373` `_recurring_summary`: money arithmetic, see B-01.
- `383-390` `_tab_counts`: loads every transaction (`limit=None`) to count them with `len(...)`. Track C (performance); layer-wise it should be a `COUNT(*)` in a service.
- `409-413` `planned_total_minor` sum in the handler.
- `_actual_day_nets` (`260-281`): converts and groups in the router, delegating arithmetic to `services/ledger_totals.py` (this one is correctly split).

### 4.4 `web/routers/planned.py`, `transactions.py`, `accounts.py`, `budget.py`

- `planned.py:112-181` `planned_batch_undo` (raw `UPDATE`, B-03); `220-300` create (transit rules differ from the other two routers: dest may be given for any category, no currency check, no "transit requires dest").
- `transactions.py:238-300` create (no "transit requires dest": B-02); `358-430` update (dest not looked up, not currency-checked, category not looked up at all: it relies on the repository `require_owned` raising `LookupError`, which surfaces as HTTP 500).
- `accounts.py:445-509` reconcile: two separate committed mutations (adjustment, then snapshot) with `contextlib.suppress(NoAdjustmentNeededError)` between (B-07); `category_id` accepted from the form and handed to the service without a direction check (B-02).
- `budget.py:235-300` tier dispatch, month 1-12 check (`_MONTHS_IN_YEAR`), unbounded `year` int for one-off overrides.

## 5. Repository discipline, functional-first and transactions

### 5.1 Mutations (ADR-0019, ADR-0022)

Every `INSERT/UPDATE/DELETE` in `repositories/` goes through `mutate` or an explicit `write_audit` except the following (verified by reading each):

| Helper | Where | Audit | Callers |
|---|---|---|---|
| `recurring.set_next_due` | `repositories/recurring.py:269` | none (docstring: "the orchestrating service writes the paired audit entry") | `services/recurring.py:476,548` (orchestrators; each writes an audit row afterwards) and **`web/routers/recurring.py:522`** (router, no audit) |
| `recurring.set_inactive` | `:294` | none | `services/recurring.py:474,546` |
| `recurring.mark_override_promoted` | `:406` | none; the orchestrator audits the rule, not the override | `services/recurring.py:487` |
| `preferences.upsert` / `delete` | `repositories/preferences.py:43,59` | none (`user_preferences` has no `deleted_at`; ADR-0019 says every mutable table) | `services/preferences.py:56,66` |
| `webauthn.update_sign_count` | `repositories/webauthn.py:155` | none (high frequency counter; defensible) | auth |
| `sessions.*`, `rate_limit.*`, `retention.*` | `repositories/` | none by design (auth/ops tables); `retention.scrub_audit_request_context` rewrites `audit_log` columns on purpose | auth, retention task |
| raw `UPDATE planned_transactions` | **`web/routers/planned.py:155`** | none | router |

Soft-delete reads: every `find_*`/`list_*` on `accounts`, `categories`, `transactions`, `planned_transactions`, `recurring_rules`, `budget_*` appends `AND deleted_at IS NULL` unless `include_deleted`. `recurring_rule_overrides` and `account_snapshots` have no `deleted_at` (hard delete via `delete_override` with audit; snapshots append-only), consistent with ADR-0022 §6. I found no read that returns soft-deleted rows by mistake. Two docstring errors are noted in B-16.
Soft-delete itself is a no-op when the row is already deleted (`transactions.soft_delete` returns early when `find_by_id` is `None`), so a repeated undo does not fail.
Audit forensic columns: domain repositories (`accounts`, `categories`, `transactions`, `planned`, `budgets`, `recurring`, `snapshots`) do not accept a `RequestCtx`, so `audit_log.ip`, `session_id`, `user_agent` are NULL for all domain mutations; only `user_id` / `actor_user_id` are set (`_shared.mutate`). See question Q3.

### 5.2 Functional-first (ADR-0021)

- Non-frozen dataclasses: none (every `@dataclass` has `frozen=True`).
- Stateful classes outside DTO/Protocol: only framework-required ones (`BaseHTTPMiddleware` subclasses in `web/middleware/*.py`, `logging.Filter` in `logging.py:63`). Allowed by necessity; ADR-0021 should say so explicitly.
- Module-level mutable state: `repositories/_shared.py:98 _TX_DEPTH: dict[int, int]` keyed by `id(conn)` (nesting counter for savepoints; entries are removed on exit, but an `id` reused after an unclosed connection could inherit a stale depth, and the dict is process-global across request threads); `web/routers/recurring.py:78 _EMPTY_TERM_INPUT` (shared dict constant, only copied before use); `logging.py:103`, `web/app.py:86` `global` idempotence flags; `lru_cache` on `config.get_settings` and `services/_passwords` (fine).
- Mutation of inputs: AST scan found one: `services/recurring_formula.py:240` writes into the `cache` dict parameter of `_sum_category_in_month` (documented memo, threaded explicitly). No `list.append` on parameters elsewhere.

### 5.3 Transactions

- Reads that gate a write happen **outside** the transaction in `promote_recurring` (`services/recurring.py:396-471`, reads the rule and the override, then `with db_transaction`), `promote_to_actual` (`services/planned.py:149-189`, checks `row.promoted_to_txn_id is not None` at 161, then transacts at 189), and `reconcile` (`derive_balance` then `transactions_repo.create`). With the web server's thread pool, a double submit can pass the guard twice (B-07, probable).
- `reconcile_submit` (`routers/accounts.py:490-500`) commits the adjustment and the snapshot separately.
- `batch_promote_due` for planned reads `due_rows` before opening the transaction (`services/planned.py:221-224`).
- Audit-free helpers outside an orchestrator: `routers/recurring.py:522`.
- ADR-0022 §8 holds: no `commit()`/`rollback()` outside `transaction()`.

## 6. Findings

Class names follow implementation_plan §5.2; B-07 proposes a new class `txn-boundary`, to be documented in `findings.md` in Phase 3.

### B-01 Recurring-tab "Monthly in/out" strip adds amounts of different currencies as if they were PLN

- **Severity:** Critical (per §5.1 "wrong money shown today"; it needs two currencies among active rules. Calibrate in T-Q11 if the operator reads it as High: it is an informational strip, not a total used elsewhere.)
- **Confidence:** Confirmed (`repro/B/b_router_logic.py`, scenario 2: a 100.00 PLN and a 100.00 EUR monthly expense render as "Monthly out 200 PLN").
- **Track / root cause:** B / layer-leak
- **Locations:** `web/routers/ledger.py:343-373` (`_recurring_summary`), consumed at `ledger.py:408`; label hard-coded at `web/templates/ledger/index.html:93-110` (`PLN`, `/ 100.0`).
- **Description:** The router sums `effective_amount_minor` of each rule in its account's own currency, divides by cadence with `//`, and the template prints the result as PLN. Multi-currency is a first-class concept (ADR-0006; accounts own a currency). The same logic exists in services for the forecast/budget with `_convert_native_to_base`/`to_base`, so the router is both wrong and a fourth copy of "monthly equivalent of a rule" (Track A). The `{"monthly": 1, "quarterly": 3, "yearly": 12}.get(cadence_val, 1)` fallback silently treats any unknown cadence as monthly (Track C). `/100.0` assumes exponent 2 (Track C, JPY class).
- **Evidence:** `b_router_logic.out`: `(2) 'Monthly out' strip shows: ('200', 'PLN')`.
- **Impact:** The user sees a monthly commitment figure that is wrong by the FX rate for every non-base-currency rule.
- **Mitigation:** Move the roll-up to `services/ledger_totals.py:recurring_monthly_totals(conn, user_id, rules, base_ccy)` using the existing cached converter (`fx_service.convert_cached`), exponent-aware, with a `None` result on missing rate like `_actual_day_nets`; the router passes the result and the template prints `settings.base_currency`.
- **Alternatives:** none worth listing.
- **Effort:** S
- **Related:** B-04; Track A (monthly-equivalent and FX duplication), Track C (floor division, `/100.0`).

### B-02 Transit-without-destination rows can be persisted; any balance computation for that account then raises (HTTP 500)

- **Severity:** High (data corruption of the user's own data through UI routes; Critical-candidate for T-Q11: recoverable only by soft-deleting the row, and the broken pages are the accounts, today and forecast pages)
- **Confidence:** Confirmed (`repro/B/b_transit_validation.py`, `b_reconcile_transit.py`)
- **Track / root cause:** B / layer-leak (the invariant lives in three router copies instead of in a service or repository)
- **Locations:** `web/routers/transactions.py:263-283` (create: validates a destination only `if dest_account_id and cat.direction == TRANSIT`, so an **empty** destination on a transit category passes), `transactions.py:358-430` (update: no category lookup, no destination lookup/currency check, category may be switched to transit), `web/routers/accounts.py:489-495` with `services/reconciliation.py:62-120` (`category_id` from the form may be a user-defined transit category; `stored_amount = abs(delta)`), `web/routers/planned.py:220-300` (no "transit requires destination"; destination accepted for any category; no currency check), versus the correct copy at `web/routers/recurring.py:149-179`. The consumer that blows up: `services/balance.py:57` (`raise ValueError("transit transaction missing dest_account_id")`).
- **Description:** ADR-0008/validate rules for transit exist in `services/_promotion.validate_promotion` (used by promotion) and in `recurring.py`'s router copy, but plain create/update/reconcile never call them, and neither `transactions_repo.create/update` nor the schema enforces the shape.
- **Evidence:** `b_transit_validation.out`: `(a) POST /transactions transit, no dest -> HTTP 200`, `derive_balance: ValueError: transit transaction missing dest_account_id`, `GET /accounts status afterwards: 500`; same after re-categorising an existing expense row (`(b)`). `b_reconcile_transit.out`: reconcile with a transit category returns 500 after persisting `(5000, None)`.
- **Impact:** One accidental submit makes every page that derives that account's balance return 500 until the offending transaction is deleted.
- **Mitigation:** Add `services/transactions.py` with `create_checked` / `update_checked` that call one `validate_transit_shape(direction, account, dest)` (extracted from `_promotion.validate_promotion`, includes the currency and distinct-account rules), use it from the transactions, planned and recurring routers and from `reconciliation.reconcile` (reject `transit` categories there). Add a repository-level guard in `transactions_repo.create/update` raising on `transit` without `dest_account_id` as the last line of defence.
- **Alternatives:** guard only in `transactions_repo` (smallest change, but form errors become 500/LookupError rather than field errors).
- **Effort:** M
- **Related:** B-04; Track A (three divergent validators), Track C (500 instead of 422 on `LookupError`).

### B-03 Batch-undo endpoints bypass the repository layer, replay "the latest audit row", and do not restore all state

- **Severity:** High (audit-log bypass on a live path plus incorrect restoration)
- **Confidence:** Confirmed (`repro/B/b_undo_replay.py`, three scenarios)
- **Track / root cause:** B / repo-bypass
- **Locations:** `web/routers/planned.py:112-181` (raw `SELECT` at `140`, raw `UPDATE` at `155`), `web/routers/recurring.py:470-545` (raw `SELECT` at `501`, `set_next_due` at `522`).
- **Description:** (1) The planned undo writes `promoted_to_txn_id` with a raw `UPDATE`; no `audit_log` row (ADR-0019/0022 violation). (2) The recurring undo calls the audit-free `set_next_due` from a router, outside any audited orchestrator, so the undo itself leaves no trail. (3) Both pick `prev_json` from "the most recent audit row of the entity" (recurring: no `operation` filter), not from the row written by the batch. Any later edit of the rule gives an undo that restores the wrong state or none. (4) `promote_recurring` may call `set_inactive` (end date reached) and `mark_override_promoted`; the undo restores neither, so an undone final promotion leaves the rule inactive and the override stamped as promoted to a deleted transaction. (5) The ids come from the client form, so any user-owned transaction can be soft-deleted by an arbitrary id list.
- **Evidence:** `b_undo_replay.out`: S1 `next_due` stays `2026-12-10` after undo (txn undone, 0 live); S2 `active after undo: False`; S3 `audit rows before/after undo: 2 2`.
- **Impact:** Undo leaves a recurring rule one period ahead (a missed bill disappears from forecasts) or inactive; history of the planned change is lost.
- **Mitigation:** Delete the SQL from both routers. Add `services/planned.py:undo_batch(conn, user_id, txn_ids, planned_ids)` and `services/recurring.py:undo_batch(...)` that run in one `db_transaction`, soft-delete the transactions, restore planned via `planned_repo.stamp_promotion(..., None)` (audited) and restore rules through `update_rule` with `next_due`, `last_promoted_date` and `active` taken from the specific audit row captured at promote time. Include the previous rule state in the undo payload (the toast already round-trips ids) instead of searching `audit_log`; verify ownership of every id.
- **Alternatives:** keep audit replay but select by `id` stored in the payload (smaller change; payload would carry audit ids).
- **Effort:** M
- **Related:** B-10, B-11; ADR-0019/0022.

### B-04 No service layer for CRUD: 13 routers import repositories, 6 of them write through them

- **Severity:** Medium
- **Confidence:** Confirmed (import-linter dry run, `baseline/import-graph.txt`: 13 router modules, 23 import lines; `web -> repositories` 37 edges)
- **Track / root cause:** B / layer-leak
- **Locations:** writes from routers: `categories.py:109,192,211` (create/update/soft_delete), `accounts.py:225,325,354,377,497` (accounts and snapshots), `transactions.py:295,416,441,453`, `planned.py:269,385,413,427`, `budget.py:256,271,281,341,365,421`, `recurring.py:358,730,761,852,884`; reads in `ledger.py`, `today.py`, `settings.py`, `settings_security.py`, `plan.py`, `auth.py`; private `repositories._shared.transaction` imported at `recurring.py:486`, `planned.py:124`. Also `web/today_data.py:20,112`, `web/deps.py:18-19`.
- **Description:** CLAUDE.md says "Routers call services; services call repositories". Orchestration and validation (B-01, B-02, B-05) landed in the routers because no service exists for accounts, categories, transactions, budget overrides and recurring rule CRUD.
- **Evidence:** import-graph contract "routers must not import repositories BROKEN".
- **Impact:** Each rule is implemented per router, diverges (B-02) and cannot be unit-tested without HTTP.
- **Mitigation:** Introduce one CRUD service per entity (`services/transactions.py`, `planned.py`, `accounts.py`, `recurring_rules.py`, `budget_overrides.py`; `categories.py` exists) that validates and calls the repositories, then turn the contract on with `ignore_imports` for the not-yet-migrated modules and shrink the list per migration PR. Read-only listings may go through thin service re-exports. Do after B-06 (the recurring service shape depends on it).
- **Effort:** L
- **Related:** B-01, B-02, B-03, B-05, B-15; Track A.

### B-05 `plan()` rewrites service results in the router and 500s on out-of-range `year`

- **Severity:** Medium
- **Confidence:** Confirmed for the 500 (`b_router_logic.out`: `GET /plan?tab=budget&year=0&month=5 -> HTTP 500`); Probable for the logic claim (code citation)
- **Track / root cause:** B / layer-leak
- **Locations:** `web/routers/plan.py:68-251` (CC E 31, 184 lines), `96-98` `_shift_month`, `115-178` fiscal override and totals rebuild, `132-135` unbounded `replace(year=...)`, `223-250` second month-end computation.
- **Description:** See section 4.2. The Budget tab for a non-current month shows `committed_minor=0`, `unbudgeted_committed_minor=0`, `remaining_minor` and period dates that the router overwrites on the service's `MonthSummary`, so the service tests do not describe what the user sees. Anchor-day magic numbers `1`, `28`.
- **Impact:** A hand-edited URL gives HTTP 500; a future change to `MonthSummary` can silently desynchronise the picker view from the service.
- **Mitigation:** Move the "non-current month" variant into `services/budget.py:month_summary_for_picker(conn, user_id, year, month, today)` returning the final dataclass; validate `year` (1900-9999) and `month` in one `parse_year_month` helper shared with `budget.py` and `recurring.py:add_override`; split `plan()` into one function per tab.
- **Effort:** M
- **Related:** B-09; Track C (boundaries, clock: `datetime.now(ZoneInfo(...))` here vs `date.today()` elsewhere).

### B-06 Import cycle `repositories.recurring <-> services.recurring <-> services.recurring_formula` causes 9 `PLC0415`

- **Severity:** Medium
- **Confidence:** Confirmed (grimp SCC in `baseline/import-graph.txt`; per-suppression cycle test in table 2.2)
- **Track / root cause:** B / import-cycle
- **Locations:** `repositories/recurring.py:31` (`from services.recurring import first_due_on_or_after`, used at `_compute_initial_next_due`, line 128), `services/recurring.py:635-638` (bottom `E402` re-export of `recurring_formula`), lazy imports at `services/recurring.py:384,408,515,603` and `services/recurring_formula.py:166,167,213,336,392`.
- **Description:** A pure date-schedule function lives in a service module, so the repository depends upward (a broken contract: "repositories must not import services") and the services hide the loop with function-level imports. The `E402` bottom import makes `services.recurring` and `services.recurring_formula` a second two-node cycle.
- **Impact:** Function-level imports hide the dependency from linters and from import-time failures; they cluster 16 of the 37 suppressions and the 17-suppression `services/recurring.py` file.
- **Mitigation:** Extract the pure scheduling code (`generate_occurrences`, `advance_next_due`, `first_due_on_or_after`, `occurrence_in_month`, `_STEP_MONTHS`, `_build_lookup_stub`) into `domain/recurring_schedule.py`; repositories and services import it from there. Have `recurring_formula` import `services.recurring` at top level and drop the bottom re-export (callers import `rt_expand` from `recurring_formula` directly). Then remove the 9 real and the 6 adjacent copied lazy imports, and add the `repositories ↛ services` contract to CI.
- **Effort:** M
- **Related:** B-12, B-04.

### B-07 Compound mutations and their guard reads are not inside one transaction

- **Severity:** Medium (new class `txn-boundary`)
- **Confidence:** Probable (code citations; no race repro attempted, Track C owns concurrency)
- **Track / root cause:** B / txn-boundary
- **Locations:** `services/recurring.py:396-471` (`promote_recurring`: rule and override read, `with db_transaction` at 471), `services/planned.py:149-189` (`promote_to_actual`: `promoted_to_txn_id is not None` check at 161, transaction at 189), `services/planned.py:221-224` (`batch_promote_due`: `due_rows` read before `db_transaction`), `services/reconciliation.py:62-120` (derive balance, then insert), `web/routers/accounts.py:490-500` (reconcile then snapshot as two commits).
- **Description:** The guard and the write are separated, so two concurrent requests can both pass the guard. `stamp_promotion` is unconditional (`WHERE id = ? AND user_id = ?`, no `promoted_to_txn_id IS NULL`), so the second request creates a second transaction and overwrites the link. For reconcile, a transaction inserted between derive and insert makes the adjustment wrong, and the router commits the snapshot separately.
- **Impact:** Duplicate promoted transactions (double click on Promote) and wrong reconciliation deltas under concurrent edits.
- **Mitigation:** Move the guard reads inside `db_transaction` (open with `BEGIN IMMEDIATE` for the promote and reconcile paths so the writer lock is taken before the read), make `stamp_promotion` conditional on `promoted_to_txn_id IS NULL` and raise `AlreadyPromotedError` on zero rows, and add `reconcile_and_snapshot` in the service so both writes share one transaction.
- **Effort:** M
- **Related:** Track C (concurrency), B-03.

### B-08 Eight service signatures have adjacent same-typed positional parameters; the rule is noise on 24 route handlers

- **Severity:** Medium
- **Confidence:** Probable (signatures; no current call site is wrong)
- **Track / root cause:** B / wide-signature
- **Locations:** `services/reconciliation.py:62` (user_id, account_id, actual_balance_minor), `services/budget.py:408` (user_id, year, month), `services/forecast.py:433,530,778`, `services/recurring.py:641`, `services/recurring_formula.py:322`, `services/fx.py:119` (details in table 2.3 rows 25-32); the 24 handler suppressions in `web/routers/*.py` (rows 1-24).
- **Description:** Swapping `account_id` and `actual_balance_minor`, or `from_ccy` and `to_ccy`, type-checks. ADR-0061 §5's "`user_id` is the first positional after `conn`" is kept, which is the part to keep.
- **Impact:** A silent wrong-account adjustment or inverted FX rate after a refactor.
- **Mitigation:** Keep `conn, user_id` positional and make everything after them keyword-only (`*`) in the eight service functions (callers: about 12, all in `src/`), and replace the 24 router `noqa` comments with a `per-file-ignores` entry `"src/budget_planner/web/routers/*.py" = ["PLR0917"]` since FastAPI binds by name.
- **Effort:** S
- **Related:** B-02 (reconcile), Track G (`fx.convert` has no production caller).

### B-09 Two files over 800 lines and 16 router functions of complexity C or worse

- **Severity:** Medium
- **Confidence:** Confirmed (`baseline/sizes.txt`, `radon-cc.txt`, `xenon.txt`)
- **Track / root cause:** B / oversized-module
- **Locations:** `web/routers/recurring.py` (1115; MI B 17.61; 17 suppressions; `Any` count 109), `services/forecast.py` (978), `web/routers/plan.py:68` (E 31), `web/routers/ledger.py:140` (D 29), plus the list in table 2.4.
- **Description:** Both oversized files are the highest-density hot spots for the other findings. The split proposals are in table 2.4.
- **Impact:** Review and test cost; every router-logic defect above sits in these files.
- **Mitigation:** Do the splits in table 2.4 after B-04 (the router shrinks as services appear); introduce xenon at `--max-absolute C` in `just lint` only after the E and D blocks are gone.
- **Effort:** L
- **Related:** B-04, B-05.

### B-10 Audit-free repository helpers are public API; `user_preferences` writes are unaudited

- **Severity:** Medium
- **Confidence:** Confirmed (code citations; one illegal caller, B-03)
- **Track / root cause:** B / repo-bypass
- **Locations:** `repositories/recurring.py:269` (`set_next_due`), `:294` (`set_inactive`), `:406` (`mark_override_promoted`), `repositories/preferences.py:43,59`.
- **Description:** The docstring convention "the orchestrating service writes the paired audit entry" is not enforced. `mark_override_promoted` stamps a mutable table with no audit row at all (the rule gets one, the override does not). ADR-0019 says every mutable table; `user_preferences` is mutable.
- **Impact:** The next caller to use `set_next_due` (the router already does) bypasses the trail without any signal.
- **Mitigation:** Move the three helpers to `repositories/_unaudited.py` (underscore module) and add an architecture test beside `tests/architecture/test_user_id_filter.py` that fails when anything other than `services/recurring.py` imports it. Route `preferences.upsert/delete` through `mutate` with entity type `user_preference`.
- **Effort:** S
- **Related:** B-03.

### B-11 `audit_log` is read without a `user_id` predicate

- **Severity:** Low
- **Confidence:** Probable
- **Track / root cause:** B / scoping-gap
- **Locations:** `web/routers/planned.py:140`, `web/routers/recurring.py:501` (router SQL keyed by `entity_id` only, with `entity_id` taken from client form ids), `repositories/audit.py:30` (`list_entries`) and `:44` (`recent`) (no scoping parameter; the only caller `services/audit_tail.py` is admin-only and redacts other users).
- **Description:** Entity ids are global autoincrement, so a user can name another user's rule id and the router reads that user's `prev_json`. The result is only used to write back to rows filtered by `AND user_id = ?` (a no-op for foreign ids), so no data returns to the caller.
- **Impact:** No leak today; a pattern that breaks the ADR-0061 §5 rule, and `tests/architecture/test_user_id_filter.py` cannot see raw SQL in routers.
- **Mitigation:** Disappears with B-03 (no router SQL). For `repositories/audit.py`, add `user_id` to `list_entries` and keep `recent` explicitly admin-named (`recent_all_users`).
- **Effort:** S
- **Related:** B-03; Track D (scoping).

### B-12 28 unnecessary function-level imports, including router-to-router private imports

- **Severity:** Low
- **Confidence:** Confirmed (table 2.2)
- **Track / root cause:** B / import-cycle (suppression hygiene)
- **Locations:** table 2.2 rows 1-20, 22-24, 27, 28, 30, 31, 37; router-to-router: `planned.py:184`, `transactions.py:195` (`render_table_for` from `ledger`), `today.py:216` (`_EMPTY_TERM_INPUT`, `_formula_source_candidates` from `recurring`).
- **Description:** Stdlib and cycle-free imports sit inside functions. The router-to-router ones show helpers in the wrong module.
- **Mitigation:** Hoist all 28 to module level after B-06; move `render_table_for` to `web/ledger_render.py` and the formula-form helpers to `web/forms/recurring.py`. Drop `PLC0415` from the allowed `noqa` list afterwards so new ones fail review.
- **Effort:** S
- **Related:** B-06.

### B-13 Functional-first deviations are small

- **Severity:** Low
- **Confidence:** Confirmed
- **Track / root cause:** B / layer-leak (style)
- **Locations:** `repositories/_shared.py:98` (`_TX_DEPTH` module-level dict keyed by `id(conn)`), `services/recurring_formula.py:240` (writes to parameter `cache`), `web/routers/recurring.py:78` (`_EMPTY_TERM_INPUT` module-level mutable dict), framework classes in `web/middleware/*.py`.
- **Description:** See section 5.2. No non-frozen dataclass, no hidden service state.
- **Mitigation:** Track transaction depth on a `contextvars.ContextVar` or on the connection wrapper instead of a global keyed by `id(conn)`; make `_EMPTY_TERM_INPUT` a `MappingProxyType`; add one sentence to ADR-0021 allowing framework-mandated classes and an explicit memo-parameter pattern.
- **Effort:** S
- **Related:** none.

### B-14 Two SQL queries in `services/accounts.py` belong in repositories

- **Severity:** Low
- **Confidence:** Confirmed
- **Track / root cause:** B / repo-bypass
- **Locations:** `services/accounts.py:35-53`, `:63-80`.
- **Description:** Both are user-scoped reads. The first omits `a.deleted_at IS NULL` (harmless today, see table 2.1 row 12) and bypasses the repository helpers that the architecture test (`tests/architecture/test_user_id_filter.py`) scans.
- **Mitigation:** Add `snapshots_repo.latest_taken_at_by_account` and `transactions_repo.latest_operation_date_by_account`; the service keeps only `_max_signal` and `last_checked`.
- **Effort:** S
- **Related:** B-04.

### B-15 `web -> db` contract is broken by five modules, one hidden behind a lazy import

- **Severity:** Low
- **Confidence:** Confirmed (`import-graph.txt`: `web/app.py`, `routers/health.py`, `middleware/auth.py`, `deps.py`, `retention_task.py`)
- **Track / root cause:** B / layer-leak
- **Locations:** `web/app.py:59`, `web/routers/health.py:53,64`, `web/deps.py` (connection factory), `web/middleware/auth.py`, `web/retention_task.py:16`.
- **Description:** `deps.get_db`, `app` startup and the retention task are composition-root code and may legitimately touch `db`. `health.py` runs `PRAGMA integrity_check` in a router.
- **Mitigation:** Move the two PRAGMA probes into `db/health.py` (`check_wal_autocheckpoint`, `integrity_check`), and write the contract as "web must not import db except `web.app`, `web.deps`, `web.middleware.auth`, `web.retention_task`".
- **Effort:** S
- **Related:** B-04.

### B-16 Docstrings contradict the code on soft-delete

- **Severity:** Low
- **Confidence:** Confirmed
- **Track / root cause:** doc-drift
- **Locations:** `services/accounts.py:33` ("across non-deleted accounts" but the SQL does not filter), `services/balance.py:65` ("for all live categories" but passes `include_deleted=True`, which is the correct behaviour for historical balances).
- **Mitigation:** Fix both sentences.
- **Effort:** S
- **Related:** B-14.

## 7. Repros

| File | Shows | Output |
|---|---|---|
| `repro/B/b_undo_replay.py` | B-03 (three scenarios) | `b_undo_replay.out` |
| `repro/B/b_transit_validation.py` | B-02 (create and update paths) | `b_transit_validation.out` |
| `repro/B/b_reconcile_transit.py` | B-02 (reconcile path) | `b_reconcile_transit.out` |
| `repro/B/b_router_logic.py` | B-01, B-05 | `b_router_logic.out` |
| `repro/B/_common.py` | shared scaffolding: sets `BUDGET_DATABASE_URL=sqlite:////tmp/audit-B.sqlite` and `BUDGET_ENV=test` before importing the app (`web/app.py:250` builds a module-level `app` with default settings at import), copies `data/demo.sqlite`, migrates the copy | n/a |

Run from the repo root: `PYTHONPATH=src:. python3 docs/plans/quality-audit/repro/B/<script>.py`. Each script recreates `/tmp/audit-B.sqlite` from the demo DB.

## 8. Questions for the operator

1. B-01: is the Recurring strip meant to be in base currency (the label is hard-coded `PLN`)? Do you hold recurring rules in more than one currency today? That decides Critical vs High.
2. B-02: should a user-defined category with `direction=transit` be allowed at all (the seeded `Transit` is a system category)? If not, block it at category creation and the whole reconcile path closes.
3. Audit forensic columns (`ip`, `session_id`, `user_agent`) are NULL for all domain mutations because the repositories take no `RequestCtx` (T-D14 threaded it only through auth/user code). Is that intended (ADR-0122 records only `user_id`)? If not, a request-context plumbing task is needed.
4. B-03: is undo supposed to be a separate audited action ("undone" entry) or a revert that erases the trail? That fixes the mitigation shape.
5. B-04 order: should the recurring service extraction wait for the Sourdough redesign (ADR-0107) because the routers change anyway, or go first?
6. `services/fx.convert` has no production caller (tests only). Dead code for Track G, or reserved for a future non-cached path?
