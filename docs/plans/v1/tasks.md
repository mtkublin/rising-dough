# Budget Planner — Implementation Tasks

> Each task is scoped to be picked up by a subsequent agent (or human) with minimal cross-coordination. Dependencies noted inline. Tasks are grouped by phase; within a phase, parallel-safe tasks are marked `[P]`.
>
> Acceptance = passing tests + `just ci` green + relevant ADR referenced.

Legend:
- `[P]` = parallel-safe within its phase.
- `[S]` = sequential, must complete before next in phase.
- `→ T-xxx` = depends on task.

---

## Phase 0 — Repository Bootstrap

### ✅ T-001 [S] Repository scaffolding
- Initialize `pyproject.toml` with `uv` (Python 3.12).
- Dependencies: `fastapi`, `uvicorn[standard]`, `jinja2`, `pydantic`, `pydantic-settings`, `python-multipart`, `plotly`, `pandas` (for parquet export), `pyarrow`, `httpx` (FX fetch), `python-dateutil`.
- Dev dependencies: `ruff`, `mypy`, `pytest`, `pytest-cov`, `pytest-asyncio`, `playwright` (optional), `sqlfluff`, `djlint`, `bandit`, `detect-secrets`, `pre-commit`.
- Create directory skeleton:
  ```
  src/budget_planner/
    __init__.py
    config.py
    db/
    domain/
    services/
    repositories/
    web/
      routers/
      templates/
      static/
    adapters/
      fx/
      export/
  tests/
    unit/
    integration/
    e2e/
  migrations/
  docs/
  ```
- Reference: ADR-0002, ADR-0004.

### ✅ T-002 [S] Justfile + CI → T-001
- `justfile` with: `dev`, `test`, `lint`, `format`, `typecheck`, `ci`, `db-reset`, `seed`, `migrate`.
- `.github/workflows/ci.yml` running `just ci` on push/PR on `ubuntu-latest` + Python 3.12.
- Coverage artifact uploaded.
- Reference: ADR-0019, ADR-0021.

### ✅ T-003 [S] Pre-commit stack → T-001
- `.pre-commit-config.yaml` with: `ruff`, `ruff-format`, `mypy`, `sqlfluff`, `djlint`, `bandit`, `detect-secrets`, standard stdlib hooks.
- `pyproject.toml` configs for ruff, mypy (strict), coverage threshold (90%).
- `just install-hooks` recipe.
- Reference: ADR-0020.

### ✅ T-004 [S] Config module → T-001
- `src/budget_planner/config.py` using `pydantic-settings`.
- Fields: `database_url`, `base_currency` (default `PLN`), `display_timezone` (default `Europe/Warsaw`), `host` (`127.0.0.1`), `port` (`8000`), `fx_api_url`.
- `.env.example` committed; `.env` gitignored.

---

## Phase 1 — Data Layer

### ✅ T-010 [S] Migration framework → T-004
- Pick lightweight migration tool: `yoyo-migrations` (SQL-first, simple) or hand-rolled numbered `.sql` files + runner.
- **Decision**: hand-rolled numbered `.sql` files in `migrations/`; runner in `src/budget_planner/db/migrate.py`.
- `just migrate` applies all pending migrations.

### ✅ T-011 [S] Core schema migration → T-010

Tables:
- `users(id, name, created_at)` — single seed row for v1.
- `accounts(id, user_id, name UNIQUE, type, currency, opening_balance, created_at, updated_at, deleted_at)`.
- `categories(id, user_id, name UNIQUE, direction CHECK IN ('income','expense','transit','adjustment'), created_at, updated_at, deleted_at)`.
- `transactions(id, user_id, operation_date, category_id, account_id, dest_account_id NULLABLE, amount, description, promoted_from_planned_id NULLABLE, created_at, updated_at, deleted_at)`.
- `planned_transactions(id, user_id, operation_date, category_id, account_id, dest_account_id NULLABLE, amount, description, recurring_rule_id NULLABLE, occurrence_date NULLABLE, promoted_to_txn_id NULLABLE, created_at, updated_at, deleted_at)`.
- `recurring_rules(id, user_id, cadence CHECK IN ('monthly','quarterly','yearly'), start_date, end_date NULLABLE, category_id, account_id, dest_account_id NULLABLE, default_amount, default_description, day_of_month NULLABLE, month_of_year NULLABLE, active, created_at, updated_at, deleted_at)`.
- `recurring_rule_overrides(id, rule_id, occurrence_date, state CHECK IN ('skipped','overridden'), amount_override NULLABLE, description_override NULLABLE, date_override NULLABLE, created_at)`.
- `budget_defaults(id, user_id, category_id UNIQUE, amount)`.
- `budget_recurring_overrides(id, user_id, category_id, month CHECK 1-12, amount, UNIQUE(category_id, month))`.
- `budget_one_off_overrides(id, user_id, category_id, year, month, amount, UNIQUE(category_id, year, month))`.
- `account_snapshots(id, account_id, taken_at, balance, note)`.
- `fx_rates(id, date, from_ccy, to_ccy, rate, UNIQUE(date, from_ccy, to_ccy))`.
- `audit_log(id, entity_type, entity_id, changed_at, operation CHECK IN ('create','update','delete','undelete'), prev_json, new_json)`.

Indexes:
- `transactions(operation_date)`, `transactions(account_id)`, `transactions(category_id)`.
- `planned_transactions(operation_date)`.
- `fx_rates(date, from_ccy, to_ccy)`.

Reference: ADR-0008, ADR-0009, ADR-0010, ADR-0011, ADR-0013.

### ✅ T-012 [S] Seed data migration → T-011
- Seed single `users` row (`id=1, name='default'`).
- Seed system categories: `Transit` (direction=transit), `Reconciliation` (direction=adjustment).
- These must be undeletable (enforced in service layer).

### ✅ T-013 [P] Repository layer → T-011
- `src/budget_planner/repositories/` — one module per entity (`transactions.py`, `accounts.py`, `categories.py`, `planned.py`, `recurring.py`, `budgets.py`, `snapshots.py`, `fx.py`).
- Each module exposes pure functions (no classes). Signature pattern:
  ```python
  def find_by_id(conn: Connection, entity_id: int) -> Entity | None: ...
  def list_filtered(conn: Connection, filters: Filters) -> list[Entity]: ...
  def create(conn: Connection, data: NewEntity) -> Entity: ...
  def update(conn: Connection, entity_id: int, data: PatchEntity) -> Entity: ...
  def soft_delete(conn: Connection, entity_id: int) -> None: ...
  ```
- All mutating functions write to `audit_log` in the same transaction.
- All read functions filter `deleted_at IS NULL` by default; accept `include_deleted: bool = False` kwarg.
- Reference: ADR-0022.

### ✅ T-014 [P] Domain types → T-011
- `src/budget_planner/domain/` — frozen dataclasses or Pydantic models for every entity + DTOs (`NewTransaction`, `PatchTransaction`, `TransactionFilter`, etc).
- `Direction` enum: `income`, `expense`, `transit`, `adjustment`.
- `Cadence` enum: `monthly`, `quarterly`, `yearly`.
- Money helpers: `to_minor_units(decimal) -> int`, `from_minor_units(int) -> Decimal`, formatter respecting currency decimals.

---

## Phase 2 — Services (Pure Business Logic)

### ✅ T-020 [P] FX service → T-013, T-014
- `src/budget_planner/services/fx.py`.
- `get_rate(conn, date, from_ccy, to_ccy) -> Decimal`:
    - Return `1.0` if `from == to`.
    - Lookup `fx_rates`; if present return.
    - Else fetch from `frankfurter.app`; insert; return.
    - On API error, return the most recent `rate` for that pair (fallback) with a log warning.
- `convert(conn, amount_minor, date, from_ccy, to_ccy) -> int`.
- Unit-tested with mocked HTTP client.
- Reference: ADR-0008.

### ✅ T-021 [P] Balance service → T-013
- `derive_balance(conn, account_id, as_of_date | None) -> int`:
  `opening_balance + Σ (signed amount of all non-deleted txns on/before as_of_date affecting this account)`.
- Signed amount rules:
    - `income` → `+amount` on `account_id`.
    - `expense` → `-amount` on `account_id`.
    - `transit` → `-amount` on `account_id`, `+amount` on `dest_account_id`.
    - `adjustment` → `+amount` on `account_id` (amount already signed per ADR).
