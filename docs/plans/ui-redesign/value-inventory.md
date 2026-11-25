# Handoff value inventory and data gaps (T-UR34a)

Docs-only discovery for T-UR34 (ADR-0147 §3, §4; ADR-0148). Source: `docs/design/rising-dough-frontend/` (vendored handoff, base `21ccd21a`, frozen date 2026-10-31). Producers are read from `src/budget_planner/` as of that base.

## 1. Method and legend

- **Scope per page:** every displayed value in the page's own content: visible text that carries data (amounts, dates, names, counts, status words that depend on data) and the value attributes ADR-0147 §4 allows: `aria-label`, `title`, `value`, `datetime`, `aria-keyshortcuts`, `data-digits`, `data-marks`, `data-signs` (plus `aria-valuenow`/`aria-valuetext` where a page carries them). Static copy (headings, button labels, column heads) is skipped unless it embeds data. The shell (nav, tab bar, command palette, cheatsheet, flash/toast roots) is identical on every page and inventoried once in 2.0.
- **Overlay pages** (`pages/overlays/*`) show a dialog on top of a base page; only the dialog's own values are listed (the page behind carries the base page's values, section 2.x).
- **Producer** column: `module.function` / `ViewModel.field` / template context key in `src/budget_planner/`. `missing` = no producer today (feeds section 4). `partial` = a producer exists but lacks the exact value or format (named in the note). `T-URxx` = produced by an in-flight Phase P item (not a T-UR34 gap).
- **Rendered by the template** means no arithmetic in the template: a value the handoff prints that today is only derivable by template math counts as `missing` (CLAUDE.md "Thin web", G9).
- Amount/date formatting (`money_num`, `date_day_month`, `dt_local`) is the existing filter set in `web/templating.py`; only the underlying value is inventoried.
- Seed note for T-UR00a/T-UR00b: figures below are the handoff's; internal inconsistencies are in section 5 (overlay candidates).

### Coverage (derived from the handoff tree)

| Group | Files | States inventoried | Section |
|---|---|---|---|
| Today (`pages/today*.html`) | 6 | today, empty, loading, flash, afford-over, afford-invalid | 2.1 |
| Accounts | 2 | accounts, accounts--empty | 2.2 |
| Ledger | 9 | actual, actual--long, --empty, --no-matches, planned, planned--empty, recurring, recurring--empty, recently-deleted | 2.3 |
| Plan | 4 | budget, year, forecast, analytics | 2.4 |
| Settings | 6 | categories, currency-fx, preferences, security, security--error, users | 2.5 |
| Auth | 12 | login(+error), register(+error), invite(+used, expired, invalid), reauth(+error), force-password(+error) | 2.6 |
| Errors | 5 | 404, 409, 422, 500, offline | 2.7 |
| Overlays | 62 | all 62 (dialog-only values) | 2.8 |
| Charts | 5 specimens + index | forecast, income-vs-expense, sparkline, spend-by-category, year-grid | 2.9 |
| `components.html`, `index.html` | 2 | specimen / link index: sample data only, no producer (not inventoried) | none |

Total pages and states inventoried: **106 page files** (8 + 12 + 5 + 9 + 62 + 4 + 6) plus 5 chart specimens. Nothing is "not yet inventoried"; the few values whose semantics the handoff leaves open are flagged "confirm" in section 4.

## 2. Per page and state

### 2.0 Shell (every page)

| Value | Producer | Status |
|---|---|---|
| `aria-keyshortcuts` on nav links (`g o`, `g l`, ...) and the visible key labels in the palette and cheatsheet | `web/templates/partials/_nav.html`, `_palette.html`, `_cheatsheet.html` (static markup; ADR-0147 §5 sets `g t`) | static; Today key is an overlay row (section 5) |
| Header "signed in as" / user name | `web.deps.current_user_id` + auth user (`auth_deps`) | exists |
| Tab bar active state, `@value=1` hidden form values (CSRF) | `web/csrf_token.py` | exists |

### 2.1 Today

Base: `pages/today.html`. Router `web/routers/today.py` `today()`; data `web/today_data.py`, `web/view_models.py`.

| Value (handoff) | Producer today | Status |
|---|---|---|
| Hero figure `199.99` PLN / day | `BudgetView.left_per_day_minor` (`view_models.budget_view`, `view_models.left_per_day`) | exists |
| `data-digits=5`, `data-marks=1`, `data-signs=0` on the hero figure | none (README: "one small Jinja filter computes them") | missing (G10) |
| "● on track" pace tag | `today_data.pace_tag` -> `PaceTag.kind/label` | exists |
| "7 days until next income (Salary, 7 nov)" / phone variant "7 days until salary (7 nov)" | `MonthSummary.days_until_next_income`, `.anchor_category_name`, `.next_income_date` (via `BudgetView.summary`) | exists (both copies from the same fields) |
| "PERIOD · 7 OCT → 7 NOV · DAY 25 OF 31" | `MonthSummary.period_start`, `.next_income_date`, `BudgetView.period_day`, `.period_total_days` | exists |
| Bar `aria-label` "78 percent spent, 15 percent left" and block cells | `BudgetView.spent_pct`, `.committed_pct` (floored by `domain.money.percent_of`); `progress_bar` macro emits `aria-valuenow` only | partial: no `left_pct`, no cell count, rounding differs (G10; section 5) |
| spent `5,014.55`, committed `34.60`, left `1,399.93`, of `6,449.08` | `MonthTotals.spent_minor`, `.committed_minor`, `.remaining_minor`, `.budgeted_minor` (`BudgetView.summary.totals`) | exists |
| Can-I-afford input `@value=250.00` (and `1,800.00` in afford-over) | request query `amount` (`web.params.positive_amount`) | exists |
| "per day becomes 164.28" and "(↓ 35.71)" | `AffordResult.per_day_minor`, `.delta_minor` (`services.today.afford`) | exists |
| afford-over: "per day becomes −14.20 · 114.20 over" | `AffordResult.per_day_minor` is clamped at 0; no "over" amount | missing (G4; semantics confirmed 2026-11-23, ADR-0151) |
| afford-invalid: "Enter an amount, like 250.00" | router returns bare `422 "invalid amount"` | missing (G4) |
| NET WORTH `34,439.69`; assets `36,895.43`; liabilities `−2,455.74` | `fortune_service.compute_fortune` -> `.net_base`, `.assets_base`, `.liabilities_base` | exists |
| "all 10 accounts →" | `account_rows|length` (`today_data.collect_account_rows`) | exists |
| Upcoming range pills 7/30/all | `today_data.window_from` -> `window_label` | exists |
| Overdue group "▲ OVERDUE · 1", "● DUE TODAY · 1", "NEXT 30 DAYS" | `UpcomingItem.is_overdue`, `.is_due_today` (`view_models.upcoming_view`) | partial: group counts need template counting (G10 `UpcomingView` counts) |
| Row: date `28 OCT`, description, "· Checking", category pill, "▲ overdue 3 days", amount `−412.00` PLN | `UpcomingRow.operation_date/description/amount_minor`, `UpcomingItem.account/.category/.is_overdue`; "3 days" = template `today - date` | partial: overdue/due-in day count missing (G2 `days_delta`, shared helper) |
| Row action labels "Annual insurance · −412.00 PLN", "28 OCT · Checking" (`aria-label`/`title` of the row menu) | same fields | exists |
| "showing 6 of 23 · open in ledger →" | `UpcomingView.total_count`, `.cap`, `.has_more` | exists |
| "promote all due" (visible when due rows exist) | `today_data.list_upcoming` rows with `is_overdue`/`is_due_today` | exists |
| States: **empty** (no upcoming, no accounts), **loading** (skeleton fragment), **flash** (`● Saved · Takeaway −35.50 PLN`, error flash with retry), **afford-over**, **afford-invalid** | flash text from `web/htmx.toast_payload` / `form_responses`; empty/loading are template states | exists (flash amount from the saved txn) |

