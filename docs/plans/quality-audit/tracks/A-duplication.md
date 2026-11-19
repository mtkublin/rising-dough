# Track A — Duplicated domain logic (T-Q04)

> Audit commit `AUDIT_SHA` = `9fb18cbca26ef305855efc8fc106d896edc82631`. All `path:line` cites are at that SHA (paths relative to `src/budget_planner/` unless they start with `docs/`).
> Read-only audit. Repro scripts and recorded output: `docs/plans/quality-audit/repro/A/` (`run_all.sh` re-runs all of them on `/tmp/audit-A.sqlite`, a fresh copy of `data/demo.sqlite` migrated to head; `data/budget.sqlite` was never opened).

## TOP — Critical / headline

**A-01 (Critical, conditional on data): the Today "Net worth" card shows native balances of non-2-decimal accounts 100x wrong.** `web/templates/today/index.html:100` renders `row.balance_minor / 100.0`. A JPY account holding 12,345 JPY renders `123.45` on `/today` (reproduced by HTTP render, `repro/A/output/inv_06_currency_exponent.txt`). T-JPY fixed `/accounts` but missed this card. Critical **if the live DB has any JPY/KRW (or ISK, A-09) account**; T-JPY's existence suggests it does. The demo DB has none (all PLN). Operator: please confirm whether prod has such an account; this is the only item where I could not check real data.

Other **confirmed wrong-number defects** reproduced on a multi-currency scratch scenario (the demo DB itself is all-PLN, so every scenario below adds one EUR account/transaction + a cached rate; none of these fire on pure-PLN data): A-02 (analytics ignores FX), A-03 (forecast spent ignores FX), A-04 (forecast double-counts linked recurring occurrences, also on PLN-only data), A-05 (budget "left per day" off-by-one with no income anchor, PLN-only data), A-07 (Net worth excludes non-base accounts while labelled "all accounts").

## 1. Coverage statement

**Read in full:** `domain/money.py`, `domain/fx.py`, `services/{fx,balance,fortune,ledger_totals,budget,analytics,today,income,upcoming,account_planned,forecast,_promotion,export}.py`, `repositories/{fx,_shared}.py`, `repositories/transactions.py` (`list_filtered`), `repositories/budgets.py` (reads), `web/today_data.py`, `web/htmx.py`, `web/routers/{today,plan,forecast}.py`, `web/routers/ledger.py` (L254-491), `web/templating.py` (money filters), `db/migrate.py` (`_backfill_recurring_next_due`).
**Read in part:** `services/recurring.py` (cadence/expansion/override/`expand_unpromoted`/`linked_occurrence_keys`; NOT `promote_recurring`, `skip_and_advance`, `batch_promote_due`), `services/recurring_formula.py` (to L385; not validation/preview), `web/routers/{transactions (L100-300),budget,accounts,planned,recurring}.py` (amount parsing, transit validation, trigger sites only), `web/charts.py` (scale helpers only), `repositories/recurring.py` (`create_rule`), `services/accounts.py` (SQL), templates by grep (all `/ 100`, direction, trigger names), `tests/architecture/test_user_id_filter.py`.
**Plan §3 checklist:** all 11 concepts mapped (section 2). Method: grep for every concept keyword, then diff implementations; 10 differential scripts executed (section 4).
**Skipped / not covered:** auth/users/sessions/webauthn/rate-limit (other tracks); `services/reconciliation.py`, `services/planned.py` (promotion), `services/recurring.py` promotion functions, `web/routers/{accounts,recurring}.py` beyond the cited helpers, `web/static/js` beyond trigger names, `web/charts.py` rendering, all of `tests/` except the scoping test (Track F), `terraform/`, CI. No prod data: every conclusion about "real data" is limited to demo data plus synthetic scenarios.
**Baselines used:** `just ci` baseline only. `pylint duplicate-code` / `jscpd` reports were not on `audit/quality` when I merged; I did not run them (grep + manual diff was sufficient for the domain-logic concepts).

## 2. Concept map

Legend for "differences": R = rounding, D = rate date, M = missing-rate fallback, S = sign, W = window inclusivity, X = soft-delete/archived filter, U = user scoping.