- `account_stats(conn, account_id) -> AccountStats`.

### ✅ T-022 [P] Recurring occurrence generator → T-013, T-014
- `generate_occurrences(rule, start_date, end_date) -> list[Occurrence]` (pure function).
    - Expand cadence: `monthly` → month-step from `start_date`; `quarterly` → every 3 months; `yearly` → yearly.
    - Clip by `end_date` of rule and query range.
    - Return virtual `Occurrence` dataclasses carrying rule defaults.
- `apply_overrides(occurrences, overrides) -> list[Occurrence]`:
    - Drop `skipped`.
    - Mutate `overridden` with override fields.
- Reference: ADR-0015.

### ✅ T-023 [P] Planned log service → T-013, T-022
- `list_planned(conn, filters) -> list[PlannedView]`: UNION of `planned_transactions` + virtual occurrences from active rules in range.
- `promote_to_actual(conn, planned_id, edits) -> Transaction`: insert into `transactions`, update `planned_transactions.promoted_to_txn_id`, write audit entries.
- Reference: ADR-0014.

### ✅ T-024 [P] Budget service → T-013
- `resolve_budget(conn, category_id, year, month) -> int | None`: null-coalesce one-off → recurring → default.
- `month_summary(conn, year, month) -> MonthSummary`: per-category budgeted/spent/remaining + analytics (avg monthly spend overall, avg this year, delta vs previous month).
- Reference: ADR-0017.

### ✅ T-025 [P] Forecast service → T-013, T-020, T-021, T-022
- `forecast(conn, horizon_days) -> ForecastSeries`:
    - For each day in horizon, project balance per account (base-currency converted via latest FX rate).
    - Return daily series + totals.
- Deterministic, pure.
- Reference: ADR-0018.

### ✅ T-026 [P] Reconciliation service → T-013, T-021
- `reconcile(conn, account_id, actual_balance_minor) -> Transaction`:
    - Compute delta = actual − derived.
    - Insert transaction: category=Reconciliation, direction=adjustment, amount=delta (signed), description=`"auto-reconciliation {date}"`.
    - Return the created transaction.
- Reference: ADR-0013.

### ✅ T-027 [P] Export service → T-013
- `export_csv(records) -> bytes`, `export_parquet(records) -> bytes`.
- Shared across txn-log, planned-log, analytics views.

### ✅ T-028 [P] Audit helper → T-013
- `write_audit(conn, entity_type, entity_id, operation, prev_json, new_json)`.
- Called from every mutating repository function.
- Reference: ADR-0022.

---

## Phase 3 — Web Layer

### ✅ T-030 [S] FastAPI app skeleton → Phase 2 complete (minus any lagging [P] tasks)
- `src/budget_planner/web/app.py` creates FastAPI app, mounts static, templates, routers.
- Jinja env with helpers: `format_money(amount, currency)`, `format_date(date)`, `direction_badge(d)`.
- HTMX included via CDN in base template.
- Tailwind CSS via CDN.
- `base.html`, `partials/` directory for HTMX fragments.
- `just dev` → `uvicorn --reload --host 127.0.0.1 --port 8000`.

### ✅ T-031 [P] Transactions router → T-030, T-013
- `GET /transactions` — list with filter sidebar; HTMX re-renders table partial on filter change.
- `GET /transactions/new` — form fragment.
- `POST /transactions` — create.
- `GET /transactions/{id}/edit` — edit form fragment.
- `POST /transactions/{id}` — update.
- `POST /transactions/{id}/delete` — soft delete.
- `GET /transactions/export?format=csv|parquet` — download filtered view.

### ✅ T-032 [P] Accounts router → T-030, T-013, T-021, T-026
- `GET /accounts` — list with derived balance + stats.
- `POST /accounts` — create.
- `POST /accounts/{id}` — update (not currency).
- `POST /accounts/{id}/delete` — soft delete.
- `POST /accounts/{id}/snapshot` — take snapshot.
- `GET /accounts/{id}/reconcile` — reconcile form.
- `POST /accounts/{id}/reconcile` — perform reconciliation.

### ✅ T-033 [P] Categories router → T-030, T-013
- `GET /categories` — list.
- `POST /categories` — create.
- `POST /categories/{id}` — update (not direction once used).
- `POST /categories/{id}/delete` — soft delete (block system cats).

### ✅ T-034 [P] Planned transactions router → T-030, T-023
- `GET /planned` — list including virtual occurrences; filter + export.
- `POST /planned` — create one-off.
- `POST /planned/{id}` — edit one-off.
- `POST /planned/{id}/promote` — promote to actual (modal with editable amount/date).
- `GET /planned/{id}/delete` — soft delete (one-off).

### ✅ T-035 [P] Recurring rules router → T-030, T-013, T-022
- `GET /recurring` — list rules + upcoming occurrences preview.
- `POST /recurring` — create rule.
- `POST /recurring/{id}` — edit rule.
- `POST /recurring/{id}/deactivate` — set `active=false`.
- `POST /recurring/{rule_id}/overrides` — add skip/override for a specific occurrence_date.
- `POST /recurring/{rule_id}/overrides/{occurrence_date}/delete` — remove override.

### ✅ T-036 [P] Budget router → T-030, T-024
- `GET /budget` — current month view with per-category spent/budgeted/remaining + analytics.
- `GET /budget/manage` — manage defaults + overrides.
- `POST /budget/defaults/{category_id}` — set default.
- `POST /budget/recurring/{category_id}/{month}` — set recurring override.
- `POST /budget/one-off/{category_id}/{year}/{month}` — set one-off override.

### ✅ T-037 [P] Forecast router → T-030, T-025
- `GET /forecast?horizon_days=N` — chart + table.
- Plotly JSON embedded; HTMX re-triggers on inputs changing in any router (via `HX-Trigger` response header `forecast-stale`).

### ✅ T-038 [P] Analytics router → T-030, T-013
- `GET /analytics` — multi-chart dashboard: spend by category, cash-flow by account, income vs expense trend, top categories per month.
- Groupby selector (category / account / direction / month-quarter-year).

### ✅ T-039 [S] Navigation + home → T-031..T-038
- Base template with left nav: Transactions, Accounts, Categories, Planned, Recurring, Budget, Forecast, Analytics.
- Home dashboard: snapshot of current month budget + fortune total + next 7 days of planned txns.

---

## Phase 4 — Testing

### ✅ T-040 [P] Unit tests
Per service and repository. Target ≥90% coverage. Pure-function heavy, mocks only for HTTP.

### ✅ T-041 [P] Integration tests
- Full repository stack against a temp SQLite file.
- FX service against mocked HTTP.
- Promotion flow: planned → actual.
- Reconciliation flow: before/after derived balance.

### ✅ T-042 [P] E2E smoke tests
- Create account, add transaction, see balance update.
- Set budget, record spend, see remaining.
- Add recurring rule, see virtual occurrences in planned view, promote one.
- Reconcile an account, confirm adjustment txn created.

### ✅ T-043 [S] Coverage gate
- `pytest --cov=src/budget_planner --cov-fail-under=90`.
- Added to `just test` and `just ci`.

---

## Phase 5 — Polish

### ✅ T-050 [P] README
- Prereqs (uv, just, Python 3.12).
- Quick start (`just install`, `just migrate`, `just seed`, `just dev`).
- Link to `docs/`.

### ✅ T-051 [P] Error handling + flash messages
- Validation errors shown inline via HTMX partials.
- Server errors returned with 4xx/5xx + user-facing message, logged with context.

### ✅ T-052 [P] Accessibility pass
- Semantic HTML in templates.
- Form labels associated.
- Keyboard-navigable.

### ✅ T-053 [P] Visual polish
- Consistent spacing, typography scale, color tokens via CSS custom properties layered on top of Tailwind.
- Avoid default template look (see global web/design-quality rule).

---

## Phase 6 — UX Redesign (IA Consolidation + Interaction Model)

> Collapses 9 top-level nav items into 4 + a Settings drawer. Adds Command palette (⌘K) + Quick-add FAB + keyboard shortcuts. No data-model change; pure web-layer refactor. Decision: [ADR-0023](../../adr/0023-ux-redesign-information-architecture.md). Detailed plan + ASCII mockups: [`phase-6/README.md`](phase-6/README.md), [`phase-6/mockups.md`](phase-6/mockups.md).