### 2.2 Accounts

Router `web/routers/accounts.py`; data `web/accounts_data.py`, `web/accounts_view.py`.

| Value | Producer | Status |
|---|---|---|
| Hero net worth `34,439.69`, `data-digits=7`, `data-marks=2`, `data-signs=0` | `fortune.compute_fortune.net_base`; digits attrs none | exists / missing (G10) |
| "10 accounts" (hero and section head) | `accounts_service.list_all` length | exists |
| "assets 36,895.43 · liabilities −2,455.74" | `FortuneTotals.assets_base/.liabilities_base` | exists |
| "planned −312.54" | `AccountsPlanned.base_net_minor` (`planned_service.compute_accounts_planned`) | exists |
| Row: name, type (`investment`, `bank`, `credit card · liability`) | `Account.name`, `.type`, `.is_liability` | exists |
| "· checked 01 APR" | `accounts_service.last_checked` -> `LastCheckedRow.last_checked_at` | exists |
| TXNS `84` | `balance_service.account_stats` (`AccountStats`, txn count) | exists |
| BALANCE `16,991.29` PLN (native per row; `−6,601.15` for the EUR account shown in PLN) | `balance_service.derive_balances`; base conversion `fx.FxConverter.to_base` | exists |
| "→ 3,662.52 after planned" | `AccountPlanned` in `AccountsPlanned.by_account` | exists |
| Sparkline `<polyline points=…>` | `balance.sparkline_points` via `accounts_view.sparkline_fields` | exists (handoff geometry is one fixed polyline, section 5) |
| Credit card: "used 16% · available 12,521.63 of 14,977.37", bar `aria-label` "16 percent spent, 80 percent left" | `accounts_view.credit_utilisation` -> `CreditUtilisation.used_pct`, `.available_minor`, `.limit_minor` | exists; left% and cells partial (G10; section 5) |
| Row menu `aria-label`/`title`: "Investments A · 16,991.29 PLN" | `Account.name`, balance | exists |
| **accounts--empty**: header still shows `34,439.69`, "10 accounts" with an empty list | none (inconsistent board) | overlay candidate (section 5) |

### 2.3 Ledger

Router `web/routers/ledger.py`; data `web/ledger_data.py`, `services/ledger_totals.py`.

**Common to all ledger tabs (filter bar and tab strip)**

| Value | Producer | Status |
|---|---|---|
| Tab counts "actual 616 · planned 3 · recurring 27" | `ledger_data._tab_counts` | exists |
| Filter `from`/`to` `@value=2026-10-07 / 2026-10-31` | `ledger_data.parse_filters` -> `LedgerFilters.date_from/date_to`; default window = fiscal period | partial: no default-period fallback on the form today (G2) |
| Category and account `<option>` lists | `categories_service.list_all`, `accounts_service.list_all` | exists |
| Direction options, search `q` | `LedgerFilters.direction`, `.search` | exists |
| Export menu text "actual · current filters" / "planned · current filters", csv and parquet links | per-tab export hrefs carrying the query string | missing (G1; recurring has none, ADR-0134 §6) |
| "filters · 0 selected" (bulk bar: "N selected") | client-side count of checked `@value=sel-<id>` rows | static behaviour; row ids from `TxnRow.id` |

**actual**

| Value | Producer | Status |
|---|---|---|
| Hero "spent this period" `5,014.55`, digits attrs | `MonthTotals.spent_minor` (`budget_service.month_summary`); not in ledger context today | missing (G2); digits (G10) |
| Day header "SAT 31 OCT · NET −35.50" | `ledger_totals.actual_day_nets` (`ledger_data._ledger_day_nets`) | exists |
| Row: checkbox `@value=sel-10` and `aria-label` "Select Takeaway, −35.50 PLN" | `TxnRow.id/.description/.amount`, direction sign via `domain.transactions.signed_legs` | exists |
| Description, account, category, amount, "31 OCT · Credit Card" (row menu) | `TxnRow.description/.account/.category/.amount/.operation_date` | exists |
| Transit: "Checking → Credit Card", `⇄ 21.93` | `TxnRow.account`, `.dest_account` | exists |
| Reconciliation rows `−14.72`, `+9.57` | `TxnRow` with system category | exists |
| "page 1 · older →", "recently deleted →" | `ledger_data.table_context` paging keys (`_page_keys`) | exists |
| **actual--long**: 1,234,567.89 amounts, long descriptions | same fields (stress seed) | exists |
| **actual--empty**: "No entries yet." | empty-state template; tab counts as above | exists (hero still shows 5,014.55: section 5) |
| **actual--no-matches**: "Transport · 01/01/2026 – 31/01/2026 · “pizza”" filter summary | `LedgerFilters` rendered as a summary string | missing (G2 `filter_summary`); from/to inputs in the board still show October (section 5) |