| # | Concept | Implementations (`path:line`) | Behavioural differences | Recommended canonical home |
|---|---|---|---|---|
| 1 | FX conversion + rate lookup | `services/fx.py:119` `convert` (network); `:146` `convert_cached`; `services/forecast.py:221` `_convert_native_to_base` (pre-fetched rate dict); `web/today_data.py:90` `_convert_minor` (pre-fetched rate); `services/budget.py:55` `base_amount_converter` + `:88` `base_txn_converter` (closures over `convert_cached`); `web/routers/ledger.py:273` nested `convert` (over `convert_cached`); rate collection: `forecast.py:204` `_collect_fx_rates` and `today_data.py:119-129` loop | R: all four arithmetic copies identical (HALF_EVEN, `inv_04` 273 samples, 0 divergences). D: budget committed = latest cached on/before **today** (`budget.py:69`, ADR-0095 s2); spent = on/before txn date (`:108`); forecast/today rows = **exact-today** rate via `get_rate` (**network on page render**, `forecast.py:217`, `today_data.py:127`); ledger = txn date. M (`inv_10`): budget -> native amount + log; today_data -> rate 1 (native counted as base); ledger -> `None` day-net; forecast -> `FxUnavailableError` uncaught -> HTTP 500; analytics -> no conversion at all (A-02). Inverse pair never derived (only `from->to`). | `services/fx.py`: one `to_base(conn, amount, on_date, from, base, *, policy)` + one `Converter` factory; the missing-rate policy is an explicit parameter chosen once (A-06) |
| 2 | Minor units parse / format / exponent | `domain/money.py:190` `currency_decimals`, `:198` `to_minor_units` (HALF_UP), `:210` `parse_amount_str`, `:245` `format_money`; `web/templating.py:28-65` three Jinja filters; **bypasses**: `web/routers/today.py:126` float `*100`; `services/forecast.py:956` `/100.0`; `web/routers/plan.py:36`, `web/routers/forecast.py:31` `_MINOR_UNITS_PER_MAJOR=100.0`; 51 template sites `/ 100.0` (inv_06c); router parsers `transactions.py:223`, `planned.py:209`, `accounts.py:171,203,474`, `budget.py:316`, `recurring.py:232,846,1043` | Exponent table only lists JPY/KRW as 0 and nothing as 3 (A-09). Parsers disagree on comma, extra decimals, NaN/Infinity/huge values (A-08). HALF_UP on input vs HALF_EVEN on conversion is deliberate. Hard-coded `/100` ignores exponent (A-01). | `domain/money.py` only: complete exponent table (or `babel`/ISO data), one `parse_money_input(raw, ccy) -> int` with size cap, one Jinja `money_num` used everywhere |
| 3 | Signed amount from `category.direction` | `services/balance.py:42` `signed_legs`; `services/ledger_totals.py:22` `signed_effect`; `services/forecast.py:128` `_signed_events_for_direction`; `forecast.py:751,770` inline INCOME/EXPENSE branches; `services/account_planned.py:74` `_legs`; `web/routers/transactions.py:145` limit-preview inline; `services/analytics.py:202-205` inline; SQL `c.direction IN (...)` in `repositories/transactions.py:98`; templates `web/templates/_partials/components/_amount.html:5-6`, `ledger/_table.html:76,114,177` | S: source legs identical for income/expense/transit (`inv_04a`). Adjustment: balance + ledger_totals count it (pre-signed); forecast + account_planned skip it by design (ADR-0011). Transit: balance/forecast/account_planned give two legs; ledger_totals gives 0 (net-zero by design); analytics ignores it. Pure duplication, no live divergence (A-10). | `domain/transactions.py` (or `domain/direction.py`): `signed_legs(direction, account, dest, amount) -> tuple[(account, signed)]`; everything else derives from it; adjustment policy a flag |
| 4 | Account balance + fortune | `services/balance.py:85` `derive_balance`, `:122` `account_stats`; `services/fortune.py:30` `compute_fortune` (base-currency accounts only); `web/today_data.py:105` `collect_account_rows` (all accounts, converted, rate 1 on miss); `services/forecast.py:546+` day-0 anchor (`derive_balance(as_of=today)`); `services/account_planned.py:130`; oracle SQL in `inv_02` | `derive_balance == SQL oracle` for every demo account (PASS). `compute_fortune.net_base` ignores non-base accounts; `today_data` fortune_base converts them; Today shows the former under the label "all accounts" and drops the latter (computed, unused by any template). Liability: fortune uses `abs(bal)` for liabilities but `+bal` for net. (A-07) | `services/fortune.py`: one `compute_fortune(..., converter)` returning per-currency and converted totals; delete `today_data.collect_account_rows` fortune math |
| 5 | Period / month ranges, "today", left-per-day | month bounds: `budget.py:203`, `analytics.py:84`, `forecast.py:317`, `recurring_formula.py:123`, `account_planned.py:66`, `planned.py:86`; prev/next month: `budget.py:176`, `forecast.py:621`, `plan.py:96`; anchor lookup duplicated: `budget.py:388` `fiscal_month_for` vs `:408` `_resolve_period_start`; left-per-day: `budget.py:551,584`, `today.py:46,98`, template `today/index.html:32`; "today": 8 sites `datetime.now(ZoneInfo(display_tz))` vs 16 `date.today()` (inv_08b list) | W: committed window is half-open `[None,end)`, analytics/spent windows inclusive; **no-anchor fallback end = last day (exclusive) drops the last day** while `account_planned.py:66` uses last day+1 (A-05). Non-current months re-implemented in `plan.py:121-175` (anchor day capped at 28, committed zeroed). Hero recomputes left-per-day in the template in float (A-15). Host-clock vs display-tz "today" (A-13). | new `domain/periods.py` (`month_range`, `shift_month`, `fiscal_window`) + one injected `today(settings)` dependency |
| 6 | Budget tier resolution | `services/budget.py:183` `resolve_budget` (3 repo calls/cell) vs `:603` `yearly_grid` (bulk maps); routers read tiers directly `web/routers/budget.py:99,206`; consumers: `budget.py:486`, `forecast.py:461,696` | Parity PASS on all 2026 cells incl. one-off = 0 (`inv_08a`); soft-delete filtered in repos (`repositories/budgets.py:78-90`). Duplication only (A-20). Category scope differs (archived), see concept 11/A-11. | `services/budget.py`: build `yearly_grid` on top of `resolve_budget` semantics via one pure `pick_tier(one_off, recurring, default)` |
| 7 | Recurring expansion / `next_due` / overrides | generator `services/recurring.py:107,177,222`; runtime wrapper `recurring_formula.py:322` `rt_expand`; consumers (each hand-rolls "rules x overrides x dedup x window"): `budget.py:296-310` committed, `forecast.py:262-283` events, `forecast.py:373-381` overlay committed, `forecast.py:710-770` flow sums, `account_planned.py:106-116`, `income.py:25-93` next anchor, `upcoming.py:74-174`; `next_due` seeding: `recurring.py:309` vs `db/migrate.py:134` vs `repositories/recurring.py:227` | **Linked-row dedup** (`linked_occurrence_keys`) applied in budget/forecast events/flow/account_planned but **not** in `forecast.py:345` overlay helper (A-04). Overdue: budget counts unbounded-start (ADR-0105), forecast drops everything `<= today` (A-12). Window keyed on canonical date by budget/forecast but events placed on `effective_date`. `income.py`/`upcoming.py` look only at `next_due`, others expand the horizon. Formula sources read `list_overrides_all`, others `list_overrides`. (A-17) | `services/recurring.py`: one `pending_occurrences(conn, user, window, *, include_overdue, dedup=True)` returning `Occurrence`s; all consumers map it |
| 8 | Aggregates (`_mean_minor`, totals per category/month) | `budget.py:240` `_mean_minor`; `analytics.py:138` `_mean_minor`; `balance.py:112` `_mean`; `today.py:46` `_div_round_half_even`; `budget.py:584`, `forecast.py:409` inline divisions; per-category sums: `budget.py:228` `_sum_by_category` (converted) vs `analytics.py:123,166` (native) vs `forecast.py:322` (native); router totals `ledger.py:343,409`, `plan.py` | R: all HALF_EVEN, identical. Divisor semantics differ: budget overall avg = active months, this-year = months elapsed, analytics "12-mo avg" always /12 (Q-02). Native vs converted sums: A-02/A-03/A-16. | `services/aggregates.py`: `mean_minor`, `sum_by_category(txns, to_base)`; analytics must take the converter |
| 9 | User scoping | repositories carry `user_id = ?` by hand; enforced by `tests/architecture/test_user_id_filter.py` (scans `repositories/`, `services/`, `web/routers/`); allowlist `.user-id-filter-allowlist`; `repositories/_shared.py:166` `require_owned` for FK links | All reviewed read paths for this track pass `user_id` (`inv_*` use user 1 only; no cross-user data exists in demo, so scoping is verified by reading, not by test). `services/accounts.py:35,63` raw SQL is scoped via JOIN/predicate. `db/` and `web/` outside routers are not scanned by the test (note for Track B/D). No duplication problem beyond the repeated literal; guard exists. | keep `_shared.py` + arch test; add a `scoped_select(table, user_id)` helper only if Track B/D find gaps |
| 10 | Validation (amount > 0, direction, cross-currency transit) | amount: `transactions.py:223`, `planned.py:209`, `accounts.py:171`, `budget.py:316`, `recurring.py:232`/`:846`/`:1043`, `today.py:126`; transit currency match: `services/_promotion.py:55`, `web/routers/transactions.py:274`, `web/routers/recurring.py:174`; zero-amount: `_promotion.py:46` vs routers `<= 0` | A-08. Transit rule exists in 3 places with 3 error messages; only `_promotion` is the service-level guard, the create/update paths rely on router code (service callers could bypass). | `services/` validators (`validate_amount`, `validate_transit`) called by routers and services alike |
| 11 | HTMX trigger names / swap targets | emit: 45 string-literal sites (`routers/{categories,recurring,accounts,transactions,budget,planned}.py`, helper `web/htmx.py:18`); hand-built `HX-Trigger` JSON: `categories.py:231`, `recurring.py:460,533`, `planned.py:102,165`, `accounts.py:358`; listeners: only `ledger/_table.html:22` (`ledger-stale`), `partials/forecast/_view.html:2` (`forecast-stale`), `static/js/bulk-select.js:66-68` | `budget-stale`, `balance-stale`, `today-stale`, `settings-categories-stale` are emitted but nothing listens (A-18). Trigger sets per route differ without a rule (e.g. category create emits `budget-stale` only; transaction create has no `today-stale`/`budget-stale`). | `web/htmx.py`: `Event` constants + `invalidate(response, *domains)` mapping domain -> events once |
| 12 (new) | Category scope ("which categories count") | live-only: `budget.py:475,605`, `forecast.py:686`; include-archived: `forecast.py:447` via `directions_by_cat`, `analytics.py:113,156,188`, `balance.py:69`, `account_planned.py:93` | X: A-11. | `services/categories.py`: `expense_category_ids(conn, user, *, include_archived)` used by all |
| 13 (new) | Date-string parsers in routers | `_parse_date`/`_parse_int`: `transactions.py:55,64`, `planned.py:33`, `recurring.py:40,49`, `ledger.py:44,53` | byte-identical copies; `budget.py:81-86` `int(q.get(...))` unguarded (500 on `?year=x`), whereas `plan.py:80-93` guards | `web/params.py` |