### ✅ T-060 [S] ADR-0023 + Phase 6 docs scaffolding
- Write [`docs/adr/0023-ux-redesign-information-architecture.md`](../../adr/0023-ux-redesign-information-architecture.md).
- Add Phase 6 directory + 12 task stub files under `docs/plans/v1/phase-6/`.
- Rename prior "Phase 6 — Deferred to v2" to Phase 7 (below). (The deferred bucket moved to v3 after the v2 slot was reassigned to the Rising Dough redesign on 2026-10-28.)

### ✅ T-061 [S] Base shell refactor → T-060
- Left rail + `#drawer-root` + `#modal-root` + FAB slot in `base.html`.
- Preserve Jinja block names (`title`, `head_extra`, `nav`, `main`, `scripts`).
- Reuse editorial/Swiss tokens from T-053.
- Reference: ADR-0023.

### ✅ T-062 [S] Nav partial rewrite (4-item left rail) → T-061
- `partials/_nav.html`: Overview, Ledger, Accounts, Budget + Settings affordance at bottom.
- `aria-current="page"` on active; 2 px accent left-border; `data-shortcut` attrs.
- Reference: ADR-0023.

### ✅ T-063 [P] Overview composition → T-062
- Three-panel layout: Accounts list + sum, Budget-left headline, Upcoming planned with overdue muting.
- New fragment `/overview/upcoming?window=7|30|all`.
- Reuse `services.balance.derive_balance`, `services.budget.month_summary`, `services.planned.list_planned`.
- Reference: ADR-0023.

### ✅ T-064 [P] Ledger unification → T-062
- New `routers/ledger.py` + `templates/ledger/{index,_table}.html` with Actual|Planned|Recurring segmented control.
- Fragment `/ledger/table?view=…` dispatches to existing repository queries.
- Alias old fragment routes.
- Reference: ADR-0023.

### ✅ T-065 [P] Accounts polish → T-061
- Per-card 90-day sparkline (pure SVG), inline Reconcile button, Show snapshots disclosure.
- Reference: ADR-0023.

### ✅ T-066 [P] Budget consolidation → T-061
- `/budget` with three stacked sections: Monthly summary, Rules editor, Breakdown.
- Reuse analytics figures from current `/analytics`.
- Reference: ADR-0023.

### ✅ T-067 [P] Settings drawer → T-061
- New `routers/settings.py` + `templates/settings/{_categories,_fx,_prefs}.html`.
- Slide-over right, 480 px, three internal tabs (Categories, FX, Preferences).
- Reference: ADR-0023.

### ✅ T-068 [P] Command palette + keyboard shortcuts → T-062
- `partials/_palette.html` + `static/js/palette.js` (~60 lines) + `static/js/shortcuts.js` (~40 lines) + `partials/_shortcuts.html` cheatsheet.
- Keyboard map: `g o/l/a/b/s`, `n`, `/`, `[ ]`, `?`, `⌘K`, `⎋`.
- Reference: ADR-0023.

### ✅ T-069 [P] Quick-add FAB + slide-over form → T-064
- Fixed bottom-right 56×56 accent FAB; `n` key opens.
- Context-aware against active Ledger segmented tab.
- Reference: ADR-0023.

### ✅ T-070 [S] Legacy URL redirects → T-064, T-066, T-067
- 302: `/transactions`, `/planned`, `/recurring`, `/categories`, `/analytics` → new homes.
- Preserve HTMX fragment aliases for one release.
- Reference: ADR-0023.

### ✅ T-071 [S] Accessibility re-audit on new surfaces → T-063..T-069
- Focus trap in drawer + palette; shared focus-manager; `aria-current` on new nav; reduced-motion branches.
- Topmost-overlay stack rule (drawer + modal + palette coexist).
- Reference: ADR-0023, ADR-0019 (T-052 baseline).

### ✅ T-072 [S] README + CHANGELOG update → T-071
- README: nav screenshot description, keyboard map, migration note, ADR-0023 link.
- CHANGELOG entry on landing day.

---

## Phase 7 — Liability accounts (credit cards)

Adds behavioural classification + credit limit to accounts (ADR-0024, F2.1a). Scope: accounts surface + fortune reporting. See `docs/plans/v1/phase-7/README.md`.

### ✅ T-080 [S] ADR-0024 + Phase 7 docs scaffolding
- ADR-0024, F2.1a in `docs/requirements.md`, Phase 7 README + task stubs.

### ✅ T-081 [S] Migration `0004_add_liability_columns.sql` → T-080
- `accounts.is_liability INTEGER NOT NULL DEFAULT 0 CHECK (0,1)`; `accounts.credit_limit_minor INTEGER CHECK (NULL or > 0)`.
- Idempotent additive migration; existing rows default to assets.
- Reference: `docs/plans/v1/phase-7/T-081-migration-liability-columns.md`.

### ✅ T-082 [S] Domain + repository → T-081
- `Account`, `NewAccount`, `PatchAccount` gain `is_liability: bool` + `credit_limit_minor: int | None`.
- `PatchAccount.clear_credit_limit` sentinel distinguishes "no change" from "clear to NULL".
- Repository CRUD, hydrator, audit payloads thread the two new fields.
- Reference: `docs/plans/v1/phase-7/T-082-domain-and-repository.md`.

### ✅ T-083 [S] Fortune service → T-082
- New `services/fortune.py` with `compute_fortune(conn, settings) -> FortuneTotals`.
- Both `/` and `/accounts` routers call the service; `derive_balance` / `signed_legs` untouched.
- Reference: `docs/plans/v1/phase-7/T-083-fortune-service.md`.

### ✅ T-084 [S] Web form + templates → T-083
- Account form: "Credit card (liability)" checkbox + conditional credit-limit input.
- Account card: pill, utilization strip, over-limit badge.
- Overview + Accounts: Assets / Liabilities / Net worth split.
- Reference: `docs/plans/v1/phase-7/T-084-web-form-and-templates.md`.

### ✅ T-085 [S] Transaction-form soft warning → T-084
- `GET /transactions/_limit_preview` HTMX fragment previews post-transaction utilization for a liability account.
- Soft-only: form continues to submit when `over_by > 0`.
- Reference: `docs/plans/v1/phase-7/T-085-transaction-form-soft-warning.md`.

### ✅ T-086 [S] Seed + e2e journey → T-084
- `seed.seed()` adds demo "Bank (PLN)" + "Visa (PLN)" accounts, idempotent on re-seed.
- `tests/e2e/test_credit_card_journey.py` exercises the full user flow end-to-end.
- Reference: `docs/plans/v1/phase-7/T-086-seed-and-e2e-journey.md`.

---

## Phase 8 — Post-redesign UX fixes

Driven by field-use report 2026-10-27. Scope: UX bugfix + polish only. See `docs/plans/v1/phase-8/README.md` for the root-cause analysis.

> **ID note:** these use `T-090..T-094` as successors to Phase 7 (last `T-086`). Phase 9 (user preferences, directory `phase-9/`) currently uses `T-090..T-096` and will be renumbered by its own agent to avoid collision.

### ✅ T-090 [S] Shell + rail layout fit → T-061, T-062
- `.app-shell__main` gains `min-width: 0`; wide tables scroll inside their surface, not the page.
- `.rail-nav` tightened so Settings footer fits at 720 px high.
- Reference: `docs/plans/v1/phase-8/T-090-shell-and-rail-fit.md`.

### ✅ T-091 [S] One-field-per-row forms (`.form-stack`) → T-053, T-069
- Shared `.form-stack` component replaces `grid grid-cols-2` on all five create/edit partials.
- Applies to Transactions, Planned, Recurring, Accounts, Categories.
- Reference: `docs/plans/v1/phase-8/T-091-form-stack-layout.md`.

### ✅ T-092 [S] Ledger segmented wiring → T-064
- Wrap `_table.html` in `<div id="ledger-table">` so segmented `hx-target` resolves. Preserves legacy inner ids.
- Secondary effect: FAB view-aware routing becomes reachable, closing the "no option to add Planned/Recurring" gap.
- Reference: `docs/plans/v1/phase-8/T-092-ledger-segmented-wiring.md`.