**planned**

| Value | Producer | Status |
|---|---|---|
| Hero `−1,531.35` PLN net, `data-signs=1` | `ledger_totals.planned_totals` -> `PlannedTotals.net_minor` | exists; `data-*` (G10) |
| "3 items · 1 overdue · 1 due today" | `PlannedTotals.count` only | missing: `overdue_count`, `due_today_count` (G2) |
| Rows: due date, description, account, category, amount, "promote", row menu labels | `planned_service.PlannedView`, `ledger_data._hydrate_planned_rows` | exists |
| Status "in 45 days" / "▲ overdue 3 days" / "● due today" | template `days_delta` today (`ledger/_table.html` line 112, template arithmetic) | missing as a view-model field (G2) |
| **planned--empty**: "Nothing planned." | empty template | exists (hero still shows 3 items: section 5) |

**recurring**

| Value | Producer | Status |
|---|---|---|
| Hero "per month" `−13,755.41` out, "in +23,253.18" | `ledger_totals.recurring_monthly_totals` -> `RecurringTotals.monthly_out_minor/.monthly_in_minor` | exists |
| "27 rules" | `_tab_counts["recurring"]` | exists |
| "next due 01 nov" | earliest `next_due` over active rules | missing (G2) |
| Net per month (ADR-0134 §2 L11: out, in and net) | in minus out | missing `RecurringTotals.net_minor` (G2) |
| Row: cadence "MONTHLY", next due, "ends 15 MAY 2028", description, account, category, amount | `ledger_data._recurring_row` (`cadence`, `next_due`, `end_date`, `effective_amount_minor`, `account`, `category`) | exists |
| "ƒ" marker, FORMULA breakdown ("+ 19 % of Salary, Side Income − 19 % of Bank fees") | `_recurring_row` `is_formula`, `amount_formula`; `recurring_formula` parse | exists |
| "→ next amount 1,836.93 PLN" | `formula_svc.resolve_rule_amount(... rule.next_due)` -> `effective_amount_minor` | exists |
| "↻ 4 overrides" and "OVERRIDES · 4" list: `Oct 2026 · 15,800.00 PLN · −413.97` | `recurring_service.list_overrides` -> `RecurringOverride.occurrence_date/.amount_override`; count `len(overrides)` | partial: delta vs rule default per override missing (G2) |
| "Remove override Oct 2026" `aria-label` | `RecurringOverride.occurrence_date` | exists |
| **recurring--empty**: "No recurring rules." | empty template | exists (hero still shows 27 rules: section 5) |

**recently-deleted**

| Value | Producer | Status |
|---|---|---|
| "last 90 days", section counts "Transactions · 0", "Planned · 1", "Categories · 3" | `transactions_service.list_recently_deleted`, `planned_service.list_recently_deleted`, `categories_service.list_recently_deleted` (lengths) | exists |
| "deleted 29 OCT 20:30" | `.deleted_at` on `Transaction`/`PlannedTransaction`/`Category` (`dt_local`) | exists |
| Planned row due `15 DEC`, description, category, `−2,306.35 PLN`, `@value=planned-1` | `PlannedTransaction` fields | exists |
| Category row name, "↑ income"/"↓ expense", `@value=cat-0` | `Category.name/.direction` | exists |

### 2.4 Plan

Router `web/routers/plan.py`; data `web/plan_data.py`, `web/view_models.py`, `services/budget.py`, `services/forecast.py`, `services/analytics.py`.

**budget**

| Value | Producer | Status |
|---|---|---|
| Hero "budget left" `1,399.93`, digits attrs | `MonthTotals.remaining_minor`; digits (G10) | exists / missing |
| "6,449.08 budgeted · 5,014.55 spent · 34.60 committed" | `MonthTotals.budgeted_minor/.spent_minor/.committed_minor` | exists |
| "6 categories over" | count of `BudgetLineView.is_over` | missing: `BudgetView.over_count` (G10) |
| "277.94 planned in unbudgeted categories" | `MonthTotals.unbudgeted_committed_minor` (ADR-0085) | exists |
| "34.60 committed · 6 over" (phone) | same two | as above |
| Period control "October 2026", year "2026", "oct = 7 oct → 7 nov" | `view_models.plan_header`, `month_options`, `period_label`; range = `MonthSummary.period_start`..`next_income_date` | partial: the "= 7 oct → 7 nov" range text needs a field on `PlanHeader` (G10) |
| Row: category, bar, `234.82 / 604.35`, "left 369.53", "▲ over 5.19" | `BudgetLineView` (`spent_minor`, `budget_minor`, `delta_minor`, `delta_kind`, `used_pct`) via `view_models._line_view` | exists |
| Row bar `aria-label` "39 percent spent, 60 percent left" and block cells | `BudgetLineView.used_pct` (floored) | partial: `left_pct`, cell count, rounding rule (G10; section 5) |
| Unbudgeted rows: "no budget", spent `5,790.81 / —` | `view_models.budget_view` unbudgeted lines | exists |
| Total row `5,014.55 / 6,449.08 · left 1,399.93` | `MonthTotals` | exists |
| Row menu (override) `aria-label` "Bank Fees #18 actions" | `BudgetLineView.category_name` | exists |

**year**

| Value | Producer | Status |
|---|---|---|
| Year label `2026`, year options 2025/2026/2027 | `plan_header(year_selected=…)` | exists |
| Cell text `604.35` / `↻ 1,200.00` / `• 783.11` / `–` and `aria-label` "Big Purchases, January: 604.35 PLN, default" / "…recurring override" / "…one-off override" / "unset, unset" | `YearCellView` (from `budget_service.YearlyCell.amount_minor/.origin`) via `view_models.year_view` | exists |
| `data-state` default/recurring/one-off/unset | `YearlyCell.origin` | exists |
| "2 categories without a budget" heading, unset rows | `YearView.unset_heading`, `.unset_rows` | exists |
| Current-month header `aria-current` | `view_models.plan_header` | exists |

**forecast**