## 3. Findings

Severity per plan §5.1; confidence Confirmed = reproduced by script in `repro/A/`, Probable = code citation only. Effort S/M/L.

### A-01 — Today Net-worth card divides native balances by 100.0 (JPY/KRW/ISK shown 100x too small)
- **Severity / Confidence:** Critical (conditional on a 0-decimal account in live data) / Confirmed (HTTP render)
- **Track / root cause:** A / template-logic, money-arith (duplicate-logic of `money_num`)
- **Location(s):** `web/templates/today/index.html:100` (native `row.balance_minor / 100.0`); same pattern for base-currency amounts in 50 more template sites (`grep '/ 100'`: `plan/_forecast_tab.html:85-88`, `ledger/_table.html:69`, `today/_afford_preview.html:3,5`, `ledger/index.html:98-114`, `today/index.html:32-55,89-93`, `plan/_analytics_bundle.html:17-110`, `plan/_budget_tab.html:6-57`, `plan/_year_tab.html:47-75`, `accounts/index.html:23-39`, `_partials/components/_period_header.html:4-6`, `_heatmap_cell.html:4`, `partials/budget/_override_form.html:56`, `partials/recurring/_formula_preview.html:4`, `partials/recurring/_promote_inline_row.html:38`); Python: `services/forecast.py:956`, `web/routers/plan.py:36,48-56`, `web/routers/forecast.py:31,57`
- **Description:** T-JPY (CHANGELOG 2026-11-06) introduced `money_num` for native amounts but only converted some templates. ADR-0006 says amounts are minor units of the account currency and the base currency can change without migration; templates and chart code hard-code two decimals.
- **Evidence:** `repro/A/output/inv_06_currency_exponent.txt`: JPY account with 12345 minor renders `123.45` on `/today`, `12,345` on `/accounts`.
- **Impact:** wrong balance on the landing page for any JPY/KRW/ISK account; every base-currency figure becomes wrong if `base_currency` is ever set to a non-2-decimal currency.
- **Mitigation:** replace every `/ 100.0` formatting with the `money_num` / `money` filters (base amounts: `base_ccy`), replace the three Python `/100.0` with `from_minor_units(..., base)`; add a lint test that greps templates for `/ 100` (`tests/architecture/`), as a guard.
- **Effort:** M. **Related:** A-09, T-JPY, ADR-0006/0008.