### ✅ T-093 [S] Overview upcoming interactions → T-063, T-069
- `+ Planned` button wired to `/planned/new` slide-over.
- Range segmented active state updated via `hx-swap-oob` on the segmented group.
- Reference: `docs/plans/v1/phase-8/T-093-overview-upcoming-interactions.md`.

### ✅ T-094 [S] FAB visibility scope + Budget rules affordance → T-069, T-092, ADR-0026
- `fab_target_for` returns `None` outside Overview + Ledger; `base.html` skips the include.
- Budget rules section gains an inline-edit hint; no new endpoint.
- New ADR-0026 narrows ADR-0023 affordance #4.
- Reference: `docs/plans/v1/phase-8/T-094-fab-scope-and-budget-affordance.md`.

---

## Phase 9 — Left Daily Spend

Metric `remaining ÷ days-until-next-income` surfaced on `/budget`; first per-user preference store (`user_preferences` table) holds the income anchor category. ADR-0025. See `docs/plans/v1/phase-9/README.md`.

### ✅ T-095 [S] ADR-0025 + requirements + Phase 9 docs scaffolding
- ADR-0025 user preferences + income anchor; F4.6 + F4.7 in `docs/requirements.md`; task stubs + CHANGELOG entry.

### ✅ T-096 [S] Migration `0005_user_preferences.sql` → T-095
- `user_preferences(user_id, key, value)` with `UNIQUE(user_id, key)`; no `deleted_at`, no audit (ADR-0025).

### ✅ T-097 [S] Domain + repository → T-096
- `domain/preferences.py` (`UserPreference`, `NewUserPreference`, `PREF_INCOME_ANCHOR_CATEGORY_ID`); `repositories/preferences.py` with `get` / `upsert` / `delete` in BEGIN/COMMIT, no `write_audit`.

### ✅ T-098 [S] Preferences service + income anchor resolver → T-097, T-033
- `services/preferences.py` with `get_` / `set_` / `resolve_income_anchor_category` + `InvalidAnchorCategoryError`. Direction + liveness defence at boundary; resolver permissive on stale references.

### ✅ T-099 [S] Next-planned-income lookup → T-023
- `services/planned.next_planned_for_category(conn, category_id, after, *, horizon_days=400)` reuses `list_planned` for persisted + virtual + dedup (ADR-0013); excludes promoted rows.

### ✅ T-100 [M] Left daily spend in `services/budget.py` → T-024, T-098, T-099
- `MonthSummary` grows `left_daily_spend_minor`, `next_income_date`, `days_until_next_income`, `anchor_category_name`. `month_summary(..., today=date)` injected per ADR-0007. Zero-budget → `None`; stale anchor / no planned hit → end-of-month fallback. Banker's rounding.

### ✅ T-101 [M] `/budget` card + anchor selector + endpoint → T-036, T-100
- New "Left to spend per day" hero section + "Income anchor" `<select>` on `/budget`. New `POST /budget/preferences/income-anchor` (empty body clears, non-income or unknown category → 422); emits `HX-Trigger: budget-stale`. `/budget` passes `today` in `settings.display_timezone`. 11 integration tests.

---

## Phase 10 — Frontend Toolchain Hardening → ADR-0027

Web-layer only. No service, repository, or data-model changes. Tasks follow ADR-0027 decisions 1–5 in order.

### ✅ T-102 [M] Local Tailwind build + CDN removal → ADR-0027 §1
- Add `package.json` with `tailwindcss` pinned; `tailwind.config.js` with content globs per ADR-0027.
- `just css` and `just css-watch` recipes.
- Build `src/budget_planner/web/static/tailwind.css`; wire into `base.html` with the existing `?v=<hash>` pattern.
- Remove the `cdn.tailwindcss.com` `<script>` from `base.html`.
- Pre-commit hook `tailwind-check` fails if generated CSS is stale vs. content globs.
- `just install` runs `npm ci` alongside `uv sync`.
- `frontend-visual-audit` sweep on `/`, `/ledger`, `/accounts`, `/budget` at 1440/1024/375 before marking done.

### ✅ T-103 [S] Stylelint pre-commit hook → ADR-0027 §2
- Add `stylelint` + `stylelint-config-standard` to `package.json`.
- Project override file for allowed custom-property patterns.
- Scope to `src/budget_planner/web/static/*.css`, exclude generated `tailwind.css`.
- Pre-commit hook wired; CI step runs via `npx --no-install stylelint`.

### ✅ T-104 [M] Jinja partial extraction → ADR-0027 §3
- Scaffolded `src/budget_planner/web/templates/_partials/` with five macros: `card`, `segmented`, `chip`, `slide_over_header`, `overdue_row`. Each leads with a `{# #}` block documenting inputs (name, type, nullable, default).
- `overdue_row` applied to `home/_upcoming_list.html` to prove the shape and anchor a baseline. Visual-regression suite confirms the panel renders byte-identically.
- **Follow-ups (T-108)** — apply the remaining macros across Overview, Ledger, Accounts, Budget, Settings drawer, Transaction form, Planned, Recurring call sites. Deliberately deferred to keep the Phase 10 toolchain commit tight; macros + baselines are the risky part and are in place.

### ✅ T-105 [M] Visual-regression suite → ADR-0027 §4
- `tests/visual/test_snapshots.py` drives Playwright through `sync_playwright` (no `pytest-playwright` dependency — kept the dep surface minimal); session-scoped `live_server` fixture boots `uvicorn` on a free port.
- Routes: `/`, `/ledger`, `/accounts`, `/budget`. Viewports: 1440×900, 1024×768, 375×812.
- Baselines in `tests/visual/baselines/<viewport>__<route>.png`, committed. Diff tolerance starts strict (byte-equal) — pixelmatch tolerance ≤ 0.1 pixel ratio is a Phase 10 follow-up (see T-109).
- `just test-visual` + `just test-visual-update` recipes. Visual tests are opt-in: default `pytest` run excludes them via `-m "not visual"` in `pyproject.toml` addopts.
- CI: still opt-in; default `just ci` unchanged.

### ✅ T-106 [S] CI Node toolchain + docs sync → ADR-0027 §5–§6
- `.github/workflows/ci.yml` grows an `actions/setup-node@v4` step (Node 20, npm cache) + `npm ci` + `npm run css` before `just ci`.
- README's "Prerequisites" table + Quick start now mention the Node + npm setup; the daily-commands table lists `just css` / `just css-watch` / `just test-visual` / `just test-visual-update`.
- `CLAUDE.md` "Frontend validation" cross-links ADR-0027 (committed in the earlier docs commit).

### ✅ T-108 [M] Jinja partial extraction — remaining call sites → T-104
- Reconciled 2026-11-21 (T-Q246): landed 2026-10-27 in 1877d9d with a narrowed scope: `segmented` and `slide_over_header` applied; `card` and `chip` scaffolds dropped (design decision, needs a follow-up ADR; CHANGELOG 2026-10-27 T-108 line). The bullets below are the original plan.
- Replace open-coded duplicates for `card`, `segmented`, `chip`, and `slide_over_header` across Overview, Ledger, Accounts, Budget, Settings drawer, Transaction form, Planned, Recurring templates.
- Each swap must leave the visual-regression suite green; refresh baselines only when the design intentionally changes.

### T-109 [S] Visual-regression pixelmatch tolerance → T-105
- Reconciled 2026-11-21 (T-Q246): stays open, not done. The CHANGELOG 2026-10-27 T-108 line records it as dropped from the backlog; `tests/visual/test_snapshots.py` is still byte-equal.
- Wire `pixelmatch`'s Node CLI into `tests/visual/test_snapshots.py` so the suite tolerates ≤ 0.1 pixel ratio diffs per ADR-0027 §4. Current implementation is byte-equal and is a strict first baseline, which is fine until anti-aliasing drift between CI and local shows up.