| Value | Producer | Status |
|---|---|---|
| Hero "projected balance · end of sep 2027" `79,047.79` | `ProjectionSummary.end_point` (`services.forecast.projection_summary`) | exists |
| "+46,320.57 PLN over 12 months · peak 86,239.67 in aug 2027" | `ProjectionSummary.peak_point`; the delta end - now is template math | missing: `ProjectionSummary.delta_minor` (G9) |
| Horizon pills 6/12/24/60 | `forecast.normalize_horizon` | exists |
| Table: month, income, expenses, planned budget, net (with "▲" sign mark), balance (EOM) | `MonthlyProjectionPoint.income_minor/.expense_minor/.planned_budget_minor/.net_minor/.end_balance_minor` | exists |
| Chart `<g aria-label>` points and tooltips | `web/charts.py` / `forecast_data.py` geometry from `MonthlyProjectionPoint` | exists |

**analytics**

| Value | Producer | Status |
|---|---|---|
| Hero "where it went" `19,417.18` PLN spent | `analytics.spend_total_minor(bundle)` | exists |
| Range pills month / year to date / 12 months | `analytics.normalize_period` | exists |
| Row: category, `aria-label` "Taxes: 8,611.82 PLN, open in ledger" and "44 percent of spend", block cells, `8,611.82`, "▲ +1,288.90" | `view_models.spend_rows` -> `SpendRowView.amount_minor/.bar_pct/.delta_minor/.delta_kind` | exists; cell count and rounding rule partial (G10) |
| Income vs expense chart `aria-label` "Oct 2026: income 22,341.10 PLN, expense 19,417.18 PLN" and loaf geometry | `analytics.MonthlyFlow` (`income_vs_expense_monthly`), `web/charts.py` | exists |
| "Largest single items": category, "· 15 Oct", `−4,482.35` | `analytics.LargestItem.category_name/.operation_date/.amount_minor` (limit 3) | exists |

### 2.5 Settings

| Page | Value | Producer | Status |
|---|---|---|---|
| categories | Income-anchor choices Salary/Side Income/Profit Share, current anchor | `preferences_service.resolve_income_anchor_category`, `categories_service.list_all` | exists |
| categories | Group counts "Expense · 17", "Income · 5", "System · 2" | length of `categories_service.list_all` groups by `Category.direction` | exists (note: handoff lists 17/5/2 = 24 rows, picker says 21: section 5) |
| categories | Row name, "custom colour"/"default colour", "locked" | `Category.name/.color/.is_system` | exists |
| currency-fx | "No FX rates cached yet · refreshed when the app starts." | `fx_health` / `fx_service` cache state | exists (only the empty state is on the board; rates table has no handoff board) |
| preferences | Base currency `PLN`, timezone `Europe/Warsaw`, theme system/light/dark | `Settings.base_currency`, `.display_timezone`; theme is a client setting | exists |
| security | "owner@example.test" | `CurrentUser` | exists |
| security | Session device "Firefox · macOS", IP `83.24.117.9`, THIS DEVICE | `SessionRow.session.user_agent` (raw UA string today), `.session.ip`, `.is_current` | partial: device label parse (G7) |
| security | SIGNED IN / LAST SEEN / EXPIRES `12 NOV 09:14`, `now`, `12 DEC` | `Session.created_at/.last_seen_at`, `SessionRow.absolute_expires_at` | exists ("now" for the current session: template wording) |
| security | Session `@value=s2` (revoke) | `Session.handle` | exists |
| security | "12+ characters" hint, error "▲ Current password is wrong" (security--error) | `password_flow` errors | exists |
| security | "No passkeys yet." | `SecurityView.passkeys` | exists |
| users | Email, name, role (`admin`/`member`), "you" | `UserListing.email/.name/.is_admin`; current id | exists |
| users | LAST SEEN `30 OCT 21:12`, `now`, `—` | `UserListing.last_seen_at` | exists |
| users | Status "● active", "◐ new password required at next sign-in" | `UserListing.must_change_password` | exists |
| users | "✉ invited · expires 07 NOV", "pending invite", copy link / resend / revoke | invite service | T-UR30 (new `services/invites.py`) |

### 2.6 Auth

| Page | Value | Producer | Status |
|---|---|---|---|
| login, login--error | "Hello again." | static | n/a |
| login--error | "▲ Email or password is incorrect." | `auth_flow` login failure message | exists |
| register, register--error | "▲ Enter a full email address", "▲ Use at least 12 characters" | `auth_flow` / form validation errors | exists on the setup path T-UR32 (new `services/setup.py`) |
| invite, invite--used/--expired/--invalid | "invited by owner@example.test", the three state messages | invite service | T-UR30 |
| reauth | "signed in as owner@example.test" | `CurrentUser.email` | exists |
| reauth--error | "That password doesn't match. 4 attempts left." | `rate_limit` has `retry_after_seconds` only; no remaining-attempts count | missing (G8) |
| force-password, --error | "signed in as parent@example.test", "▲ Passwords don't match" | `CurrentUser.email`, `password_flow` errors | exists |

### 2.7 Errors

| Page | Value | Producer | Status |
|---|---|---|---|
| 404, 409, 500, offline | Static headings and copy ("ERROR 404", "Changed elsewhere", …) | `web/errors.py` handlers | exists |
| 422 | "▲ 2 fields need fixing", list "Amount is required", "Pick a category" | `web/errors.py` renders `field: msg` with raw field keys, no count | missing (G11) |

### 2.8 Overlays (dialog values only)