### A-02 — Analytics sums native minor units across currencies (no FX conversion)
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** A / duplicate-logic (T-FIX6 fixed `budget.py` but not its sibling aggregation)
- **Location(s):** `services/analytics.py:123-125` (`_spend_by_category`), `:166-168` (`_twelve_month_averages`), `:197-205` (`_income_vs_expense_monthly`), `:236-243` (`_largest_items`)
- **Description:** ADR-0006 ("all aggregates (fortune, budget, forecast, analytics) are expressed in base currency") and ADR-0095 s6 ("analytics derived from the same transaction lists ... converts") are violated: `t.amount` of a EUR account is added to PLN totals as if it were PLN. The Plan->Analytics screen is labelled in `base_ccy`.
- **Evidence:** `inv_01`: after adding a 100.00 EUR grocery (rate 4.30) budget spent = 85717 and ledger total = 85717, analytics = 52717 (+10000 instead of +43000).
- **Impact:** wrong money on Analytics (spend by category, 12-mo avg, income-vs-expense chart, largest items) for any multi-currency user; also `plan.py` "vs 12-mo avg" deltas.
- **Mitigation:** inject `budget.base_txn_converter` into all four analytics functions (and make `_largest_items` sort on converted amounts); long term via A-14's shared `sum_by_category`.
- **Effort:** S. **Related:** A-03, A-06, ADR-0095.