### ✅ T-107 [S] Ledger segmented control → full-page nav → ADR-0028
- Supersedes implementation approach in T-092 for segmented tabs only; filter form and pagination keep their htmx partial swaps.
- `src/budget_planner/web/templates/ledger/index.html`: replace segmented `<button>` elements with `<a class="segmented__btn" href="/ledger?view={{ v }}">`; set `aria-current="page"` on the active tab; drop `hx-get`, `hx-target`, `hx-swap`, `hx-push-url`, `aria-pressed` from the segmented control. Keep `data-view` for the keyboard-shortcut discovery path.
- `src/budget_planner/web/static/js/shortcuts.js`: switch the `[` / `]` listener from clicking the segmented button to `location.assign(nextHref)`, and find the active tab via `aria-current="page"` instead of `aria-pressed`.
- Resolves the FAB staleness defect: `base.html` re-renders `fab_target_for(request)` on every tab switch, so the FAB opens the correct create form on Actual / Planned / Recurring.
- Tests:
  - `tests/integration/web/test_ledger.py` — segmented control renders anchors with correct `href`; `aria-current` moves with `view` param; filter form + pagination htmx wiring unchanged; `[data-ledger-table]` wrapper still ships from fragment endpoint.
  - `tests/integration/web/test_fab.py` — FAB `hx-get` matches `view` on each `/ledger?view=…` response (Actual → `/transactions/new`, Planned → `/planned/new`, Recurring → `/recurring/new`).
- `frontend-visual-audit` sweep on `/ledger?view=actual|planned|recurring` at 1440/1024/375 before marking done; confirm FAB opens the right slide-over on each view.
- Docs:
  - `docs/CHANGELOG.md` — one dated line.
  - `docs/plans/v1/tasks.md` — mark `✅ T-107` on completion.

---

## Phase 11 — Shared Form Primitives + Overview Enhancements + Budget Page v2 + Fixes

> Driven by field-use report 2026-10-27. Consolidated workstream: Budget + Account + Overview changes compose from the same shared primitives (ADR-0030); two surgical fixes (ledger row actions + transit lock) ride on the same phase. No data-model change; web-layer only. Decisions: [ADR-0030](../../adr/0030-shared-form-interaction-primitives.md), [ADR-0031](../../adr/0031-budget-page-composition-v2.md). Detailed plan: [`phase-11/README.md`](phase-11/README.md).

### ✅ T-110 [S] ADR-0030 + ADR-0031 + requirements + Phase 11 docs scaffolding
- Write [`docs/adr/0030-shared-form-interaction-primitives.md`](../../adr/0030-shared-form-interaction-primitives.md), [`docs/adr/0031-budget-page-composition-v2.md`](../../adr/0031-budget-page-composition-v2.md), update [`docs/adr/README.md`](../../adr/README.md).
- Update `docs/requirements.md`: F1.1 (shared primitives), F2.1 (slide-over + currency combobox + conditional credit limit + clear-on-save + "Credit (liability)" relabel), F2.5 (reconcile close affordance), F4.5 (+ Rule affordance), F4.6/F4.7 (anchor placement), §3.9 (Settings Preferences tab + Overview +Recurring + form primitives).
- Add Phase 11 directory with task stubs (`phase-11/README.md`, `phase-11/T-111-*.md`, `phase-11/T-112-*.md`, `phase-11/T-113-*.md`).
- Append dated line to `docs/CHANGELOG.md`.
- Docs only; no code.

### ✅ T-111 [S] Shared form primitives (combobox / digit-only amount / default date / clear-on-save / close affordance / conditional field) → T-110, ADR-0030
- New `src/budget_planner/web/templates/_partials/combobox.html` macro + `src/budget_planner/web/static/js/combobox.js` (~80 lines).
- New `src/budget_planner/web/static/js/numeric-input.js` (~30 lines) + `data-numeric` opt-in on every amount input across transactions / planned / recurring / reconcile / account opening & credit-limit / budget rule.
- Jinja global `today_local()` wired from `settings.display_timezone` (ADR-0007); every create partial sets `value="{{ today_local()|date_fmt }}"` on its date input.
- `data-reset-on-submit` attribute + `htmx:afterRequest` listener in `base.html` scripts block clears create forms on 2xx response and re-fires the default-date assignment.
- `partials/accounts/_reconcile_modal.html` migrated to the shared `partials/_slideover.html` wrapper so it inherits the `.slide-over__close` button + Esc + backdrop click + overlay-stack cooperation.
- `partials/accounts/_form.html` renames label `"Credit card (liability)"` → `"Credit (liability)"`; the credit-limit field renders with `hidden` + `aria-hidden="true"` + `disabled` when the toggle is off; the inline script flips all three in lockstep.
- `domain/money.py` gains `ISO_4217_CURRENCIES: tuple[str, ...]` (~180 codes); the Account form currency field becomes a combobox over it.
- Transaction, planned, recurring form `<select>`s for category / account / dest become comboboxes composed from the shared macro.
- `frontend-visual-audit` sweep on `/accounts`, `/ledger?view=actual|planned|recurring`, `/budget` at 1440/1024/375.
- Visual-regression baselines refreshed only on affected routes.

### ✅ T-112 [S] Overview enhancements (left-per-day + Upcoming unions planned+recurring + "+ Recurring" button) → T-110
- `templates/home/_month_panel.html` adds a `panel__hero-sub` line with `summary.left_daily_spend_minor` (rendered as `"— / day"` when `None`), feeding from the same `MonthSummary` the Budget hero already consumes.
- `routers/home.py` injects `today` into `services.budget.month_summary(..., today=…)` using `ZoneInfo(settings.display_timezone)` per ADR-0007; already true per T-100 but asserted by a new regression test.
- `templates/home/_upcoming_panel.html` keeps `+ Planned`; adds `+ Recurring` button (`hx-get="/recurring/new" hx-target="#modal-root" hx-swap="innerHTML"`, mirrored markup + a11y attrs).
- No change to `services.planned.list_planned` — the union already covers persisted + virtual (ADR-0013); the fragment response is unchanged.
- Visual-regression baseline refreshed on `/`.

### ✅ T-113 [S] Budget page v2 (Income anchor → Settings · Preferences; Rules redesign; Yearly table) → T-110, T-111, ADR-0031
- Delete `templates/budget/index.html` Section 2b ("Income anchor"); keep the "Left to spend per day" caption and append an inline `"Change anchor →"` link to `/settings?tab=prefs#income-anchor`.
- `templates/settings/_prefs.html` gains the income anchor `<section>` (anchor id `income-anchor`), reusing the existing form markup verbatim. `POST /budget/preferences/income-anchor` URL unchanged.
- Rewrite `templates/budget/index.html` Rules section: scrap the three-column table; new row = `category + default amount input (inline, submits to existing POST /budget/defaults/{category_id}) + Override… button`.
- `Override…` button is `<button hx-get="/budget/rules/{category_id}/overrides/new" hx-target="#modal-root" hx-swap="innerHTML">`; new partial `partials/budget/_override_form.html` wrapped by `partials/_slideover.html` carries tier radio (recurring / one-off), `<select>` month 1-12 (visible when either tier chosen), year input (visible when `tier=one-off` per ADR-0030 §6 conditional pattern), digit-only amount, hidden `category_id`.
- New `POST /budget/rules/{category_id}/overrides` router handler acts as a thin tier-dispatcher that calls the existing `budgets.set_recurring_override` or `budgets.set_one_off_override` repository functions. Emits `HX-Trigger: budget-stale`. 422 re-renders the form fragment, keeping the slide-over open.
- New Yearly budget table section (`#budget-yearly`) under Rules: rows = live expense categories, 12 month columns + year selector header, cells render F4.2-resolved values with typography encoding tier dominance (bold = one-off, italic = recurring, plain = default, em-dash = unset). Row + column totals in footers.
- Cell edit: click swaps the readout to an inline amount input (digit-only); Enter / blur submits to the existing `POST /budget/one-off/{category_id}/{year}/{month}`; empty value clears the one-off override.
- New HTMX fragment `GET /budget/yearly?year=…` returns the yearly table partial for year switches without full-page reload. Year defaults to current year in `display_timezone` (ADR-0007).
- Service helper (`services.budget.yearly_grid(conn, year) -> list[YearlyRow]`) returns per-category Jan..Dec resolved values + per-tier origin tag; pure projection over existing `budget_defaults` / `budget_recurring_overrides` / `budget_one_off_overrides` repositories. No new persistence.
- Existing integration tests covering the three-column Rules table + the on-/budget anchor selector move / rewrite against the new row shape + `tests/integration/web/test_settings.py`. New tests cover: Override dispatcher (recurring + one-off branches + 422), yearly grid resolution (default-only / recurring-wins / one-off-wins / all-unset), yearly cell edit path, year switch fragment.
- `frontend-visual-audit` sweep on `/budget` + `/settings?tab=prefs` at 1440/1024/375 before marking done.

