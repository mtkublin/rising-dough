# Budget Planner — Requirements

> Source: `docs/initial_reqirements.txt` + decisions captured during planning Q&A (see `docs/adr/`).
> This is the canonical requirements document; the initial text file is retained for history only.

---

## 1. Product Scope

A web application for personal budget planning and fortune (net-worth) tracking across multiple accounts and currencies. Started as a local single-user tool (v1, bound to `127.0.0.1`); v2 ships the Rising Dough redesign (still local, still single-user); v3 (§6) moves the same functional surface to a hardened public-internet deployment and promotes the long-scaffolded `user_id` column into real **multi-user** support (admin-managed; see [§6.9](#69-multi-user-scope-added-2026-10-30-adr-0061) and [ADR-0061](adr/0061-v3-multi-user-admin-bootstrap-and-data-isolation.md)).

---

## 2. Functional Requirements

### 2.1 Transaction Log (persistent)

- **F1.1** Record transactions with these mandatory fields: `operation_date` (DATE), `category_id`, `amount` (positive integer in minor units of the account's currency), `description`, `account_id`. On create forms (transactions, planned, recurring, reconcile, budget rule), `operation_date` defaults to today in `display_timezone`; `amount` inputs reject non-digit input client-side, **accept both `,` and `.` as the decimal separator** (server-side normalisation via `domain.money.parse_amount_str`), and never trigger a slide-over dismissal when a side-effect HTMX request (e.g. `/transactions/_limit_preview`) resolves — the dismiss-on-success behaviour fires only on the owning form's submit per [ADR-0040](adr/0040-modal-dismissal-scope.md). Id-reference fields (category, account, dest, currency) render as filterable comboboxes with case-insensitive substring match — see [ADR-0030](adr/0030-shared-form-interaction-primitives.md).
- **F1.2** All transactions persisted in SQLite.
- **F1.3** Filterable by any field (date range, category, amount range, account, description substring).
- **F1.4** Export the current filtered view to CSV and Parquet.
- **F1.5** Edit any existing transaction; soft-delete any existing transaction. Every mutation recorded in `audit_log`.
- **F1.6** Categories drawn from a user-managed list. Each category has a `direction`: `income`, `expense`, `transit`, or `adjustment`. **User-created categories are restricted to `income` and `expense`** — `transit` and `adjustment` are reserved for the two seeded system categories (`Transit`, `Reconciliation`) created by the seed migration. The category create / edit form in Settings exposes only `income` and `expense`; the service layer rejects user requests carrying `transit` or `adjustment` with 422. System categories are also immutable (not renameable, not soft-deletable) per existing `is_system` guard. Categories also carry an optional `color` (nullable 6-digit lowercase hex, e.g. `#a3c2ff`) stored on `categories.color`; when `NULL` the category name renders in its `direction` color (`--income` / `--expense` / `--transit` / `--adjust`), when set it renders in the override color. The create and edit forms expose a color picker with a "Use direction default" affordance that clears the override. The direction pill (`direction_badge`) continues to reflect `direction` only, independent of the override. See [ADR-0048](adr/0048-category-color-coding.md).
- **F1.7** Transits between the user's own accounts modelled as a single transaction row with both `account_id` (source) and `dest_account_id` (destination) populated. Transits are excluded from income/expense statistics. **Transits are only allowed between accounts of the same currency.**

### 2.2 Account Management

- **F2.1** Create multiple accounts. Each account has: `name` (required, unique), `type` (optional free-text label, e.g. "bank", "cash"), `currency` (ISO 4217, immutable after creation), `opening_balance` (integer minor units). Account creation surfaces as a slide-over (not inline), carries a visible close affordance per [ADR-0030](adr/0030-shared-form-interaction-primitives.md), clears its inputs after a successful save, selects currency from a filterable combobox over the ISO 4217 list, and **shows the "Credit limit" field only when the "Credit (liability)" toggle is enabled** — this conditional-visibility rule applies on initial render inside the slide-over, on toggle change, and after HTMX re-swaps the form (e.g. 422 validation rerender). The initial-render regression (credit-limit visible even when the toggle is off on a fresh New-account slide-over) is a bug fixed in T-123; see [ADR-0030 §6](adr/0030-shared-form-interaction-primitives.md) for the lockstep `hidden` + `aria-hidden` + `disabled` contract.
- **F2.1a** Liability accounts carry an `is_liability` boolean (default `false`) and an optional `credit_limit_minor` positive integer; see [ADR-0024](adr/0024-liability-accounts-and-credit-limit.md). The user-facing label for the liability toggle is **"Credit (liability)"** (ADR-0030) — the data contract is unchanged.
- **F2.2** Transactions must reference an existing (non-deleted) account.
- **F2.3** View current state per account:
    - Current balance (derived from `opening_balance + Σ signed transactions`).
    - Transaction count, average inflow/outflow, last activity date.
- **F2.4** Manual balance snapshots (user clicks "take snapshot") stored in `account_snapshots` as a pure audit record (does not alter the derived balance).
- **F2.5** Reconciliation flow: user enters the true current balance from their bank; the system computes the delta and auto-inserts an adjustment transaction under the seeded "Reconciliation" category so the derived balance matches reality. The reconcile dialog is a slide-over with a visible close affordance per [ADR-0030](adr/0030-shared-form-interaction-primitives.md).

### 2.3 Planned Transactions and Recurring Rules (separate surfaces — [ADR-0038](adr/0038-recurring-standalone-lifecycle.md))

Planned transactions and recurring rules are two independent concepts with two independent lifecycles. The UI must not conflate them.

#### 2.3a Planned transactions (one-off intent)

- **F3.1** Planned transactions follow the same data model as persistent transactions. `recurring_rule_id` and `occurrence_date` columns remain on `planned_transactions` **only** for the historical rows created before ADR-0038; new planned rows are always one-off (`recurring_rule_id IS NULL`).
- **F3.3** One-off planned transactions supported (not tied to a rule). This is the only kind of planned row a user can create via the UI.
- **F3.4** Filtering, export, edit, soft-delete — same semantics as the persistent log.
- **F3.7** Planned → actual promotion is **manual**. User clicks "mark executed", edits amount/date/description if needed, system inserts into the persistent transaction table and stamps `promoted_to_txn_id` on the planned entry for audit.
- **F3.10** The Ledger Planned tab (`/ledger?view=planned`) lists **only persisted one-off planned transactions**. Virtual recurring occurrences do **not** appear in this tab. See [ADR-0038](adr/0038-recurring-standalone-lifecycle.md).

#### 2.3b Recurring rules (standing schedule)

- **F3.2** Recurring rules supported with cadences: `monthly`, `quarterly`, `yearly`. Rules are the source of truth for upcoming occurrences; a persisted `recurring_rules.next_due DATE NOT NULL` column stores the authoritative next-occurrence date and is advanced on promotion. See [ADR-0038](adr/0038-recurring-standalone-lifecycle.md).
- **F3.2a** A recurring rule may carry an optional `end_date` (stop date). Semantics: the last valid occurrence is the latest canonical date `<= end_date` (inclusive). Must be `>= start_date` (DB-enforced, surfaced as an inline form error on 422). Setting `end_date < today` on create, or `end_date < next_due` on edit, deactivates the rule within the same transaction. `services.upcoming.list_upcoming` filters rules whose `next_due > end_date` to prevent stale pre-promotion display. Forecast and Budget already respect `end_date` through `generate_occurrences`. See [ADR-0063](adr/0063-recurring-stop-date.md).
- **F3.5** A dedicated view for managing recurring rules (`/ledger?view=recurring`): list, edit, delete (soft via `deactivate_rule`), **promote-next**, **override-next**.
- **F3.6** Per-occurrence overrides via `recurring_rule_overrides(rule_id, occurrence_date, state, amount_override, description_override, date_override, promoted_to_txn_id)` with `state ∈ {skipped, overridden}`. Semantics narrowed by ADR-0038 and amended by [ADR-0046](adr/0046-recurring-override-soft-consume.md): an override applies to **one** promotion whose `due_date = occurrence_date`, and on promotion the row is **soft-consumed** by stamping `promoted_to_txn_id = <new txn id>` (not deleted). Soft-consume keeps the override visible to historical reads so [ADR-0045](adr/0045-recurring-formula-amount.md) formula compute continues to see B's May override when materialising A's May amount after B's promotion. "Skip July AND September" remains two rows — each inserted when its target becomes `next_due`. Default `list_overrides` filters out consumed rows so the Recurring UI and promote-lookup paths are unaffected; `list_overrides_all` (used by formula compute) includes them. The Recurring row exposes an **"Override next…"** action that pre-fills `occurrence_date = rule.next_due`.
- **F3.8** Recurring → actual promotion is **manual** and lives on the recurring rule, not on a planned row. User clicks "promote" on a recurring row → modal pre-fills from the rule's defaults (plus any override on `next_due`); on confirm the system inserts a `transactions` row with `promoted_from_recurring_rule_id = rule.id` + `promoted_from_recurring_date = next_due`, advances `rule.next_due` via `services.recurring.advance_next_due`, updates `rule.last_promoted_date = next_due`, deletes the matching override row (if any), and writes audit entries. If `advance_next_due` returns `None` (end-of-rule reached) the rule is set to `active = 0`.
- **F3.11** Recurring rule `default_amount` may be defined as a **formula**: a linear combination of signed terms where each term is `coefficient_bps × Σ(monthly amounts of recurring rules in selected source_category_ids)`. Formula value = `Σ terms`. Each term carries `sign ∈ {+, −}`, `coefficient_bps` (basis points, positive), and a non-empty `source_category_ids` list. The formula is stored as versioned JSON (`schema_version: 2`) in `recurring_rules.amount_formula` and overrides `default_amount` at every expand site (Budget `committed_in_window`, Forecast, Promote modal pre-fill, Ledger row render). **Chaining is allowed**: a source rule may itself be a formula rule; the compute recurses with memoisation. Cycle detection runs at the save boundary — attempts to create a dependency cycle 422 with "formula would create a cycle". If a formula resolves to a non-positive amount at promotion, 422 with "formula resolved to a non-positive amount" (no silent clamp). The snapshot `default_amount` stored on a formula rule is a last-computed convenience value that does not drive display or promotion. Direction is magnitude-only within terms; the computed amount takes on *this rule's* category direction at promotion. See [ADR-0047](adr/0047-recurring-formula-linear-combination-and-chaining.md) (supersedes [ADR-0045](adr/0045-recurring-formula-amount.md) §Decision).
- **F3.9** Skip-next is a separate affordance from Delete. "Skip next" writes a `state=skipped` override for the current `next_due`, which blocks promotion for that occurrence; a companion endpoint `POST /recurring/{id}/skip-next` applies the skip and advances `next_due` (same advancement rules as F3.8) in a single DB transaction. Deleting the rule (soft via `deactivate_rule`) stops all future advancement.

### 2.4 Monthly Budget

- **F4.1** Flat category list (no hierarchy).
- **F4.2** Three-tier budget resolution per category per month:
    1. `budget_defaults(category_id, amount)` — base.
    2. `budget_recurring_overrides(category_id, month 1-12, amount)` — applied every year for that month.
    3. `budget_one_off_overrides(category_id, year, month, amount)` — applied once.
    Resolved as `one_off ?? recurring ?? default`.
- **F4.3** No rollover between months. Each month resets.
- **F4.4** Per-category budget only. Total budget shown as a derived sum.
- **F4.5** Current month view includes per-category spent / budgeted / remaining, plus analytical values: average monthly spend overall, average this year, delta vs previous month. The three analytical values render as the trailing columns of the Section 1 Monthly summary table — **Avg/mo** · **YTD avg** · **Δ prev** — with the delta carrying an explicit sign and a `.delta--up` / `.delta--down` modifier class; `tfoot` leaves those cells blank (weighted sums across differing active-month counts are misleading). YTD avg + Δ prev are hidden below the 640px viewport; Avg/mo stays visible. The values originate on `CategoryBudgetLine` in `services.budget.month_summary` and this is a template-only surfacing per [ADR-0049](adr/0049-budget-monthly-summary-analytics-columns.md). The Rules section renders one row per live expense category with two surfaces: a **Default amount** input (inline-editable, submits to the existing `POST /budget/defaults/{category_id}`) and an **Override…** button that opens a slide-over for authoring a recurring (per-month) or one-off (year + month) override on that category. The slide-over dispatches to the two existing override endpoints; the three persistence tables ([ADR-0014](adr/0014-budget-flat-no-rollover-three-tier.md)) remain the single source of truth. See [ADR-0031](adr/0031-budget-page-composition-v2.md).
- **F4.6** Current month view surfaces a prominent "Left to spend per day" metric: `remaining_minor ÷ days_until_next_income`, where `remaining_minor = budgeted − spent − committed`. Per-category `spent_minor` sums expenses over the **paycheck window** `[last_anchor_date, today]` — `last_anchor_date` is the most recent promoted anchor-category transaction with `operation_date <= today`, falling back to month start when no such transaction exists, when no anchor is configured, or in zero-budget months (see [ADR-0041](adr/0041-budget-period-anchor-window.md)). `budgeted_minor` stays monthly (one budget per paycheck cycle; [ADR-0014](adr/0014-budget-flat-no-rollover-three-tier.md) tiers unchanged). `committed_minor` is the sum of unpromoted planned-expense + active-recurring-expense amounts whose effective date (resp. `next_due`, override-applied) falls in `[today, next_income_date)` per [ADR-0039](adr/0039-budget-daily-spend-includes-recurring.md). `days_until_next_income` is driven by the configured income anchor category and falls back to end-of-month when the anchor is unset or stale (see [ADR-0025](adr/0025-user-preferences-and-income-anchor.md)). Zero-budget months render `—`. The committed figure renders as a dim sub-line beneath the headline on both the Budget hero and the Overview Month panel: `"X committed (recurring + planned)"`. The income-anchor "next date" calculation uses `services.income.next_anchor_date` which composes persisted planned one-offs + active recurring `next_due` values for the anchor category — virtual occurrence expansion is no longer required (ADR-0038). Analytics (`avg_this_year`, `avg_monthly_overall`, `delta_vs_prev_month`) stay on calendar-month windows — they are historical references, not current-cycle math.
- **F4.6a** The Plan hub (`/plan?tab=budget` and `?tab=analytics`), the Today surface (`/today`), and the legacy Overview (`/`) default their landing `(year, month)` to the **fiscal month** — the month of `last_anchor_date` (ADR-0041). When no anchor is configured, or when no promoted anchor-category transaction exists on-or-before today, the surfaces fall back to the calendar month. Explicit `?year=&month=` query parameters on `/plan` still win over the default so the Plan picker's prev/next navigation is unchanged. See [ADR-0064](adr/0064-plan-default-fiscal-month.md).
- **F4.7** The income anchor is a user preference (`user_preferences(key='income_anchor_category_id')`, [ADR-0025](adr/0025-user-preferences-and-income-anchor.md)). The selector lives in the Settings drawer under the Preferences tab (`/settings?tab=prefs#income-anchor`) — see [ADR-0031](adr/0031-budget-page-composition-v2.md). The `POST /budget/preferences/income-anchor` endpoint URL is unchanged.
- **F4.8** `/budget` renders a **Yearly budget table** below the Rules section: rows = live expense categories, columns = Jan..Dec of the selected year, each cell = the F4.2-resolved budget for that `(category, year, month)` triple with typography encoding tier dominance (bold = one-off override, italic = recurring override, plain = default, em-dash = unset). Cells are inline-editable; edits submit to the existing one-off endpoint (`POST /budget/one-off/{category_id}/{year}/{month}`), with empty value clearing the one-off override. Row + column totals render in the table footers. Year selection via a sibling picker; HTMX fragment `GET /budget/yearly?year=…` services year switches. See [ADR-0031](adr/0031-budget-page-composition-v2.md).

### 2.5 Forecasting

- **F5.1** Long-term fortune forecast across accounts and in aggregate (base currency = PLN by default, configurable).
- **F5.2** **Deterministic projection**: `projected_balance(account, date) = current_balance(today) + Σ planned_txns + Σ virtual_recurring_occurrences + Σ budget_overlay_events` up to `date`. The **budget overlay** materialises per-category per-month residual budget — `unaccounted(c, m) = max(resolved_budget(c, m) − spent_so_far(c, m) − committed_future(c, m), 0)` — as synthetic expense events distributed evenly across the remaining days of each month inside the horizon, allocated to the first active account (deterministic by `id`). Clamped per category — a category whose planned+recurring already exceeds its budget does not generate income. Overlay is on by default; the service accepts `include_budget_overlay=False` for the pre-overlay projection exercised by targeted unit tests. See [ADR-0042](adr/0042-forecast-budget-overlay.md). Cross-currency aggregation uses the latest cached FX rate.
- **F5.3** Live-updating via HTMX fragment swap: every edit to planned/recurring/account state triggers a server-side recomputation and chart redraw.
- **F5.4** Horizon selectable by the user in **months** (default 12, min 1, max 60). See [ADR-0043](adr/0043-forecast-tab-monthly-horizon-and-table.md).
- **F5.5** The Forecast surface renders a **monthly breakdown table** below the chart with one row per month in the horizon: *Month · Income · Expenses · Planned budget · Net · Projected balance (EOM)*, all in `base_currency`. For the **current calendar-month row**, `Expenses` and `Planned budget` are sourced from `services.budget.month_summary.totals` — `Expenses = totals.committed_minor` (anchor-window-aware per ADR-0041), `Planned budget = max(totals.remaining_minor, 0)` — so the row matches the Budget page's "remaining" and Overview's "committed (recurring + planned)" sub-line. For **future rows**, `Expenses` sums signed planned + recurring events landing in that calendar month, and `Planned budget = Σ max(resolve_budget(cat, m) − spent_so_far(cat, m) − committed_future(cat, m), 0)` across live expense categories (clamped per ADR-0042). `Net = Income − Expenses − Planned budget`. `Projected balance (EOM)` uses the ADR-0042 overlay-on daily projection so the current-month row absorbs remaining planned events + remaining-budget synthetic spend. Chart renders at **monthly granularity** (one EOM point per month) rather than daily. Chart + table swap atomically on `forecast-stale`. See [ADR-0043](adr/0043-forecast-tab-monthly-horizon-and-table.md).
- **F5.6** Forecast is a first-class nav entry in the primary rail (keyboard shortcut `g f`).

### 2.6 Analytics

- **F6.1** Analytics view over the persistent transaction log.
- **F6.2** Graphs: spend by category over time, income vs expense trend, cash-flow by account, top categories per month.
- **F6.3** Groupable by category, account, direction, month/quarter/year.
- **F6.4** All graphs interactive (Plotly).

### 2.7 Multi-Currency

- **F7.1** Each account has an immutable `currency` set at creation.
- **F7.2** Transactions inherit the currency of their account (not stored on the transaction row).
- **F7.3** A `base_currency` configured in the application config (default: `PLN`). All aggregates (fortune, budget, forecast, analytics) converted into base currency for display.
- **F7.4** FX rates fetched from the ECB via `frankfurter.app` on demand, cached in a local `fx_rates(date, from_ccy, to_ccy, rate)` table. **Historical rates used for historical transaction conversion** (a transaction on 2026-01-15 converts at the 2026-01-15 rate, not today's). Fallback to the last-known rate if the API is unreachable.
- **F7.5** Transits across currencies are **blocked at the validation layer** in v1.

---

## 3. Non-Functional Requirements

### 3.1 Technology

- Python 3.12.
- SQLite (OLTP). DuckDB attach deferred to a later iteration if analytics queries become slow.
- FastAPI + HTMX + Jinja2 (templates) + Tailwind CSS (compiled via local Tailwind CLI, output to `static/tailwind.css`; see [ADR-0027](adr/0027-frontend-toolchain-hardening.md)).
- Plotly for charts.
- `uv` for Python dependency and virtual-environment management.
- `npm` for the small dev-only Node toolchain (`tailwindcss`, `stylelint`, `pixelmatch`, Playwright). See [ADR-0027](adr/0027-frontend-toolchain-hardening.md).
- `just` as the task runner.

### 3.2 Testing

- Unit test coverage ≥ 90% enforced in CI (bar raised above the 80% minimum requested, because the codebase is functional and pure).
- Integration tests cover: database layer, FX-rate resolver, forecast engine, planned→actual promotion, reconciliation flow.
- End-to-end smoke tests (Playwright or `httpx` + Jinja fixtures) cover the critical user flows.

### 3.3 Code Style

- Functional-first: pure functions, immutable data (dataclasses `frozen=True`), no OO beyond dataclasses / Pydantic DTOs / Protocols.
- DRY: shared repository/service layer across views; one place for query helpers.
- Type-checked with `mypy --strict`.
- Formatted and linted with `ruff` (replaces `black` + `isort` + `flake8`; `black`-compatible output).
- SQL formatted/linted with `sqlfluff`.
- Jinja templates linted with `djlint`.
- Hand-authored CSS (`static/*.css`, excluding generated `tailwind.css`) linted with `stylelint`. See [ADR-0027](adr/0027-frontend-toolchain-hardening.md).

### 3.4 Pre-commit

Hooks: `ruff`, `ruff-format`, `mypy`, `pytest` (fast subset), `sqlfluff`, `djlint`, `stylelint`, `tailwind-check` (fails if `static/tailwind.css` is stale vs. content globs), `bandit`, `detect-secrets`, and the standard pre-commit stdlib hooks (trailing whitespace, EOF newline, large file check, yaml/toml validate). See [ADR-0027](adr/0027-frontend-toolchain-hardening.md) for the three new hooks.

### 3.5 Developer Experience

- `just dev` — run the app with hot reload.
- `just css` — build `static/tailwind.css` once from source.
- `just css-watch` — watch mode for Tailwind, run alongside `just dev`.
- `just test` — run the test suite with coverage.
- `just test-visual` — run Playwright visual-regression snapshot tests (opt-in; not part of `just ci` by default).
- `just test-visual-update` — regenerate visual-regression baselines after an intentional design change.
- `just lint` — run all linters.
- `just format` — autofix formatting.
- `just typecheck` — mypy strict.
- `just ci` — run everything CI runs.
- `just db-reset` — recreate the dev database.
- `just seed` — seed default categories, demo accounts.

Local setup runs both `uv sync` (Python) and `npm ci` (Node dev toolchain) through `just install`.

### 3.6 CI

- GitHub Actions.
- Single matrix row: `ubuntu-latest` + Python 3.12 + Node 20 (dev-only, for the Tailwind + stylelint + Playwright toolchain).
- Setup steps: `actions/setup-python@v5` + `actions/setup-node@v4` + `npm ci`.
- Runs `just ci` on push/PR.
- Coverage uploaded as artifact.
- Visual-regression suite (`just test-visual`) is **not** run in default CI; it is opt-in via `CI_VISUAL=1` on manual workflow dispatch. See [ADR-0027](adr/0027-frontend-toolchain-hardening.md).

### 3.7 Data Semantics

- **Amounts**: positive integer minor units. Direction derived from `category.direction`. Exception: adjustments (reconciliation) may be signed to encode inflow/outflow.
- **Timestamps**: `created_at` / `updated_at` columns stored as UTC. User-facing dates on transactions stored as DATE (no time component). Display timezone = `Europe/Warsaw` by default, configurable.
- **Soft delete**: every mutable table has `deleted_at` nullable timestamp. All queries filter `WHERE deleted_at IS NULL` via a repository helper.
- **Audit**: shared polymorphic `audit_log(id, entity_type, entity_id, changed_at, operation, prev_json, new_json)` written on every mutation.
- **Multi-user scaffold**: every user-owned table has a nullable `user_id` column (defaults to `1`), unused in v1, ready for future auth. **v3 activates this scaffold** — see [§6.9](#69-multi-user-scope-added-2026-10-30-adr-0061) and [ADR-0061](adr/0061-v3-multi-user-admin-bootstrap-and-data-isolation.md); the `DEFAULT 1` is dropped by migration `0012_multi_user.sql`.

### 3.9 UI / Interaction Model

- **Information architecture.** Four top-level nav items in a left rail: **Overview**, **Ledger**, **Accounts**, **Budget**. One Settings affordance at the bottom opens a slide-over drawer; Settings is not a top-level tab. Legacy routes (`/transactions`, `/planned`, `/recurring`, `/categories`, `/analytics`) continue to resolve via 302 redirects for one release before Phase 7 cleanup. See [ADR-0023](adr/0023-ux-redesign-information-architecture.md).
- **Overview `/`.** Three panels: (1) all accounts with per-account balance + base-currency summed total, (2) current-month budget stats with **amount left** as the headline number, a second-line **"left per day"** figure sourced from the same `MonthSummary.left_daily_spend_minor` that powers the Budget hero (F4.6), plus spent/of + days-left (`MonthSummary.days_until_next_income` — paycheck-cycle cutoff per [ADR-0041](adr/0041-budget-period-anchor-window.md), end-of-month fallback) + pace tag, plus a dim sub-line `"X committed (recurring + planned)"` reflecting [ADR-0039](adr/0039-budget-daily-spend-includes-recurring.md), (3) **Upcoming**: the sorted union of (a) persisted planned one-offs with `operation_date` inside the window and (b) active recurring rules whose `next_due` falls inside the window (date rendered from `rule.next_due`, override-applied if an override targets `next_due`). The union is composed by `services.upcoming.list_upcoming(window)`; **virtual recurring occurrences no longer flow through `services.planned.list_planned`** (ADR-0038). Rows carry a `kind` discriminator (`"planned"` | `"recurring"`) so the row partial renders the right action set (promote-planned vs. promote-recurring). Rows where effective-date `>= today` render at full emphasis; rows where effective-date `< today` (overdue, planned only) render muted + italic with an `overdue` chip. Already-promoted planned rows do not appear. The panel header groups both affordances in one cluster — `+ Planned` + `+ Recurring` — rendered as a shared `.panel__add-group` so the pair sits visually together ([ADR-0030](adr/0030-shared-form-interaction-primitives.md) spacing tokens).
- **Ledger `/ledger`.** One shell renders Actual | Planned | Recurring behind a segmented control; filter and column shape are shared. The fragment route `/ledger/table?view=…` dispatches to existing repository queries. Keyboard `[` and `]` cycle the segmented control. **Planned** lists only persisted one-off `planned_transactions`; no virtual recurring rows (ADR-0038). **Recurring** lists all live `recurring_rules` with columns `cadence | next_due | account | category | amount | active | actions`. The actions column exposes **Promote**, **Override next…**, **Skip next**, **Edit**, **Delete**: Promote posts to `POST /recurring/{id}/promote` (opens a confirm modal pre-filled from `rule.default_amount`/`description` with any override on `next_due` layered on top); Override-next opens the existing `POST /recurring/{id}/overrides` slide-over pre-filled with `occurrence_date = rule.next_due`; Skip-next posts to `POST /recurring/{id}/skip-next`; Edit opens the rule edit slide-over; Delete posts to the existing `POST /recurring/{id}/deactivate` (soft delete via `active=0`).
- **Settings drawer.** `/settings?tab=categories|fx|prefs` returns the drawer HTML; drawer is injected into a persistent `#drawer-root`. Opens via gear icon or `g s`. The Preferences tab (`?tab=prefs`) owns the income-anchor selector (F4.7, [ADR-0031](adr/0031-budget-page-composition-v2.md)) and is the home for all future per-user preferences ([ADR-0025](adr/0025-user-preferences-and-income-anchor.md)).
- **Form primitives.** All create / edit forms share a small primitive set per [ADR-0030](adr/0030-shared-form-interaction-primitives.md): `<input type="date">` on create defaults to today; `amount` inputs restrict to digits + decimal separator client-side; id-reference `<select>`s become filterable comboboxes (case-insensitive substring match on label); every modal / slide-over carries a visible close button; create forms clear their inputs after a successful 2xx submit; conditional fields (today only: liability credit-limit) hide at both the markup and the a11y layer when their trigger toggle is off.
- **Command palette.** `⌘K` / `Ctrl K` opens an Alfred-style popover for navigation and quick actions. Vanilla JS (no framework), ~60 lines total.
- **Keyboard shortcuts.** `g o / g l / g a / g b / g s` navigate. `n` opens the context-aware Quick-add form. `/` focuses the active page's search/filter. `[` / `]` cycle Ledger segmented control. `?` opens the cheatsheet. `⎋` closes the topmost overlay. All guards against capturing keys inside `<input>` / `<textarea>` / `[contenteditable]`.
- **Quick-add FAB.** Fixed bottom-right. Click or `n`. Form shape is derived from the active Ledger tab (or defaults to actual transaction on Overview / Accounts).
- **Design direction.** Editorial / Swiss, per [ADR-0023](adr/0023-ux-redesign-information-architecture.md) continuing [T-053](plans/v1/phase-5/T-053-visual-polish.md): oklch palette, hairline elevation, tabular numerals, one display + one text + one mono face, single accent colour. No dark mode, no mobile adaptive nav, no icon system in v1.
- **Overlay stack.** Only one overlay (drawer, modal, palette) responds to Esc at a time; stack managed by `static/js/overlay-stack.js`.

---

### 3.8 Out of Scope for v1

- CSV import from banks (deferred past v1; not scheduled for v2 or v3 either; see [ADR-0020](adr/0020-import-deferred-export-v1.md)).
- Multi-user authentication (**promoted into v3** — see [§6.9](#69-multi-user-scope-added-2026-10-30-adr-0061) and [ADR-0061](adr/0061-v3-multi-user-admin-bootstrap-and-data-isolation.md); kept here for v1 historical scope).
- Cross-currency transits.
- ML/trend-based forecasting.
- Rollover budgets.
- Hierarchical categories.
- Background scheduling / cron jobs.

---

## 4. Deliverables

- Running local web app satisfying all functional requirements above.
- CI green on `main`.
- `docs/` kept in sync with code (ADRs for every meaningful change).
- `README.md` with run instructions.

---

## 5. v2 — Rising Dough Redesign Scope (added 2026-10-28)

v2 keeps v1's functional surface and data model unchanged and layers a full UI/UX redesign on top, codenamed **Rising Dough**. The product is renamed Rising Dough and adopts the editorial / Swiss design system defined in `docs/application_redesign_handoff/`. Full plan: `docs/plans/v2/`. Decisions: ADR-0050..ADR-0056 (to be minted — see the plan).

### 5.1 Scope

- Rename **Budget Planner → Rising Dough** (wordmark only; package name, DB name, repo name all stay `budget_planner`).
- New information architecture: top-level nav **Today · Ledger · Plan · Accounts** with Settings pinned at the bottom. Replaces v1 **Overview · Ledger · Accounts · Budget** + separate Forecast + settings drawer.
- Design system: OKLCH warm-neutral palette with one accent (indigo H265), hairline elevation, three typefaces (Newsreader display, Hanken Grotesk body, IBM Plex Mono numerals), tabular numerals everywhere money appears.
- Rebuilt screens: Today, Ledger (Actual · Planned · Recurring), Plan (Budget · Year · Forecast · Analytics), Accounts, Settings (Categories · Currency & FX · Preferences), Reconcile slide-over, Add-entry modal (Fixed / Formula), Create account, Create category.
- Responsive to **mobile**: ≤ 640px uses a bottom tab bar with a centre `+ Add` sheet; between 641 and 1099 the sidebar collapses to a top bar; ≥ 1100 keeps the left rail.
- Settings becomes a dedicated page (`/settings`) with its own tabs — the v1 slide-over drawer is retired.
- The floating Quick-add FAB is removed; **+ Add** lives in the top bar (desktop) / centre tab (mobile).
- Jinja macros for every new primitive: `amount`, `category_pill`, `direction_badge`, `pace_tag`, `overdue_chip`, `table_row`, `heatmap_cell`, `segmented_bar`.
- Charts switch from **Plotly to Jinja-rendered SVG** on the Forecast and Analytics surfaces (smaller bundle, on-brand, accessible with data-table fallbacks).
- Server-rendered inline interactions: **promote-in-place** on Upcoming / Ledger rows, cell edit popover on Plan · Year, "can I afford" live preview on Today, formula-term live preview on Add.
- Backend additions implied by the design (see §5.4).
- Deferred: command palette (`⌘K`), dark mode, hover-only row-action visibility on Recurring, additional currency examples. These are explicitly out of v2 scope per the handoff `docs/application_redesign_handoff/docs/07-open-items.md`.

### 5.2 Non-functional

- **Toolchain upgrade**: Tailwind v4 with design tokens in CSS (`@theme` block fed by `tokens.css`). Self-hosted variable `woff2` fonts (Newsreader, Hanken Grotesk, IBM Plex Mono).
- **Accessibility**: WCAG 2.1 AA preserved — contrast figures from `docs/application_redesign_handoff/docs/01-visual-direction.md`, no colour-only state cues, `prefers-reduced-motion` respected, data-table equivalents for every chart.
- **Visual regression**: baseline images regenerated at desktop (1440) · tablet (1024) · mobile (375) viewports for every rebuilt screen. CI remains opt-in per ADR-0027; the v2 release gate runs the suite manually.
- **Routes**: v1 URL shape (`/`, `/ledger`, `/budget`, `/accounts`, `/forecast`, `/categories`, `/transactions`, `/planned`, `/recurring`, `/settings`) is **preserved** by server-side 302 redirects to the new IA for one release before cleanup. New canonical routes: `/today`, `/ledger?view=actual|planned|recurring`, `/plan?tab=budget|year|forecast|analytics`, `/accounts`, `/settings?tab=categories|fx|prefs`.

### 5.3 Data model

- Zero schema changes required by the redesign itself. The design is a presentational re-skin + IA consolidation.
- Soft-delete, audit log, categories, accounts, transactions, planned, recurring rules, overrides, budget tiers, FX cache all keep their v1 shapes.

### 5.4 Backend additions

| Endpoint | Purpose | Notes |
|---|---|---|
| `GET /today/afford?amount=` | Returns recomputed left-per-day given an input purchase | Debounced live preview; pure service call. |
| `POST /recurring/formula/preview` | Returns computed value for a draft formula term list | Used by Add-entry formula builder; validates cycles / non-positive before save. |
| `GET /accounts/last-checked` | Latest snapshot or reconcile date per account | Powers the "last checked" column on Accounts. |
| `GET /plan/analytics` | Spend by category for selected period + 12-month averages + income-vs-expense + largest items | Replaces Plotly-backed `/analytics` with server-rendered SVG + table. |
| `POST /categories/{id}/archive` + `POST /categories/{id}/restore` | Archive / restore category | Soft-delete via existing repository helper. |
| `POST /recurring/batch/promote-due` | Promote every rule due today or overdue | Returns a toast with Undo (soft-delete makes undo safe). |

All endpoints follow the existing router → service → repository → SQL stack. No new persistence tables.

### 5.5 Deliverables

- All v2 ADRs (0050..0056) Accepted.
- `docs/plans/v2/` phases 1–7 complete with `✅` on every task (see `tasks.md`).
- `/today`, `/ledger`, `/plan`, `/accounts`, `/settings` all render the Rising Dough design at desktop + tablet + mobile viewports with no `horizontalScroll` / overflow findings from `frontend-visual-audit`.
- Visual-regression baselines regenerated and committed.
- The wordmark "Rising Dough" shipping in the header; `budget_planner` package name retained.
- Dated entry in `docs/CHANGELOG.md` on first merge of §5 scope.

### 5.6 Non-goals for v2

Explicitly out of v2 scope (require ADR before promotion):

- Dark mode or additional themes.
- `⌘K` command palette (kept as design reference only — see handoff screen 1m).
- CSV import from banks (still deferred — ADR-0020).
- Any schema change.
- Remote deployment, authentication, infrastructure, monitoring — those live in v3 (§6).
- Multi-user authentication (**promoted into v3** — see [§6.9](#69-multi-user-scope-added-2026-10-30-adr-0061) and [ADR-0061](adr/0061-v3-multi-user-admin-bootstrap-and-data-isolation.md); remains out of v2).

### 5.7 Dependencies on v3

v2 ships against the local `127.0.0.1` server (ADR-0005). v3 (§6) picks up the redesigned app and makes it internet-reachable. v3 depends on v2 shipping; v2 does not depend on v3.

---

## 6. v3 — Remote Deployment Scope (added 2026-10-27 as v2; renumbered to v3 on 2026-10-28)

v3 keeps the v2-redesigned functional surface unchanged and layers a hardened public-internet deployment on top. Full plan: `docs/plans/v3/`. Decisions: ADR-0032..ADR-0037.

### 6.1 Deployment target

- **Compute**: Scaleway Stardust `STARDUST1-S` in region `pl-waw` zone `pl-waw-1` (Warsaw).
- **Durability**: Scaleway Object Storage bucket `budget-planner-prod-pl-waw` with Litestream continuous replication.
- **TLS**: Caddy auto-HTTPS via Let's Encrypt (ACME HTTP-01).
- **DNS**: operator-owned domain, A + AAAA records managed by Terraform.
- **Server bind**: inside the container, `0.0.0.0:8000` (Caddy terminates TLS and proxies to it). ADR-0005's `127.0.0.1` constraint applies only to v1 local use.

### 6.2 Authentication (new; multi-user per ADR-0061)

- **Model**: multi-user, admin-gated. One admin bootstrapped by Terraform at first boot; admin manages the user list but does **not** see other users' data. See [ADR-0061](adr/0061-v3-multi-user-admin-bootstrap-and-data-isolation.md).
- **Primary credential**: per-user password (bcrypt-hashed). Each user may additionally register their own passkeys (WebAuthn via `py_webauthn`) after logging in. No self-signup; user creation is admin-only.
- **Admin bootstrap**: Terraform generates `admin_initial_password`; cloud-init injects `BUDGET_PLANNER_ADMIN_EMAIL` + `BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD`; the app's startup hook creates the admin idempotently and flags `must_change_password=1` so the first login forces rotation. Terraform exposes the password as a sensitive output; operator captures it once.
- **Session**: signed `__Host-session` cookie, 7-day sliding expiry, revocable per session via `/auth/sessions`. Sessions are per-user; deleting a user revokes all their sessions in the same transaction.
- **CSRF**: `__Host-csrf` cookie + `X-CSRF-Token` header enforced on all state-changing routes.
- **Rate limit + jail**: 3 attempts / 15 min on `/auth/login` per IP; `fail2ban` jail reading Caddy's access log.
- **Admin surface**: `/settings/users` (list, add, edit, remove, reset password) — admin-only, returns 404 to non-admins to avoid surface fingerprinting. `/settings/password` is available to every user to change their own password.

### 6.3 Infrastructure as Code (new NFR)

- All Scaleway resources (project, IAM app + policy + key, instance, Flex IP, security group, object storage bucket, DNS records) are managed by **Terraform** (ADR-0035). No OpenTofu, no click-ops.
- Terraform state lives in a bootstrap Scaleway Object Storage bucket (`budget-planner-tfstate-pl-waw`) created once out-of-band.
- Two environments: `prod` and `drill` (disposable).

### 6.4 Deployment pipeline (new NFR)

- GitHub Actions: `build.yml` (image + cosign) → `deploy.yml` (SSH to deploy user, auto-rollback on `/ready` probe failure).
- Deploy user has `/usr/sbin/nologin` + `command=".../deploy-budget-planner"` restriction. No arbitrary SSH.
- Immutable SHA-tagged images; cosign keyless via GitHub OIDC.
- Prod deploy requires explicit `prod` environment approval; drill deploys automatically.
- Rollback is one SSH call or one `workflow_dispatch`.

### 6.5 Durability (amends §3.7 for v3)

- SQLite file at `/data/budget.db` with `journal_mode=WAL`, `synchronous=NORMAL`, `wal_autocheckpoint=0`, `busy_timeout=5000` (ADR-0034).
- Litestream sidecar streams WAL to Scaleway Object Storage every ≤10 s.
- 30-day retention, daily snapshots.
- RPO ≤ 15 s. RTO target < 60 min for full re-provision.
- Monthly automated restore drill opens a GitHub issue on failure.

### 6.6 Observability (new NFR, minimal)

- `/health` (liveness) + `/ready` (readiness, DB-aware) endpoints, public.
- Structured JSON logs on stdout via `structlog`; request-id propagation.
- UptimeRobot (or Betterstack free) hits `/health` every 5 min; email alert.
- Scaleway cost alert at 2× expected monthly cost (PLN).

### 6.7 Security (new NFR)

- CSP with per-request nonce (Caddy injects, app propagates to Jinja).
- HSTS preload, X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy strict-origin-when-cross-origin, Permissions-Policy minimal.
- `trivy` + `pip-audit` block on HIGH/CRITICAL in CI.
- `testssl.sh` grade A, Mozilla Observatory ≥ A+ required pre-go-live.
- UFW default-deny; only 22/80/443 allowed. `fail2ban` jails on `sshd` + `caddy-auth`.

### 6.8 Non-goals for v3

Explicitly out of v3 scope (require ADR before promotion):

- Self-signup / public registration. User creation remains admin-only (ADR-0061).
- Multi-admin impersonation ("login as") or admin visibility into user data.
- "Forgot password" email flow. Admin reset is the only recovery path (ADR-0061).
- External IdP (GitHub / Google OIDC) or per-user API tokens.
- Hard-delete flows for user data (soft-delete only; see ADR-0061 §Consequences).
- Autoscaling or multi-instance.
- Cross-region replication of the Litestream bucket.
- Centralised log store or distributed tracing.
- CDN or edge caching.
- CSV import from banks (remains deferred — see ADR-0020).

### 6.9 Multi-User Scope (added 2026-10-30; ADR-0061)

- **Capacity target**: order-of-magnitude 10 users on the Stardust1-S host. Vertical bump to Pro2-S noted as future knob if load requires. SQLite single-writer ceiling (~100 concurrent writers) remains the long-term limit.
- **Roles**: `is_admin` boolean on `users`. One admin bootstrapped at provisioning; any admin can promote another user. The last admin cannot be deleted or demoted.
- **Data isolation**: every user-owned table (`accounts`, `categories`, `transactions`, `planned_transactions`, `recurring_rules`, `budget_defaults`, `budget_recurring_overrides`, `budget_one_off_overrides`, `user_preferences`) is filtered on `user_id = current_user.id` in every repository query. `account_snapshots` and `recurring_rule_overrides` are scoped via join through their parent FK. `fx_rates` is global. The admin cannot see other users' data.
- **Admin panel**: `/settings/users` — list / add (auto-generated password shown once) / edit (email, name, is_admin toggle) / reset password / remove (soft-delete + session revoke).
- **Password change**: `/settings/password` — all users. Requires current password. Clears `must_change_password` flag; revokes all other sessions of the same user.
- **Schema**: migration `0012_multi_user.sql` extends `users` with `email`, `is_admin`, `must_change_password`, `updated_at`, `deleted_at`; drops the `DEFAULT 1` sentinel on every user-owned FK. Legacy `user_id = 1` data is preserved as the bootstrapped admin's own history. See ADR-0061. <!-- pragma: allowlist secret -->
- **Static-analysis guard**: a CI test parses each repository module's SQL and fails if a SELECT/UPDATE/DELETE against a user-owned table lacks a `user_id` filter.

### 6.10 Deliverables

- All seven v3 ADRs (0032–0037 + 0061) Accepted.
- `docs/plans/v3/` phases 1–4 complete with `✅` on every task.
- Production deployment running at the agreed hostname with Observatory ≥ A+.
- First restore drill logged in `docs/plans/v3/runbooks/restore-log.md`.
- Monthly automated restore drill scheduled.
- Operator captured the `admin_initial_password` into a password manager; admin has logged in, rotated the password, and (optionally) registered at least one passkey.
- Dated go-live entry in `docs/CHANGELOG.md`.