| Overlay (states) | Values | Producer | Status |
|---|---|---|---|
| new-entry (happened, planned, repeats-fixed, repeats-formula, error, over-limit, phone-sheet), category-picker (+no-match) | Amount `@value=35.50`/`13,000.00`/`0.00`; currency `PLN`; category lists "recent" (Takeaway, Groceries, Transport, Nights Out) with "↓ expense"/"↑ income"/"⇄ transit"/"± adjustment" tags; "search all 21 categories"; account list; date `2026-10-31`; due date `2026-11-15` | `categories_service.list_all`, `accounts_service.list_all`, `Category.direction`, form defaults in `web/entry_forms.py` | partial: "recent" categories and "N categories" count have no producer (G6) |
| same | Credit-line hint "Credit Card · 12,521.63 of 14,977.37 left → 12,486.13 after this" | `limit_preview.compute_limit_preview` -> `LimitPreview.available_after`, `.limit` | partial: "left" before the entry missing (G3) |
| new-entry--over-limit | "▲ Credit Card · 478.37 over the credit limit (12,521.63 left)" | `LimitPreview.over_by`; left missing | partial (G3) |
| new-entry--repeats-formula | Formula result `774.01`, component sign, `@value=12` %, "of Salary" | `recurring_formula` preview (`partial/recurring/_formula_preview.html`, `formula_svc.resolve_rule_amount`) | exists |
| edit-transaction (+error, +transit) | `@value=35.50`, `0.00`, `21.93`; destination account; hint as above; error "▲ Enter an amount above 0.00" | `TxnRow`, `LimitPreview`, form errors | partial (G3: edit must exclude the txn being edited, confirm) |
| edit-planned | `@value=2,239.80`, due `2026-12-15` | `PlannedView` | exists |
| edit-recurring (fixed, formula, empty, incomplete, picking) | `@value=277.94` / `1,836.93`; computed `—`, `1,836.93`, `3,488.75`; component `@value=19`, categories list | `recurring_formula` (`resolve_rule_amount`, preview) | exists |
| promote--planned, promote--recurring | `@value=2,239.80`, date `2026-12-15` / `277.94`, `2026-11-01` | `PlannedView`, `recurring.pending_occurrences` | exists |
| override--occurrence | Amount `277.94`, month "November 2026" `@value=2026-11` | `recurring_overrides` | exists |
| override--budget-month/-default/-every | Amount `650.00`/`700.00`, "default 604.35", "Big Purchases · Oct 2026" | `budget_overrides`, `budget.resolve_budget` | exists |
| override--remove | "goes back to the default 604.35 PLN" | `budget.resolve_budget` default tier | exists |
| override--year-cell | "Nights Out, November budget", `@value=525.26` | `YearlyCell.amount_minor` | exists |
| reconcile | "+4.29 PLN difference", "in rising dough 3,685.81", bank `@value=3,690.10`, SNAPSHOTS `01 APR 3,702.44`, `01 MAR 3,415.02` | `accounts_data.recent_snapshots` (snapshots), `balance.derive_balance`; difference: none | partial (G5) |
| reconcile--liability | "−121.63 difference", "12,521.63 remaining balance", `@value=12,400.00`, snapshots | `accounts_data.available_mode_context` (`available_minor`), snapshots; difference none | partial (G5) |
| edit-account (+liability), new-account (+filled, +error) | Name/currency/type, `@value=0.00`/`1,250.00`, as-of `2026-10-31`, "▲ 2 transactions: this balance will count against net worth", "▲ Unknown currency code" | `Account`, `AccountStats` txn count, form errors | exists |
| delete-account | "Delete Investments E?" (account missing from the list: section 5) | `Account.name` | exists |
| delete-account--blocked, --blocked-planned | "84 transactions and 3 planned or recurring items", "2 recurring rules", "view 84 transactions" | counts returned by the account delete service | exists (T-UR33, T-UR23) |
| row-menu (account, budget, planned, recurring, transaction, upcoming), period-picker (+year) | No new values (static action lists; month and year names) | `view_models.month_options`, `plan_header` | exists |
| command-palette (+filtered, +no-match) | Static commands, typed query echo "led" / "pizza" | static, request echo | exists |
| shortcuts | Static key map | static | exists |
| edit-category, new-category (+filled, +error) | "↓ expense · locked by 41 entries"; swatch `@value=#ef4444` etc; preview name | `Category.direction/.color`; entry count none | missing (G6) |
| archive-category | "Its 41 entries and budget history stay" | entry count none | missing (G6) |
| add-user (+error), edit-user, delete-user, reset-password, one-time-password | Email, role, "Delete Ola?", `partner@example.test`, one-time password `kT4p-9wrx-Lomb`, "▲ A user with this email already exists" | `users.build_draft`, `generate_password`, `get_live_user`, `UserConflict` | exists (edit-user email change refused: T-UR29) |
| invite-user (+error), revoke-invite | "▲ This person already has an account", "The link sent to accountant@example.test…" | invite service | T-UR30 |

### 2.9 Chart specimens (`charts/*.html`)

| Specimen | Values | Producer | Status |
|---|---|---|---|
| forecast | 5 gridline labels, one point per month with `aria-label`, tooltip 190x64 | `forecast_data` / `web/charts.py` from `MonthlyProjectionPoint` | exists |
| income-vs-expense | 4 month loaves, gridline 10k, `aria-label` per month | `analytics.MonthlyFlow`, `web/charts.py` | exists |
| spend-by-category | Same rows as 2.4 analytics | `view_models.spend_rows` | exists; cell rule (G10) |
| sparkline | `<polyline points="0,20 10,18 … 100,8">` | `balance.sparkline_points` | exists |
| year-grid | Same cells as 2.4 year | `view_models.year_view` | exists |

## 3. What is already covered (no gap)

Most values come from existing canonical modules: budget summary (`services/budget.py`), fortune (`services/fortune.py`), forecast monthly points (`services/forecast.py`), analytics bundle (`services/analytics.py`), per-account stats and sparkline (`services/balance.py`), ledger day nets and strip totals (`services/ledger_totals.py`), recurring and formula amounts (`services/recurring_formula.py`), credit utilisation (`web/accounts_view.py`), upcoming (`services/upcoming.py`). Users, invites, delete-account counts and first-run setup are the Phase P items T-UR29..T-UR33 and are not repeated here.

## 4. Gaps

Grouped by owning service so each group maps to one wave 2 item (T-UR34b..). "Shared file" notes say where two groups touch the same file in disjoint hunks (the later item merges the main work branch into its branch; no rebase).