### ✅ T-114 [P] Ledger row actions: fix edit regression + add Delete affordance → T-110
- **Bug.** Clicking **Edit** on a ledger row removes the row from the DOM instead of swapping it with its edit form. Root cause (to confirm): the current `_row.html` edit button HTMX wiring targets the row with `hx-swap="outerHTML"` against an endpoint response that is intended as a form fragment but currently renders as the empty-body create partial (post Phase 7/8 refactor fallout). Investigation + fix in the ledger row partial(s): `partials/transactions/_row.html`, `partials/planned/_row.html`, `partials/recurring/_row.html`.
- **Add Delete.** Every ledger row gains a `<button>` Delete affordance next to Edit — `hx-post="/transactions/{id}/delete"` (resp. `/planned/{id}/delete`, `/recurring/{id}/deactivate`) with `hx-confirm="Delete this row?"` and `hx-target` + `hx-swap="outerHTML swap:200ms"` so the row visually drops on success. The soft-delete endpoints already exist (T-031 / T-034 / T-035); this task is affordance-only.
- Regression test on each ledger view: click Edit → row swaps to form fragment carrying hydrated values; click Delete → row disappears, server records a soft-delete + audit entry.
- Visual-regression baselines on `/ledger?view=actual|planned|recurring` refreshed to pick up the new Delete button.
- `frontend-visual-audit` sweep on the three ledger views at 1440/1024/375.

### ✅ T-115 [P] Lock `transit` direction out of user category creation → T-110
- `src/budget_planner/web/templates/settings/_categories.html` + `partials/categories/_form.html`: narrow the direction `<select>` to `income` and `expense` only (today it still exposes `transit`).
- `routers/categories.py` + `services/categories.py` (or equivalent create path): reject `direction ∈ {transit, adjustment}` on the create / update path with 422 (today only `adjustment` is explicitly blocked). Message: `"transit and adjustment directions are reserved for system categories"`.
- Regression test: `POST /categories` with `direction=transit` returns 422 and no row is inserted; audit log untouched.
- Requirement reference: §2.1 F1.6 (narrowed in T-110).
- Seeded `Transit` system category remains the only transit-direction row in the database.

---

## Phase 12 — Recurring Standalone + Overview/Budget Fixups + Modal Scope + Account/Form Bugs

> Driven by field-use report 2026-10-27. Four non-negotiable UX/correctness changes: (1) separate Planned ≠ Recurring with their own promote-and-advance flow and `next_due`; (2) Overview Upcoming unions planned + recurring with grouped add buttons; (3) New-transaction popover must stop dismissing on amount keystroke; (4) Account slide-over credit-limit must respect the lockstep on initial render. Decisions: [ADR-0038](../../adr/0038-recurring-standalone-lifecycle.md), [ADR-0039](../../adr/0039-budget-daily-spend-includes-recurring.md), [ADR-0040](../../adr/0040-modal-dismissal-scope.md). Detailed plan: [`phase-12/README.md`](phase-12/README.md).

### ✅ T-116 [S] ADR-0038 + ADR-0039 + ADR-0040 + requirements + Phase 12 docs scaffolding
- Write `docs/adr/0038-recurring-standalone-lifecycle.md`, `docs/adr/0039-budget-daily-spend-includes-recurring.md`, `docs/adr/0040-modal-dismissal-scope.md` (all Accepted).
- Flip `docs/adr/0013-recurring-virtual-occurrences-and-overrides.md` to Superseded by ADR-0038; keep file for forecast.
- Update `docs/adr/README.md` index.
- Update `docs/requirements.md`: F1.1 (amount `,`/`.` + modal-safe side effects), F2.1 (credit-limit lockstep on initial render), split §2.3 into §2.3a planned + §2.3b recurring with F3.1 narrowed, F3.2 `next_due`, F3.5 Promote/Override/Skip/Delete, F3.6 narrowed override semantics, F3.7 unchanged, new F3.8/F3.9/F3.10, F4.6 includes `committed`, §3.9 Overview + Ledger panels.
- Create `docs/plans/v1/phase-12/README.md` + per-task stubs (T-116..T-124).
- Append dated line to `docs/CHANGELOG.md`.
- Append this block to `docs/plans/v1/tasks.md`.
- Docs only; no code.

### ✅ T-117 [S] Migration + domain + repository: `recurring_rules.next_due` / `last_promoted_date` + `transactions.promoted_from_recurring_*` → T-116, ADR-0038
- `migrations/0006_add_recurring_next_due.sql`: additive columns + indexes; backfill `next_due` via Python hook using the existing occurrence generator; flip `next_due` to NOT NULL via SQLite 12-step rebuild inside the same migration file (or a trailing `0007_recurring_next_due_not_null.sql`, authors choice).
- `domain/recurring.RecurringRule` gains `next_due: dt.date` + `last_promoted_date: dt.date | None`; `NewRecurringRule` does not expose `next_due` (repository computes).
- `domain/transactions.Transaction` + `NewTransaction` gain `promoted_from_recurring_rule_id` + `promoted_from_recurring_date`.
- `repositories/recurring.create_rule` populates `next_due`; `list_rules` SELECTs the new columns; new `set_next_due` + `set_inactive` thin helpers.
- `repositories/transactions.create` round-trips the recurring provenance fields.
- Test shape per `phase-12/T-117-migration-and-domain.md`.

### ✅ T-118 [S] Recurring promotion service + routes → T-117
- `services/recurring.advance_next_due` (pure), `services/recurring.first_due_on_or_after` (pure), `services/recurring.promote_recurring`, `services/recurring.skip_and_advance`.
- Shared `services/_promotion.py` validator consumed by both planned and recurring promotion paths; `services.planned.{ValidationError,UnsupportedDirectionError}` re-export the shared classes so callers keep working.
- `POST /recurring/{id}/promote` + `GET /recurring/{id}/promote` (modal partial `partials/recurring/_promote_modal.html`) + `POST /recurring/{id}/skip-next`.
- Audit entries on all mutations; HX-Trigger emits `ledger-stale`, `forecast-stale`, `budget-stale`.
- Test shape per `phase-12/T-118-recurring-promote-service.md`.

### ✅ T-119 [S] Decouple planned log from recurring; introduce `services.upcoming` + `services.income` → T-117
- `services/planned.list_planned` drops the virtual branch; `PlannedKind` collapses to `"persisted"`.
- Delete `services/planned.next_planned_for_category`; callers switch to `services/income.next_anchor_date`.
- New `services/upcoming.list_upcoming(window)` composing planned one-offs + recurring `next_due` with override merge/skip handling.
- `web/routers/home.py` Upcoming fragment switches to `services.upcoming.list_upcoming`.
- `web/routers/ledger._hydrate_recurring_rows` reads `rule.next_due` instead of aliasing `start_date`.
- `services/budget.month_summary` wires the new income-anchor service.
- Test shape per `phase-12/T-119-decouple-planned-from-recurring.md`.

### ✅ T-120 [S] Budget `committed_in_window` + `MonthTotals.committed_minor` + template surfaces → T-117, T-118, T-119, ADR-0039
- `MonthTotals` gains `committed_minor` field; `remaining_minor = budgeted − spent − committed`.
- New `services/budget.committed_in_window(start, end)` sums unpromoted planned-expense + active-recurring-expense amounts in window (overrides applied; skipped excluded; transit/adjustment excluded).
- `templates/budget/index.html` + `templates/home/_month_panel.html` render dim sub-line `"X committed (recurring + planned)"`.
- Tests pin `committed_in_window` + `month_summary` arithmetic + budget/home template rendering.

### ✅ T-121 [P] Overview Upcoming unions planned + recurring; group `+ Planned` + `+ Recurring` buttons → T-119
- `web/routers/home.py` Upcoming hydrator consumes `UpcomingItem.kind` and surfaces `planned_id` / `rule_id` / `override_present` + per-kind affordances.
- `templates/home/_upcoming_list.html` branches on `kind`: planned → promote-planned modal; recurring → Promote / Skip / Override buttons.
- `templates/home/_upcoming_panel.html` wraps `+ Planned` + `+ Recurring` in `.panel__add-group` cluster + stylesheet.
- `tests/integration/web/test_home.py` pins planned + recurring union, overdue chip semantics, `+ Recurring` wiring, grouped-cluster markup.