### A-03 — Forecast budget overlay / monthly planned budget use native `spent` against base-currency budget and committed
- **Severity / Confidence:** High / Confirmed (spent); Probable (overlay placed on account `min(id)` in that account's native currency)
- **Track / root cause:** A / duplicate-logic, money-arith
- **Location(s):** `services/forecast.py:322-342` `_spent_so_far` (raw `r.amount`), used at `:465` and `:699`; `:587` `primary_account_id = min(a.id ...)` receives an amount computed in base currency
- **Description:** `unaccounted = budget - spent - committed` mixes converted `committed` (`:345` via `base_amount_converter`) with unconverted `spent`. ADR-0095 s6/7 explicitly lists "Forecast figures consuming them". The docstring at `:666` ("Budgets are stored in base currency, so no FX conversion is needed") is only half right. The synthetic overlay events are additionally debited to the lowest-id account, whose currency may not be base.
- **Evidence:** `inv_03a`: 100 EUR expense -> `budget spent (base)` 43000 vs `forecast._spent_so_far` 10000.
- **Impact:** forecast spend/residual budget wrong by the FX factor for foreign-currency expenses; end balances drift.
- **Mitigation:** `_spent_so_far` should call `budget._sum_by_category(..., base_txn_converter)` (or the shared aggregate); overlay events should be emitted in base currency against a base-currency pseudo-account row, not `min(id)` account.
- **Effort:** S (spent) / M (overlay account). **Related:** A-02, A-04, ADR-0042/0095.

### A-04 — Forecast overlay helper double-counts recurring occurrences that already have a linked planned row
- **Severity / Confidence:** High / Confirmed (works on PLN-only data)
- **Track / root cause:** A / duplicate-logic
- **Location(s):** `services/forecast.py:345-390` `_committed_future_for_category` (no `linked_occurrence_keys` filter) vs `services/budget.py:277-310`, `forecast.py:262-283`, `:737-770`, `account_planned.py:101-113` (all dedup)
- **Description:** ADR-0087 (amendment): a linked unpromoted planned row represents its occurrence; consumers skip the virtual occurrence. The overlay copy forgot it, so the same bill is counted as planned row + virtual occurrence.
- **Evidence:** `inv_03b`: rule 22 (1530) + linked planned row -> budget committed 1530, forecast committed 3060.
- **Impact:** overlay `unaccounted` and monthly `planned_budget` are understated by the duplicated bill (forecast too optimistic about remaining budget, hence end balances overstated... or understated depending on clamp) for every re-dated recurring occurrence.
- **Mitigation:** make `_committed_future_for_category` call `budget._committed_by_category(..., category filter)` (the single copy with dedup + FX), deleting the second implementation.
- **Effort:** S. **Related:** A-17, ADR-0087, ADR-0085.

### A-05 — No-anchor fallback drops the last day of the month and under-counts the left-per-day divisor
- **Severity / Confidence:** High / Confirmed (demo data, no FX needed)
- **Track / root cause:** A / duplicate-logic (inclusive vs exclusive end convention differs between two implementations of "period end")
- **Location(s):** `services/budget.py:364-385` `_resolve_anchor` (returns last day), `:546` `end_of_month`, `:551` `days_until_next_income = (next_income_date - today).days`, `:566` `end=next_income_date` (exclusive in `_committed_by_category`, `:279`); contrast `services/account_planned.py:66` (`+ _ONE_DAY`)
- **Description:** With an income anchor the "next income date" is exclusive (money lands that day). The fallback reuses the same variable with the *inclusive* last day of month, so (a) an unpromoted expense dated on the last day is not committed, (b) days remaining is one too few (Nov 19 -> 11 instead of 12), inflating left-per-day by ~9%. `account_planned` counts the same item.
- **Evidence:** `inv_07`: item on Nov 29 counted by both; item on Nov 30: budget delta 0, account_planned -5000; divisor 11 vs inclusive 12.
- **Impact:** the Today hero "left per day" and Budget totals are wrong for users with no anchor configured (also during the month of the last paycheck lookup miss).
- **Mitigation:** `_resolve_anchor` fallback returns `last_day + 1` (first of next month), shared with `account_planned.resolve_window` through one `fiscal_window` helper.
- **Effort:** S. **Related:** A-14, ADR-0041/0064/0085.

### A-06 — Four FX arithmetic copies and five missing-rate policies; forecast raises uncaught, today does network I/O on render
- **Severity / Confidence:** High / Confirmed (`inv_10`, `inv_04b`)
- **Track / root cause:** A / duplicate-logic, silent-fallback
- **Location(s):** `services/fx.py:119,146`; `services/forecast.py:204-240`; `web/today_data.py:90-135`; `services/budget.py:55-116`; `web/routers/ledger.py:273-283`; callers without handler: `web/routers/forecast.py:48`, `web/routers/plan.py` forecast tab via `forecast.py:932`
- **Description:** The arithmetic copies agree today (273 grid samples). The policies do not: budget returns the native amount, today_data uses rate 1 (and counts it as base in fortune), ledger returns `None`, forecast raises `FxUnavailableError` (HTTP 500 on `/forecast` and Plan->Forecast when a non-base account has no cached rate and the API is down), analytics does not convert (A-02). ADR-0095 s2 says page renders never touch the network; `forecast.py:217`/`today_data.py:127` call `get_rate` (5 s timeout per currency, `today_data.py:123` opens a client in a render path).
- **Evidence:** `output/inv_10_missing_rate_fallbacks.txt`.
- **Impact:** a transient FX outage turns two pages into 500s and silently mis-states others; the same missing rate shows three different numbers.
- **Mitigation:** one `Converter` object in `services/fx.py` built per request (`cached`, no network; background job refreshes rates) with a single documented degrade policy (flag the figure as "native/unconverted" instead of silently summing); delete `_convert_native_to_base`, `_convert_minor`, the ledger nested converter.
- **Effort:** M. **Related:** A-02, A-03, A-07, ADR-0006/0095.

### A-07 — Net worth is computed twice; the displayed one drops non-base accounts but is labelled "all accounts"
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** A / duplicate-logic
- **Location(s):** `services/fortune.py:30-51` (base only: `assets_base = assets_by_ccy.get(base)`), `web/today_data.py:105-143` (converted `fortune_base`), `web/routers/today.py:55-58,81`, `web/templates/today/index.html:87-93`, `web/templates/accounts/index.html:23-26,39`, `web/routers/accounts.py:110-118`
- **Description:** ADR-0089 documents the *Planned* hero and ADR-0024 the Assets/Liabilities hero as base-only; yet Today labels it "Net worth · all accounts" and Accounts states "No FX conversions needed today". Meanwhile the Today route computes the converted figure and passes `fortune_base` to the template, which never renders it. Forecast day-0 total uses the converted figure.
- **Evidence:** `inv_02` run B: +1000.00 EUR account -> `fortune.net_base` 3443969 (unchanged), `today_data.fortune_base` and forecast day-0 3873969.
- **Impact:** net worth silently excludes every non-base account; forecast starts from a different number than the headline.
- **Mitigation:** make `compute_fortune` return converted totals (per A-06 converter) plus per-currency breakdown, render the converted net worth, delete `collect_account_rows`' fortune math and the unused template variable; update ADR-0024/0089 text.
- **Effort:** M. **Related:** A-06, ADR-0024, ADR-0089.

### A-08 — Seven independent amount parsers disagree; several 500 on NaN/Infinity/1e400/oversized input
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** A / duplicate-logic (also overlaps Track C/D input handling)
- **Location(s):** `domain/money.py:210` (canonical, used only by `web/routers/transactions.py:139,228`); copies: `web/routers/planned.py:209-216`, `accounts.py:171-182,203-206,474-477`, `budget.py:316-324,251-254,337-340`, `recurring.py:232-239,846-851,1043-1050`, `today.py:126-141`
- **Description:** Only `parse_amount_str` normalises `,`, caps fraction digits and rejects non-finite values. The others use bare `Decimal(...)`: `NaN`/`Infinity` raise `InvalidOperation` at the `<= 0` comparison or in `to_minor_units` (uncaught -> 500); `12.345` is silently rounded to 12.35 (planned, accounts, budget); `12,34` is rejected; today's afford input uses `float` and hard-coded `*100` (JPY `12.34` -> 1234 minor); `1e400` crashes every parser including the canonical one (`quantize` overflow); 99999999999999999999 is accepted and exceeds SQLite int64.
- **Evidence:** `output/inv_05_amount_validation_parity.txt` (11 PLN / 10 JPY inputs disagree).
- **Impact:** inconsistent behaviour per form, authenticated-user 500s, wrong afford preview for 0-decimal currencies, potential overflow on insert.
- **Mitigation:** one `domain.money.parse_amount_str` hardened (finite, `abs(minor) <= 10**15`, handles `e` notation) wrapped by a single `services.validate_amount(raw, ccy, *, allow_zero=False)`; all routers call it; delete the six copies.
- **Effort:** M. **Related:** A-01, A-09.

### A-09 — Currency exponent table lists only JPY/KRW; 21 accepted ISO codes mis-scaled (ISK is FX-reachable)
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** A / money-arith
- **Location(s):** `domain/money.py:14-23` (`_CURRENCY_DECIMALS`), `:30-187` (accepted list), `:195`
- **Description:** BIF CLP DJF GNF ISK KMF PYG RWF UGX VND VUV XAF XOF XPF are 0-decimal and BHD IQD JOD KWD LYD OMR TND are 3-decimal in ISO 4217, but default to 2. Service validation accepts any 3-letter code (`accounts.py:197-200`). ISK is in the frankfurter set, so rates can be fetched.
- **Evidence:** `output/inv_06_currency_exponent.txt` 6a.
- **Impact:** amounts entered/displayed/converted 100x or 10x off for those currencies.
- **Mitigation:** complete the table from ISO 4217 data (static dict generated once, tested against the ISO list in `tests/unit/domain/test_money.py`); reject accounts whose currency has no known exponent.
- **Effort:** S. **Related:** A-01.

### A-10 — Direction-to-sign logic exists in six hand-written copies
- **Severity / Confidence:** Medium / Confirmed (agree today, `inv_04a`)
- **Track / root cause:** A / duplicate-logic
- **Location(s):** `services/balance.py:42`, `services/ledger_totals.py:22`, `services/forecast.py:128,751,770`, `services/account_planned.py:74`, `web/routers/transactions.py:145-150`, `services/analytics.py:202-205`; templates `_partials/components/_amount.html:5-6`
- **Description:** ADR-0008 is the single rule, implemented per call site; adjustment handling differs by design (counted by balance/ledger, skipped by planned/forecast) and by accident-prone default branches (`transactions.py:149` `else: delta = amount_minor` also covers future enum values).
- **Impact:** any new direction or sign rule change must be applied six times (latent High per rubric, kept Medium because they agree now).
- **Mitigation:** one `domain` function (see concept 3) returning legs; the others are one-line adapters; exhaustive `match` with `assert_never`.
- **Effort:** M. **Related:** ADR-0008/0011.

### A-11 — "Which categories count" differs: forecast daily overlay includes archived categories with budgets, everything else excludes them
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** A / duplicate-logic
- **Location(s):** `services/forecast.py:581` (`directions_by_cat` built `include_deleted=True`) -> `:447` expense ids; vs `:686` (`include_deleted=False`), `services/budget.py:475,605`
- **Description:** An archived expense category that still has a default budget adds its budget to the daily forecast overlay but not to the monthly table or the Budget page.
- **Evidence:** `output/inv_09_archived_category_scope.txt`: effect on overlay 100000, on monthly 0.
- **Impact:** daily forecast series and monthly forecast table (same page) disagree; archived categories keep reserving budget.
- **Mitigation:** `expense_category_ids(include_archived=False)` helper for budget-driven paths; archived categories excluded from overlay.
- **Effort:** S. **Related:** A-17.

### A-12 — Overdue unpromoted items: budget counts them, forecast stream silently drops them
- **Severity / Confidence:** Medium / Confirmed (divergence); intent unknown (ADR-0105 only mentions budget)
- **Track / root cause:** A / duplicate-logic
- **Location(s):** `services/budget.py:279-310` (`start=None`), `services/forecast.py:254` (`event_start = today + 1`), `:262-283`
- **Evidence:** `inv_03c`: overdue 5000 planned expense counted by budget, absent from the forecast event stream.
- **Impact:** forecast end balance ignores money the budget says is committed; the monthly fiscal row (from `month_summary`) includes it, the daily series does not.
- **Mitigation:** explicit `include_overdue` parameter on the shared `pending_occurrences` (A-17); forecast passes True and places overdue items on `today + 1`.
- **Effort:** S. **Related:** ADR-0105, A-17, Q-01.

### A-13 — Two notions of "today": display-timezone date (8 sites) vs host-clock `date.today()` (16 sites)
- **Severity / Confidence:** Medium / Probable (prod host TZ not verified; arithmetic demonstrated in `inv_08b`)
- **Track / root cause:** A / clock (cross-ref Track C)
- **Location(s):** tz-aware: `web/routers/today.py:48,109,160`, `plan.py:76,272`, `budget.py:126,156,183`; host clock: `db/migrate.py:155`, `repositories/recurring.py:227`, `services/balance.py:210`, `services/budget.py:69`, `services/planned.py:86`, `web/routers/{accounts.py:46,budget.py:81,forecast.py:48,ledger.py:292,planned.py:80,recurring.py:338,353,435,580,694}`, `web/today_data.py:123`
- **Description:** ADR-0007 defines display TZ Europe/Warsaw. On a UTC host between 00:00 and 01:00/02:00 Warsaw, `/today` and `/plan` say day N+1 while `/forecast`, `/budget`, the FX rate date in `today_data` and `base_amount_converter`'s default say day N, so the same wall-clock instant yields different left-per-day/forecast rows.
- **Evidence:** `output/inv_08_tier_resolution_and_clock.txt`.
- **Mitigation:** one `today(settings)` FastAPI dependency; services never call `date.today()`; ruff `DTZ011` suppressions removed.
- **Effort:** M. **Related:** Track C, ADR-0007.

### A-14 — Month/period helpers and means copied 4-6 times; plan router re-implements the budget period for non-current months
- **Severity / Confidence:** Medium / Confirmed (code)
- **Track / root cause:** A / duplicate-logic, layer-leak
- **Location(s):** month bounds `services/budget.py:203`, `analytics.py:84`, `forecast.py:317`, `recurring_formula.py:123`; shift `budget.py:176`, `forecast.py:621`, `web/routers/plan.py:96`; means `budget.py:240`, `analytics.py:138`, `balance.py:112`, `today.py:46`; anchor query twin `budget.py:388-405` vs `:408-436`; router logic `web/routers/plan.py:111-175` (anchor day clamped to 28 although recurring uses true EOM clamp, `recurring.py:82`)
- **Impact:** drift risk (A-05 is an instance); Plan-month picker shows different period bounds than the Today/Budget page for anchors on day 29-31.
- **Mitigation:** `domain/periods.py` + `services/aggregates.py` (see map); move plan.py's non-current-month math into `budget.month_summary(mode="calendar")`.
- **Effort:** M.

### A-15 — Today hero recomputes "left per day" in the template (float) instead of using `summary.left_daily_spend_minor`
- **Severity / Confidence:** Medium / Probable
- **Track / root cause:** A / template-logic
- **Location(s):** `web/templates/today/index.html:32` vs `services/budget.py:584-587`, `services/today.py:97-98`
- **Description:** template: `(remaining/100.0)/(days_left or 1)` in float, negative remaining shown negative, zero-budget months show a figure; service: HALF_EVEN integer minor, `None` for zero budget; afford clamps remaining at 0. Three results for the same question.
- **Mitigation:** render `summary.left_daily_spend_minor`; afford uses the same clamp policy decided once.
- **Effort:** S.

### A-16 — Router/template aggregates sum native amounts across currencies (and label them PLN)
- **Severity / Confidence:** Medium / Probable
- **Track / root cause:** A / duplicate-logic, layer-leak
- **Location(s):** `web/routers/ledger.py:343-376` `_recurring_summary`, `:409-413` `planned_total_minor`; `web/templates/ledger/index.html:98-114` (literal "PLN"); `services/recurring_formula.py:191-243` formula source sums
- **Impact:** wrong totals with a foreign-currency planned/recurring row; formula amounts derived from rules in different currencies add raw minor units.
- **Mitigation:** move both totals into a service using the shared converter; formula sums convert source rules to the rule's account currency.
- **Effort:** M. **Related:** A-06.

### A-17 — Seven hand-rolled "rules x overrides x dedup x window" loops
- **Severity / Confidence:** Medium / Confirmed (structure; consequences in A-04, A-11, A-12)
- **Track / root cause:** A / duplicate-logic
- **Location(s):** `budget.py:296-310`, `forecast.py:262-283,373-381,737-770`, `account_planned.py:106-116`, `income.py:25-93`, `upcoming.py:74-174`, `recurring_formula.py:146-190` (uses `list_overrides_all`)
- **Mitigation:** one `pending_occurrences()` in `services/recurring.py` (see map). **Effort:** L.

### A-18 — HTMX invalidation events: 45 string literals, four events with no listener, inconsistent trigger sets
- **Severity / Confidence:** Low / Confirmed
- **Track / root cause:** A / htmx-contract
- **Location(s):** emit sites in map concept 11; listeners `ledger/_table.html:22`, `partials/forecast/_view.html:2`, `static/js/bulk-select.js:66-68`
- **Description:** `budget-stale`, `balance-stale`, `today-stale`, `settings-categories-stale` are emitted but unreferenced; pages instead rely on `refresh_unless_on` full reloads.
- **Mitigation:** `web/htmx.py` constants + `invalidate(resp, *domains)`; remove dead events or add listeners. **Effort:** S.

### A-19 — `_parse_date` / `_parse_int` copied in four routers; `budget._year_month` int() unguarded
- **Severity / Confidence:** Low / Confirmed
- **Location(s):** concept 13; `web/routers/budget.py:81-86` (`?year=abc` -> ValueError -> 500, vs guarded `plan.py:80-93`).
- **Mitigation:** `web/params.py` shared parsers. **Effort:** S.

### A-20 — Budget tier resolution has two implementations plus router reads (parity holds today)
- **Severity / Confidence:** Low / Confirmed (`inv_08a` PASS)
- **Location(s):** `services/budget.py:183`, `:603`; `web/routers/budget.py:99,206`
- **Mitigation:** one pure `pick_tier`. **Effort:** S.

### A-21 — `next_due` seeding logic copied in the migration hook and the repository
- **Severity / Confidence:** Low / Probable
- **Location(s):** `services/recurring.py:309`, `db/migrate.py:134-212`, `repositories/recurring.py:227` (`date.today()` inside a repository)
- **Mitigation:** hook calls `first_due_on_or_after`; repository takes `today` as a parameter. **Effort:** S.

### A-22 — Receiving screens use three different "monthly average" definitions
- **Severity / Confidence:** Low / Probable
- **Location(s):** `services/budget.py:515-523` (overall: active months; this year: months elapsed), `services/analytics.py:152` (always /12)
- **Mitigation:** decide/ document one definition; see Q-02. **Effort:** S.

## 4. Differential invariants (all executed)

Scripts and recorded output in `docs/plans/quality-audit/repro/A/` (`harness.py` copies demo.sqlite to `/tmp/audit-A.sqlite`, migrates it, refuses any other DB path). Demo data contains only PLN accounts, so "run B" adds one EUR account/transaction/rate.

| ID | Invariant | Script | Result | Finding |
|---|---|---|---|---|
| INV-1a | budget spent(C,M) == ledger total == analytics(C,M), PLN demo (Oct 2026, Groceries) | `inv_01` | PASS (42717 all three) | - |
| INV-1b | same with one 100.00 EUR expense | `inv_01` | **FAIL** budget 85717, ledger 85717, analytics 52717 | A-02 |
| INV-2a | `derive_balance` == independent SQL oracle, every account | `inv_02` | PASS | - |
| INV-2b | `compute_fortune.net_base` == `today_data.fortune_base` == forecast day-0 (PLN) | `inv_02` | PASS (3443969) | - |
| INV-2c | same with a 1000.00 EUR account | `inv_02` | **FAIL** 3443969 vs 3873969 (day-0 = 3873969) | A-07 |
| INV-3a | budget spent == forecast spent | `inv_03` | **FAIL** 43000 vs 10000 | A-03 |
| INV-3b | budget committed == forecast committed with a linked planned row | `inv_03` | **FAIL** 1530 vs 3060 (equal before linking) | A-04 |
| INV-3c | overdue planned item counted by budget is in the forecast stream | `inv_03` | **FAIL** | A-12 |
| INV-4a | source-leg sign identical across balance / forecast / account_planned for every Direction | `inv_04` | PASS (adjustment asymmetry by design) | A-10 (latent) |
| INV-4b | 4 FX arithmetic copies agree on 273 samples (EUR/JPY/PLN, half-way cases) | `inv_04` | PASS | A-06 (latent) |
| INV-5 | all amount parsers give the same verdict (PLN, JPY, 12 inputs) | `inv_05` | **FAIL** 11 / 10 inputs disagree, crashes on NaN/Infinity/1e400 | A-08 |
| INV-6a | exponent table == ISO 4217 for accepted codes | `inv_06` | **FAIL** 21 codes wrong, ISK FX-reachable | A-09 |
| INV-6b | `/today` renders a 12,345 JPY balance as 12,345 | `inv_06` | **FAIL** renders 123.45 | A-01 |
| INV-7 | budget committed and account_planned count the same last-day item; divisor == days remaining | `inv_07` | **FAIL** (Nov 30 item: 0 vs -5000; divisor 11 vs 12) | A-05 |
| INV-8a | `resolve_budget` == `yearly_grid` for every category x month (incl. one-off 0) | `inv_08` | PASS | A-20 (latent) |
| INV-8b | display-tz today == host-clock today at 23:30 UTC | `inv_08` | **FAIL** by construction (Nov 20 vs Nov 19) | A-13 |
| INV-9 | archived category budget affects daily and monthly forecast equally | `inv_09` | **FAIL** 100000 vs 0 | A-11 |
| INV-10 | one missing FX rate degrades identically in budget / today / forecast | `inv_10` | **FAIL** native amount / rate 1 / 500 | A-06 |

Not run (no ground truth or out of reach): cross-user scoping invariants (demo has one user); budget `remaining` vs `forecast` fiscal-row identity with real recurring formulas.

## 5. Questions (for Phase 3 / operator)

- **Q-01** Is forecast ignoring overdue items intentional (ADR-0105 covers only the budget)? If yes, A-12 reduces to a documentation gap.
- **Q-02** Are the three "average per month" definitions (A-22) intentional per ADR-0056/0041? Not verified against the mockups.
- **Q-03** Does prod contain any non-base, JPY/KRW or ISK account (decides A-01 Critical vs High, and A-02/03/07 real-data impact)? Needs an operator-side read; I did not open prod.
- **Q-04** What is the prod container timezone (A-13)? `deploy/` not inspected by this track.
- **Q-05** `services/recurring_formula.py:191-243` sums source *rules'* amounts across accounts; is mixed-currency formula input possible in practice (formula validation not read)?
- **Q-06** `web/routers/accounts.py` card/reconcile helpers and `services/reconciliation.py` were not read; they may hold further balance arithmetic copies.
- **Q-07** `forecast._distribute_overlay` (`:394-431`) and `today.afford` both implement "spread/divide with residual"; I did not test negative or tiny inputs.