| Group | Item | Owning file(s) | Fields / behaviour to add | Handoff pages | Size |
|---|---|---|---|---|---|
| **G1 Export honours tab and filters** (required) | T-UR34b | `web/ledger_data.py` (`parse_txn_filter`, `parse_planned_filter` only), `web/routers/transactions.py` (`export`), `web/routers/planned.py` (`export`), `domain/planned.py` (`PlannedFilter`), `services/planned.py` (`list_planned`/`list_filtered`), new `web/ledger_export.py` (hrefs) | See "Current export code" below. Parse `direction` into `TransactionFilter.directions`; in the planned parser map `account_id`, `category_id`, `direction`, `q` (needs `PlannedFilter.description_contains`); optional date defaults equal to the Ledger period; a pure helper builds per-tab csv and parquet hrefs from the current query string (none for recurring) | ledger actual, planned (+ empty, no-matches, long), phone | S |
| **G2 Ledger strips, row status, filter summary** | T-UR34c | `services/ledger_totals.py`, `web/ledger_data.py` (`index_context`, `_hydrate_planned_rows`, `_recurring_row`; shared file with G1) | `PlannedTotals.overdue_count`, `.due_today_count`; actual hero `spent_minor` reused from `budget.month_summary` (no new arithmetic); `RecurringTotals.rule_count`, `.next_due`, `.net_minor`; planned-row `days_delta` + status kind (`in N days`, `overdue N days`, `due today`), shared by Today upcoming; recurring override `delta_vs_default_minor`; `filter_summary` string for no-matches; default from/to period | ledger actual, planned, recurring, no-matches; today (overdue days) | M |
| **G3 Credit-limit preview** (required) | T-UR34d | `services/limit_preview.py`, `web/routers/transactions.py` (`limit_preview` handler only; shared file with G1) | Add `available_before` ("left of limit": `max(limit - used_before, 0)`) and `account_name` to `LimitPreview`, keeping `available_after`, `over_by`, `limit`; edit mode excludes the transaction being edited from the "before" balance (`exclude_txn_id`; confirm with designer: the edit board repeats the new-entry figures) | new-entry (happened, over-limit, error, phone-sheet), edit-transaction (+error, +transit), category-picker | S |
| **G4 Today afford** | T-UR34e | `services/today.py` (`AffordResult`), `web/routers/today.py` (`afford`) | Unclamped per-day figure (`per_day_minor` is clamped at 0 today; the board shows `−14.20`) and an `over_minor` amount; a typed invalid-amount error message "Enter an amount, like 250.00" instead of bare `422 "invalid amount"`. Semantics confirmed by the designer 2026-11-23 (ADR-0151 §1; board figures are overlay row 9) | today--afford-over, today--afford-invalid | S |
| **G5 Reconcile difference** | T-UR34f | `services/account_reconcile.py`, `web/routers/accounts.py` (reconcile preview), `web/accounts_data.py` (`reconcile_modal_context`) | `difference_minor(account, derived, entered)` (asset: entered - in-app; liability: entered available vs `available_minor`), server-rendered by an HTMX preview (handoff JS does no number work) | reconcile, reconcile--liability | S |
| **G6 Category usage** | T-UR34g | `services/categories.py`, categories repository (entry count query), `web/routers/categories.py` | `entry_count(conn, user_id, category_id)` for "locked by N entries" and "Its N entries"; "recent categories" for the picker (last-used, up to 4) and the "search all N categories" count | edit-category, archive-category, all new-entry / edit pickers | S |
| **G7 Session device label** | T-UR34h | `services/security_settings.py` (`SessionRow`) | `SessionRow.device_label` ("Firefox · macOS") parsed from `Session.user_agent` by a small pure function; fall back to "Unknown device" | settings/security (+error) | S |
| **G8 Re-auth attempts left** | T-UR34i (may merge with G7) | `services/rate_limit.py` (`Decision`), `services/reauth.py` | `Decision.attempts_left` from the rule bucket; reauth failure message "N attempts left" | auth/reauth--error | S |
| **G9 Forecast summary delta** | T-UR34j (may merge with G10 only if files are disjoint: they are) | `services/forecast.py` (`ProjectionSummary`) | `delta_minor` (end - now), `months` | plan/forecast | S |
| **G10 View-model values** | T-UR34k | `web/view_models.py`, `web/templating.py`, `domain/money.py` (only if the rounding rule moves there) | (a) hero figure fit filter: `data-digits`, `data-marks`, `data-signs` (README: "one small Jinja filter"), used by today, accounts, ledger, plan heroes; (b) `BudgetView.over_count`; (c) `PlanHeader` range text "7 oct → 7 nov"; (d) bar fields `left_pct` and block-cell counts for the 10-cell and 20-cell bars (handoff rounds half up and has a min-one-cell rule only on the 20-cell bar; `percent_of` floors); (e) `UpcomingView` group counts (overdue, due today) | today, accounts, ledger heroes, plan/budget, analytics, accounts credit card | M |
| **G11 422 error summary** | T-UR34l | `web/errors.py` | Count line "N fields need fixing" and human field labels instead of raw field keys | errors/422 | S |

Notes for the orchestrator:

- G1 and G2 both edit `web/ledger_data.py` (G1: lines 85-109, G2: later hunks); G1 and G3 both edit `web/routers/transactions.py` (G1: `export`, G3: `limit_preview`). Hunks are disjoint; dispatch the later one after merging the earlier, or serialise G1 then G2/G3.
- No gap needs a migration.
- G10 (a) and (d) are template-facing helpers consumed by the frontend migration (T-UR12 family); they live here because the inventory finds no producer today. If the orchestrator prefers, move them to the frontend phase and keep G1..G9, G11 in Phase P.
- Not gaps (listed so nobody re-derives them): users, invites, edit-user refusal, delete-account counts, first-run setup, mail port (T-UR29..T-UR33, T-UR31).

### Current export code (required statement)

- `GET /transactions/export` (`web/routers/transactions.py` `export`): `format` csv (default) or parquet. Filter from `ledger_data.parse_txn_filter`: `date_from`, `date_to`, `account_id`, `category_id`, `min_amount`, `max_amount`, `q` (as `description_contains`). It does **not** read `direction`, which the Ledger filter bar (`ledger_data.parse_filters`) does send, so a direction-filtered ledger exports all directions. Columns: id, date, amount_minor, currency, description, category, account, dest_account. No pagination parameter (exports all matching rows). Filename `transactions_<yyyymmdd>.<ext>`.
- `GET /planned/export` (`web/routers/planned.py` `export`): filter from `ledger_data.parse_planned_filter`: `date_from`, `date_to`, `scope=unpromoted`. It ignores `account_id`, `category_id`, `direction`, `q`; `PlannedFilter` already has `account_ids`, `category_ids`, `directions` but no description field. With no dates it defaults to the current calendar month (`services.planned._default_window`), not the fiscal period the Ledger shows. Columns: id, date, amount_minor, description, kind, promoted (no account, category or currency).
- Recurring has no export (ADR-0134 §6 agrees).
- No export link on the new Ledger page: the only links are static `/transactions/export?format=...` in `templates/transactions/index.html` and `/planned/export?format=...` in `templates/planned/index.html`, with no query string, so even the supported filters are not carried.
- The handoff export menu ("actual · current filters", csv, parquet) therefore needs the per-tab links built from the live filter state (G1).