### ✅ T-122 [P] Ledger Recurring row: Promote / Override-next / Skip-next / Delete + `next_due` column → T-118
- `partials/recurring/_row.html` renders `next_due` column + Promote / Override-next / Skip-next / Edit / Delete actions.
- `partials/recurring/_override_form.html` new slide-over wrapper for the Override-next affordance; reuses existing `POST /recurring/{id}/overrides` endpoint.
- `_hydrate_recurring_rows` surfaces `override_present` + effective-amount for the current `next_due`.
- `tests/integration/web/test_recurring.py` pins the five actions + `next_due` column population.

### ✅ T-123 [P] Account form credit-limit initial-render bug → T-116
- `partials/accounts/_form.html`: rewrote the sync `<script>` to find the form via `[data-account-form]` attribute (position-independent, HTMX-swap-safe), run on initial parse + scoped `htmx:afterSwap`, idempotent via `form.dataset.limitWired`; also toggles inline `style.display` so `.form-stack label { display: flex }` no longer outweighs UA `[hidden]{display:none}`.
- Jinja condition on all three attributes now reads `account is none or not account.is_liability`; the hidden branch also emits `style="display:none"` on the label.
- Four integration tests pin the markup contract (`/accounts/new`, liability edit, asset edit, `data-account-form` hook); `frontend-visual-audit` on `/accounts` at 1440 / 1024 / 375 confirms lockstep toggle behaviour, no console errors / request failures / horizontal scroll.

### ✅ T-124 [P] Modal dismissal scope + amount `,`/`.` regression test → ADR-0040
- `templates/base.html` scripts block: scope reset-and-close to `evt.target instanceof HTMLFormElement && form[data-reset-on-submit] && verb ∈ {post, put, delete}` (ADR-0040). The 422-shouldSwap branch above is unchanged.
- `domain/money.parse_amount_str(raw, currency)` normalises `,`/`.` separators and rejects more fractional digits than the currency supports; `routers/transactions._validate_amount` + `_compute_limit_preview` delegate to it. Planned / recurring / budget routers unchanged in this task — follow-up required to extend normalisation to their create flows.
- Tests: `tests/integration/web/test_forms.py` pins slide-over markup, side-effect preview isolation, handler bytes (presence of `HTMLFormElement` + `data-reset-on-submit` + `requestConfig` + `"post"`), form-submit response shape (no slide-over), and both decimal separators landing on `1234` minor units with `12.345` → 422; four new unit tests in `tests/unit/domain/test_money.py` pin the `parse_amount_str` accept / reject matrix.
- Test shape per `phase-12/T-124-modal-dismissal-scope.md`.

### ✅ T-125 [S] Budget period = last-anchor-income → next-anchor-income (per-category `spent_minor`) → T-120, ADR-0041
- `services/budget._resolve_period_start(conn, today, year, month, anchor_category)` returns the most recent promoted anchor-category transaction date `<= today`, falling back to month start when the anchor is unset, has no prior landed transaction, or in zero-budget months.
- `services/budget.month_summary` passes the resolved `period_start` into `_expense_txns_in_range` for `this_txns` only; `prev_txns`, `year_txns`, `all_txns` keep calendar-month windows (ADR-0041 analytics non-goal).
- `budgeted_minor` stays monthly; `remaining_minor = budgeted_minor - spent_minor` formula unchanged.
- Tests pin anchor mid-month, no-prior-anchor fallback, zero-budget fallback, no-anchor-configured fallback, and formula consistency.
- Test shape per `phase-12/T-125-budget-anchor-window.md`.

### ✅ T-126 [S] Forecast budget overlay → ADR-0042, T-025, T-120
- Reconciled 2026-11-21 (T-Q246): landed (merge 7d72608, 2026-10-27; CHANGELOG T-126 line, ADR-0042).
- `services/forecast.budget_overlay_events(...)` computes per-category per-month unaccounted budget (`resolved_budget − spent_so_far − committed_future`, clamped ≥ 0) and emits `_CashEvent`s distributed evenly across the month window `[max(today+1, month_start), min(month_end, horizon_end)]` on the first active account (lowest id).
- `services/forecast.forecast(...)` gains `include_budget_overlay: bool = True` and merges overlay events into `_collect_events` output ahead of day-walk accumulation. Existing dedup for persisted ↔ virtual recurring preserved.
- Pre-overlay projection remains reachable via `include_budget_overlay=False` for the pure planned+recurring regression tests. `forecast` router + home mini-chart adopt the default (`True`) with no API change.
- Tests pin: single-category unaccounted spread, zero-residual skip when planned+recurring ≥ budget, cross-month boundary distribution, zero-length-window skip (last-day-of-month `today`), overlay-off parity with pre-overlay series, deterministic re-run equivalence.

### ✅ T-127 [S] Forecast tab — monthly horizon + breakdown table → ADR-0043
- `services/forecast.py`: new `MonthlyPoint` + `MonthlySeries` dataclasses and pure `forecast_monthly(conn, http, today, horizon_months, base_currency) -> MonthlySeries`. For each month in `[today.month, today.month + horizon_months - 1]` compute `end_balance_base_minor` (last-day projection), `income_base_minor` / `expense_base_minor` / `net_base_minor` (base-currency sums over the same signed-leg event stream that drives the daily series; transits + adjustments excluded). Reuses `_collect_events`, `_collect_fx_rates`, `_convert_native_to_base` — no duplication. Daily `forecast()` kept intact and remains the source of per-day points for the chart.
- `web/routers/forecast.py`: query params swap `horizon_days` → `horizon_months` (default 12, min 1, max 60). Router expands months → `horizon_days = (end_of_horizon_month - today).days`, then calls both `forecast()` + `forecast_monthly()` in one pass, passing `monthly` + `horizon_months` + `series` to the template. Legacy `horizon_days` param removed (no persisted state depends on it, v1 cosmetic change).
- `templates/forecast/index.html` + `partials/forecast/_chart.html` + new `partials/forecast/_table.html` + new `partials/forecast/_view.html`: horizon input renders as *months* (number input `min=1 max=60`); shared `#forecast-view` wrap holds both chart + table so one HTMX swap updates both via `hx-trigger="forecast-stale from:body"`. Table columns: Month · Income · Expenses · Net · Projected balance (EOM). Mobile: `.forecast-table-wrap { overflow-x: auto }` keeps the body horizontal scrollbar off at 375.
- `templates/partials/_nav.html`: new `{{ navlink('/forecast', 'Forecast', 'g f') }}` after Budget.
- Tests: 10 new unit tests in `tests/unit/services/test_forecast_monthly.py` cover empty / single-month / multi-month / income-only / expense-only / recurring-included / transit-excluded / fx-conversion / end-balance-matches-daily / negative-horizon. Integration tests in `tests/integration/web/test_forecast.py` migrated to `horizon_months`, new `_table.html` + `_view.html` fragment-shape tests, nav-link assertion. `test_home.py::test_nav_has_five_primary_items_plus_settings` picks up the new entry.

### ✅ T-133 [S] Budget Monthly Summary — surface analytics columns → ADR-0049
- Template: `templates/budget/index.html` Section 1 table grows three columns (Avg/mo · YTD avg · Δ prev) after Actual, before Remainder-bar. Values sourced from `line.avg_monthly_overall_minor`, `line.avg_this_year_minor`, `line.delta_vs_prev_month_minor` — already present on `CategoryBudgetLine`. `tfoot` leaves these cells blank.
- Delta sign: render explicit `+` / `−` prefix; apply `.delta--up` when `> 0`, `.delta--down` when `< 0`, no modifier when `== 0`.
- Responsive: new `.col-hide-sm` utility hides YTD avg + Δ prev `<th>` + `<td>` below the 640px breakpoint; Avg/mo stays visible.
- CSS: `app.css` adds `.col-hide-sm { @media (max-width: 639px) { display: none; } }` plus `.delta--up { color: var(--expense); }` / `.delta--down { color: var(--income); }` tint rules (red = expense rising, green = expense falling). No new palette tokens.
- Service / repo / DTO: unchanged. Pure surfacing.
- Tests: `tests/integration/web/test_budget.py` asserts the three columns render with values matching `services.budget.month_summary` output on a seeded fixture; delta sign classes applied correctly for +/−/0 cases.
- Visual audit: `frontend-visual-audit` on `/budget` at 1440 / 1024 / 375; verify no horizontal scroll regression beyond the existing `.ledger-scroll` wrapper, no header/body column desync on hide-sm.

### ✅ T-132 [S] Category colour coding — per-category override with direction default → ADR-0048
- Migration `0011_add_category_color.sql`: add nullable `categories.color TEXT CHECK (color IS NULL OR color GLOB '#[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]')`. Additive; no table rebuild; no FK pragma toggle.
- Domain: `Category.color: str | None`, `NewCategory.color: str | None = None`, `PatchCategory.color + clear_color: bool` sentinel for explicit NULL reset. New `normalise_color(raw) -> str | None` + `HEX_COLOR_RE` validator mirror the SQL CHECK.
- Repository: `_COLUMNS` + `_row_to_category` + `create` grow `color`; `update` uses the existing `as_dict` path (which now understands `clear_color`).
- Service / router: `web/routers/categories.create_category` + `update_category` accept `color` + `clear_color` form fields, normalise via `_resolve_color_form`, return 422 with field error `color` on malformed hex. Budget service `CategoryBudgetLine` + `YearlyRow` + router `RulesRow` grow `category_direction` + `category_color` so templates can render the coloured name without round-tripping to the Category DTO.
- Templating helper: `web/templating.py` adds `_category_label(category)` + `_category_label_parts(name, direction, color)` registered as Jinja globals; both render `<span class="cat-name" style="color: …">`. `_resolve_category_color` maps direction → `var(--income|--expense|--transit|--adjust)`; override hex wins.
- Templates: `partials/categories/_row.html`, `partials/transactions/_row.html`, `partials/recurring/_row.html`, `ledger/_table.html` (actual + planned + recurring views), `budget/index.html` (summary + rules), `budget/_yearly.html` swap raw `category.name` references for `category_label(...)` / `category_label_parts(...)`.
- Form: `partials/categories/_form.html` grows a `<fieldset class="cat-color-field">` with "Use direction default" checkbox + `<input type="color">`; inline JS keeps the two in lockstep (checkbox checked ⇒ picker disabled ⇒ no `color` field submitted). Form appears identically for create + edit; direction `<select>` stays create-only (direction immutable post-create).
- CSS: `app.css` gets `.cat-name { font-weight: 500; color: inherit; }` + `.cat-color-field` form styles; existing `.pill-*` palette untouched.
- Tests: `tests/unit/domain/test_categories.py` (hex normalisation + PatchCategory semantics), `tests/unit/web/test_category_label.py` (helper render + XSS-escape), repo + router tests extend with colour round-trip, invalid-hex 422, `clear_color` reset, SQL CHECK rejection.

### ✅ T-131 [M] Recurring formula — linear combination of terms + chaining → ADR-0047 (supersedes ADR-0045 §Decision)
- Migration `0010_recurring_formula_terms_schema_v2.sql`: SQL file is a no-op comment; Python post-apply hook in `db/migrate._POST_APPLY_HOOKS` transforms every `recurring_rules.amount_formula` v1 JSON into v2 shape (`{schema_version: 2, terms: [{sign: "+", coefficient_bps, source_category_ids}]}`). Idempotent — re-runs skip rows already at v2.
- Domain: new `FormulaTerm(sign, coefficient_bps, source_category_ids)` dataclass; `AmountFormula` becomes `(schema_version, terms: tuple[FormulaTerm, ...])`. Wrapper preserved so B/C transitions keep the same column + repo shape.
- Service refactor: factor out `_sum_category_in_month`, `_apply_coefficient`, `_collect_referenced_category_ids` as pure primitives — reused as B's AST leaf operators and C's parser emits them. `compute_formula_amount` iterates terms with `in_progress` frozenset for defence-in-depth cycle protection and memoisation cache for diamond deps.
- Chaining: `_sum_category_in_month` recurses into formula source rules. Save-time `validate_formula_sources` becomes topological reachability check (new `FormulaCycleError`).
- Promotion: 422 at `POST /recurring/{id}/promote` when formula resolves to non-positive amount (no silent clamp).
- Repository: JSON serialize/deserialize dispatches on `schema_version` — v1 fallback keeps legacy rows readable until the data migration runs.
- UI: `partials/recurring/_form.html` dynamic terms fieldset with Add/Remove term buttons; `terms[i][sign]`, `terms[i][coefficient_percent]`, `terms[i][source_category_ids]` POST field names. Ledger row chip tooltip summarises multi-term.
- Tests: new terms (empty reject, multi-term mixed sign, zero sum), chaining (2-level, 3-level, diamond with memo, self-loop + indirect cycle rejection at save), negative-at-promote 422, migration v1→v2 round trip, UI add/remove term POST shapes.

### ✅ T-130 [S] Recurring override soft-consume on promotion → ADR-0046
- Migration `0009_recurring_override_promoted_fk.sql`: add nullable `recurring_rule_overrides.promoted_to_txn_id INTEGER REFERENCES transactions(id) DEFERRABLE INITIALLY DEFERRED` + index `ix_recurring_overrides_promoted(rule_id, promoted_to_txn_id)`. Additive, no table rebuild.
- Domain: `RecurringOverride.promoted_to_txn_id: int | None = None`.
- Repository: `list_overrides(..., include_consumed: bool = False)` default-filters consumed rows; new `list_overrides_all` + new audit-free `mark_override_promoted(conn, override_id, txn_id)`.
- Service: `services.recurring.promote_recurring` step 6e swaps `delete_override` → `mark_override_promoted`. `skip_and_advance` + `_override_on_next_due` lookups keep default `include_consumed=False`.
- Formula compute: `services/recurring_formula.compute_formula_amount` + `rt_expand` load overrides via `list_overrides_all` so historical overrides stay visible after B's promotion.
- Tests: pin "A's May = formula(B.override) *after* B's May promoted"; pin that `list_overrides` default still hides consumed; pin that consumed override still appears in `expand` output for its canonical month.

### ✅ T-129 [M] Recurring formula amount → ADR-0045
- Migration `0008_recurring_amount_formula.sql`: add nullable `amount_formula TEXT`, rebuild `recurring_rules` to relax CHECK (`amount_formula IS NOT NULL OR default_amount <> 0`); FK pragma off during rebuild via `FK_OFF_MIGRATIONS = {7, 8}`.
- Domain: `AmountFormula(coefficient_bps, source_category_ids)`; `RecurringRule.amount_formula` defaulted `None`; `NewRecurringRule.amount_formula`; `PatchRecurringRule.amount_formula` via `_UNCHANGED` sentinel.
- Service `services/recurring_formula.py`: `parse_percent_to_bps`, `build_formula`, `compute_formula_amount`, `resolve_rule_amount`, `rt_expand`, `validate_formula_sources`. Pure cycle guard: skip formula sources at compute, reject at save.
- Wire-in: `services/recurring.promote_recurring`, `services/budget.committed_in_window`, `services/forecast._collect_events`, `web/routers/ledger._hydrate_recurring_rows` route through formula-aware runtime expand.
- Repository: JSON serialize/deserialize round-trip; snapshot `default_amount` written at save using `compute_formula_amount(today.year, today.month)`.
- UI: `partials/recurring/_form.html` gains `fixed | formula` radio toggle with coefficient % + source-category checkbox grid (JS swap via `data-amount-source-panel` + `hidden` + `aria-hidden` lockstep); Ledger row + Ledger table render `ƒ` chip when `is_formula`.
- Tests: `tests/unit/services/test_recurring_formula.py` (parser, builder, rounding); `tests/integration/web/test_recurring_formula.py` (compute, repo roundtrip, promote live-recompute, override precedence over formula, save-time cycle rejection, router smoke).

---

## Phase 7 — Deferred to v3 (originally labelled v2; renumbered 2026-10-28 when v2 became the Rising Dough redesign)

- CSV import with pluggable parsers.
- Auth and multi-user.
- Cross-currency transits with FX spread modelling.
- DuckDB attach for analytics speed-up.
- Trend-based forecast overlay.
- Rollover budgets.
- Hierarchical categories.
- Deployment to a hosted environment (likely Fly.io / Railway / self-hosted Docker + Caddy).
- Prune legacy `/transactions`, `/planned`, `/recurring`, `/categories`, `/analytics` routes + templates once Phase 6 302s have aged one release.