### Current credit-limit preview (required statement)

`services/limit_preview.compute_limit_preview` returns `LimitPreview(projected_balance, available_after, used_after, limit, over_by, currency)` for a liability with a credit limit, else `None`. The partial `partials/transactions/_limit_preview.html` prints "Available <after> · Limit <limit>" or "Over limit by <over_by>". Missing for the handoff text "12,521.63 of 14,977.37 left → 12,486.13 after this": the **before** figure (left of limit before this entry) and the account name; the over-limit text "478.37 over the credit limit (12,521.63 left)" needs the same before figure. The handoff also shows the hint on edit (G3 open question) and on the phone sheet.

## 5. Overlay candidates (T-UR00b)

Values that differ only because the handoff is internally inconsistent; the handoff side is corrected (ADR-0147 §3), never the app. These are not app gaps. "Board" is the page file under `docs/design/rising-dough-frontend/pages/`. Where a row is a family, the instance count is given; T-UR00b generates the rows from the seed.

| # | Board | Value | Why it cannot come from the seed |
|---|---|---|---|
| 1 | `overlays/delete-account.html` | "Delete Investments E?" | No account "Investments E" exists in the 10-account list (README note 17). Seed has Investments A-D only; overlay to an existing deletable account name or add a seed account (T-UR00a decides). |
| 2 | `accounts--empty.html` | Hero `34,439.69`, "10 accounts", assets/liabilities/planned on an empty list | An empty account list has no net worth; app renders zeros. |
| 3 | `ledger/actual--empty.html` | Hero "spent this period 5,014.55", tab counts 616 / 3 / 27 with "No entries yet." | Empty state cannot have counts; same for `ledger/planned--empty.html` ("3 items · 1 overdue · 1 due today", net `−1,531.35`) and `ledger/recurring--empty.html` ("27 rules", out `−13,755.41`, in `+23,253.18`). 3 boards. |
| 4 | `today--empty.html`, `today--loading.html` | Hero `199.99`, spent/left/of figures, net worth `34,439.69` with empty or loading panels | Empty state with zero data cannot show those totals (the `--empty` state is the upcoming/accounts list only). |
| 5 | `ledger/actual--no-matches.html` | Filter summary "Transport · 01/01/2026 – 31/01/2026 · “pizza”" while the `from`/`to` inputs still read `2026-10-07` / `2026-10-31` and category/account selects read "all" | Inputs and summary disagree; overlay the input `value`s (`@value`) to `2026-01-01` / `2026-01-31`. |
| 6 | `today*.html` (6 boards), `plan/budget.html` header | `aria-label` "78 percent spent, 15 percent left" | 78 + 15 does not make 100 (seed gives spent 78, committed 1, left 22). 7 boards share it. |
| 7 | `accounts.html` credit card bar | `aria-label` "16 percent spent, 80 percent left" with "used 16% · available 12,521.63 of 14,977.37" | 12,521.63 of 14,977.37 is 84% available, not 80%. |
| 8 | `plan/budget.html` rows (12 rows) | `aria-label` "N percent spent, M percent left" (39/60, 45/60, 71/30, 5/90, 90/10, 3/100, 0/100, …) | "left" is the empty cell count times 10, not 100 - spent (e.g. Groceries 427.17 / 956.74 = 45% spent, 55% left; board says 60). Also the board rounds half up where `percent_of` floors (Big Purchases 38.9% shows 39). Decide in T-UR00b whether to correct the labels or the app rule (G10 d). |
| 9 | `today--afford-over.html` | "per day becomes −14.20 · 114.20 over" for amount `1,800.00` | Left `1,399.93` over 7 days gives `−57.15` per day; the figure `114.20` has no derivation. Also contradicts the clamp in `AffordResult`. Overlay values to the seed's result once G4 fixes semantics. Designer confirmed 2026-11-23 (ADR-0151): −57.15 per day · 400.07 over. |
| 10 | `ledger/recurring.html` | Formula rows VAT Refund `+3,729.21`, Taxes `−1,836.93`, Transit `⇄ 12,415.80`, Salary `+16,213.97` all show "→ next amount 1,836.93 PLN" (3 formula rows with the same text) | Different amounts and one shared formula result; the seed's `resolve_rule_amount` cannot give 1,836.93 for all. Also `overlays/edit-recurring--*`: amount `1,836.93` vs picking state `3,488.75`. |
| 11 | `ledger/recurring.html` overrides | Taxes: `Oct 2026 1,640.00 PLN −196.93` (default 1,836.93); Salary overrides `15,800.00 −413.97` etc. | Deltas are consistent only against 1,836.93 / 16,213.97, which row 10 breaks. Re-derive after the seed. |
| 12 | `overlays/*` (all pickers: new-entry x7, edit-transaction x3, edit-planned, edit-recurring x5, category-picker x2) | "search all 21 categories" and the 21-name picker list (includes "Wyjścia na miasto", omits "Bank Fees #18") | `settings/categories.html` lists 24 (17 expense incl. Bank Fees #18 and Opłaty bankowe i prowizje, 5 income, 2 system). 19 boards share the count. ADR-0151 (2026-11-23): N excludes Reconciliation (system-only in the picker). **Partly resolved (PAR-D, operator decision 2026-11-25, Q6):** the seed now has "Wyjścia na miasto" (expense, no colour), so the picker lists the handoff's 16 expense names; the seed yields N = 24 (18 expense + 5 income + Transit; overlay "search all 24 categories"). The count conflict (handoff 21, ADR-0151 23) is still the operator's call. |
| 13 | `settings/users.html`, `settings/security*.html`, `auth/*` | Dates after the frozen date: users `12 NOV 08:40`; sessions `12 NOV 09:14`, `02 NOV 18:40`, `11 NOV 22:03`, expiry `12 DEC` / `02 DEC` (frozen "now" is 31 Oct) | Last seen / signed in cannot be in the future. 3 boards (users, security, security--error). |
| 14 | `ledger/recently-deleted.html` | Planned "Car −2,306.35 PLN" deleted, while `ledger/planned.html` lists "Car −2,239.80" (same due date 15 DEC) | Same entity, two amounts. |
| 15 | `ledger/planned.html` | Filter bar `from 2026-10-07 to 2026-10-31` yet the list includes `15 DEC` | Rows outside the window the filter claims. |
| 16 | `today.html` and variants | Two copies "7 days until next income (Salary, 7 nov)" and "7 days until salary (7 nov)" | Phone vs desktop copy (README note 8); app emits both from one field, so this is a text overlay only if the visual suite renders one viewport. Listed for T-UR00b to decide. 6 boards. |
| 17 | all pages | `aria-keyshortcuts` `g o` and visible `g o` label for Today | ADR-0147 §5: operator chose `g t`; text and attribute overlay rows on every page (shell, 106 files; generated rows, `aria-keyshortcuts` and the label text). |
| 18 | `accounts.html` (10 rows), `charts/sparkline.html` | `<polyline points="0,20 10,18 …">` identical for every account | Handoff placeholder geometry; app computes per-account series. Overlay only via `source = "geometry"` rows (ADR-0147 §4), generated by the same geometry function. |
| 19 | `overlays/edit-transaction*.html` | Credit-line hint "12,521.63 of 14,977.37 left → 12,486.13 after this" equals the new-entry hint for the same 35.50 | For an existing 35.50 transaction the balance already includes it; "left" and "after" cannot both be the new-entry numbers. Confirm G3 edit semantics; overlay if the seed gives different numbers. Designer confirmed 2026-11-23 (ADR-0151 §1): edited entry left out of "before". |
| 20 | `overlays/reconcile*.html` | Snapshot dates `01 APR` / `01 MAR` and balances (e.g. `3,702.44`) while `accounts.html` says "checked 01 APR" for Checking | Seed snapshots must match; if the seed has other dates, overlay. Low risk; listed so T-UR00a seeds Checking snapshots on 01 APR and 01 MAR. |

**Design-parity seed resolutions (PAR-D, operator decision 2026-11-25, "Design-parity group"):** the seed now follows the handoff (no overlay row needed) for category chip colours by name (Q19: `settings/categories.html` presets, Reconciliation none, Transit teal), the picker entry "Wyjścia na miasto" (Q6, row 12 above) and Today's "showing 6 of 23" (eight transfer-type planned items dated 21 to 28 Nov; forecast, budget and income/expense figures unchanged). The afford-it states (row 9, ADR-0151) and `accounts--empty` (row 2, ADR-0147) conflict with the designer-number decisions and stay as overlay rows (blocked, not touched).

**S1 parity pass (T-UR00b, 2026-11-25), Today and Ledger actual:** seed: the three 7 Nov expense rules are created before Salary and VAT Refund and start on 7 Jul (rules list by start date, then id), and the listed ledger entries are written in reverse so a day reads newest-first like the handoff. App: Today's cap of 6 applies to the next-N-days rows only (overdue and due-today always listed; `derived.md` deviation), and the transfer glyph is the handoff's `⇄` (U+21C4), not `↔`. Overlay rows: Ledger actual hero `5,014.55` to `19,417.18` with `data-digits` 6 to 7 (the board repeats Today's budgeted-only spend; ADR-0151 section 2 defines every expense in the pay window), Today chip `Bank fees` to `Bank Fees #18` (one category in the seed). Not fixed here (frontend phase T-UR34c2): the ledger default `from`/`to` = pay period start to today (handoff inputs read 2026-10-07 and 2026-10-31) and the page of 11 rows ending in `older →`: the reference route must carry `date_from=2026-10-07&date_to=2026-10-31&page_size=11`, with which the 11 listed rows equal the handoff text exactly.

Count: **20 rows (families)**; expanded to instances by T-UR00b (row 17 alone is one row per page, 106 pages).

## 6. Not inventoried

Nothing page-level is outstanding. Items deliberately left out: `components.html` and `index.html` (specimen and link index, sample data only); `static/` assets (CSS, fonts, icons, JS: never overlaid); exact seed values for the rates table on `settings/currency-fx.html` (the handoff shows only the empty state); and values owned by T-UR29..T-UR33 (marked `T-URxx`), whose service fields are defined by those items.

**F1 parity pass (T-UR00b, 2026-11-25), Plan:** seed: the budget defaults of Nights Out and Subscriptions are the year grid's 525.26 and 122.91 with the October one-offs 783.11 and 592.57 and the recurring overrides Gifts Dec 1,200.00, Subscriptions Nov and Dec 140.00, Travel Jul 2,500.00 (the budget page's October figures are unchanged); the October Taxes and Fixed costs entries are split so "Largest single items" reads Taxes 15 Oct 4,482.35, Fixed costs 7 Oct 2,883.97, Taxes 15 Oct 2,155.21; the Jul to Sep expense history is spread over nine categories (three a month) so every "vs 12-mo avg" arrow points as on the board (the five up arrows have no history). The seed has 42 actual entries (overlay `actual 42`) and Checking 33 entries. Overlay: the 14 `vs 12-mo avg` figures (the board's twelve-month averages total about 22.7k a month, its own flow chart shows about 24k for four months: the figures cannot both hold), the largest-items label `Fixed Costs` to `Fixed costs`, and the forecast rows regenerated for the new Nov, Dec and Jul budgets. Not done: the inline year-cell editor (`override--year-cell`, `rd-year-editor`; the page test has no recipe in `handoff_clicks.py` and the page is unmapped in `test_reference.py`, both outside this item), and the Dec 2026 forecast net cell (the board paints it as a loss, the seed yields +597.07; one 53 px cluster against the cap of 52).

**F7 parity pass (T-UR00b, 2026-11-25), Plan dialogs:** `override--year-cell` is mapped: `handoff_clicks.py` clicks the Nights Out November cell and the app swaps in the inline `rd-year-editor` (derived.md "Year grid, cell editor"); the three `override--budget-*` dialogs are compared with the amount typed (`handoff_forms.DIALOG_SUBMITS`: 650.00, 700.00, 650.00, the field focused, no selection) and `row-menu--budget` with the first item focused from the keyboard. Not done: `plan/analytics` (the nine `vs 12-mo avg` figures: the board's twelve-month averages and its flow chart cannot both hold with the seed's 12 history entries; any wrong row is a ~200 px cluster against the cap of 52) and the Dec 2026 forecast net cell (the board paints +597.07 in the loss colour; the app paints a positive net plain).
