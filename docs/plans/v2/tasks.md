# Rising Dough v2 — Tasks

> **CLOSED, superseded by [ADR-0107](../../adr/0107-sourdough-redesign-from-designer-handoff.md) (2026-11-21, T-Q246, OQ-21 default).**
> The Rising Dough v2 chrome (ADR-0050..0056) is replaced by the Sourdough redesign built solely from the designer handoff. No row below is worked or reconciled any more; every row is kept untouched for history, so the 60 open rows stay open on purpose.
> Rows whose intent survives are carried by `docs/plans/ui-redesign/tasks.md` (T-UR*); raise them there, not here:
> - Open decisions T-R71 (archived categories on recurring rules), T-R72 (UI language), T-R73 (pace-tag rule): still unresolved; settle under T-UR00 (operator decisions) before T-UR07, T-UR10 and T-UR13.
> - Backend additions T-R40 to T-R46 (afford, formula preview, last-checked, analytics bundle, category archive, batch promote, HTMX event audit): needed by the new screens; re-scope inside the owning surface tasks T-UR07 to T-UR14.
> - Cleanup T-R57 to T-R60 (redirects, FAB, `#drawer-root`, dead CSS): covered by T-UR15.
> - Everything else (T-R01 to T-R10 foundations, T-R11 to T-R24 primitives, T-R25 to T-R39 screens, T-R47 to T-R51, T-R61 to T-R64, T-R68): superseded by T-UR01 to T-UR14.
> Pending operator confirmation (default taken 2026-11-21, `docs/plans/quality-audit/findings.md` OQ-21).

> Flat index. Full detail per task lives in the matching `phase-N-*/T-Rxx-*.md` file.
> Legend: `[P]` parallel-safe within its phase, `[S]` sequential, `→ T-Rxx` depends on upstream task.
> Acceptance = ADR referenced + tests + `frontend-visual-audit` sweep (D 1440 / T 1024 / M 375) + validation hook from the task file passes + `✅` prefix added here.

---

## Phase 0 — Open decisions (T-R71..T-R73)

> Three handoff `docs/07-open-items.md` decisions must land as ADR amendments or explicit resolutions **before Phase 1 kickoff**. They gate Phase 3 screen rebuilds.

### ◻ T-R71 [S] ADR amendment — archived categories on existing recurring rules
- Resolve handoff §07 "Whether archived categories can be used on existing recurring rules."
- Amend ADR-0048 or write a new ADR specifying behaviour: block archive if any live recurring rule points at it, or allow archive + show warning in UI.
- Blocks T-R28 (Ledger · Recurring) and T-R35 (Settings · Categories archive).
- File: `phase-0-decisions/T-R71-archived-categories-on-rules.md`.

### ◻ T-R72 [S] UI language decision
- Resolve handoff §07 "Polish labels: mockups are in English with Polish category names; confirm UI language."
- Either (a) commit to English chrome + user-controlled category names (current v1 state) or (b) introduce an i18n layer. Capture in a new ADR.
- Blocks every Phase 3 screen rebuild (strings live in templates).
- File: `phase-0-decisions/T-R72-ui-language.md`.

### ◻ T-R73 [S] Pace-tag rule confirmation
- Resolve handoff §07 "Today pace tag reads 'On track' as in the current app although spend is 71% of plan; confirm the pace rule."
- Document the pace-tag formula (expected-progress-at-today vs. actual-progress) in an amendment to ADR-0041 or ADR-0051.
- Blocks T-R25 (Today) and T-R14 (`pace_tag` macro semantics).
- File: `phase-0-decisions/T-R73-pace-tag-rule.md`.

---

## Phase 1 — Foundations (T-R01..T-R10)

Owner: web platform. All tasks block Phase 2+.

### ◻ T-R01 [S] Tailwind v4 upgrade
- Replace Tailwind v3 build chain with v4; drop `tailwind.config.ts`; consolidate into `static/css/app.css`.
- `just css` + `just css-watch` + `tailwind-check` pre-commit hook keep their names; validate the hook still catches staleness.
- Reference: ADR-0052 §1.
- File: `phase-1-foundations/T-R01-tailwind-v4-upgrade.md`.

### ◻ T-R02 [S] Design tokens pipeline → T-R01
- Copy `docs/application_redesign_handoff/tokens.css` to `src/budget_planner/web/static/tokens.css` verbatim.
- Wire `@theme` block in `app.css` to expose tokens as Tailwind utilities (ADR-0052 §1 example).
- New pre-commit hook asserts the two files remain byte-identical.
- Reference: ADR-0050 §2, ADR-0052 §2.
- File: `phase-1-foundations/T-R02-tokens-pipeline.md`.

### ◻ T-R03 [S] Self-hosted fonts → T-R01
- Add Newsreader / Hanken Grotesk / IBM Plex Mono variable `woff2` files under `static/fonts/`.
- `static/css/fonts.css` with `@font-face` + swap; imported by `app.css` before `@theme`.
- Preload critical weight per family on `base.html`; `font-display: swap` elsewhere.
- Reference: ADR-0050 §3, ADR-0052 §3.
- File: `phase-1-foundations/T-R03-self-hosted-fonts.md`.

### ◻ T-R04 [S] Base shell refactor → T-R02, T-R03
- `base.html` rewrite: hairline rail with `--paper` background, Rising Dough wordmark in Newsreader, top-bar `+ Add` slot (desktop), bottom tab bar slot (mobile — stub, Phase 6 fills).
- Preserve Jinja block names (`title`, `head_extra`, `nav`, `main`, `scripts`) so existing screens still render.
- Retire `#drawer-root` only in Phase 7; keep it available during migration.
- Reference: ADR-0051 §1, ADR-0055 §1.
- File: `phase-1-foundations/T-R04-base-shell.md`.

### ◻ T-R05 [P] Product rename → T-R04
- Wordmark + `<title>` → "Rising Dough" on every template.
- `CLAUDE.md` project line + `README.md` prefix line updated.
- `grep "Budget Planner" src/budget_planner/web/templates` returns zero live hits.
- Reference: ADR-0050 §1.
- File: `phase-1-foundations/T-R05-product-rename.md`.

### ◻ T-R06 [S] Nav skeleton + routes → T-R04
- Register canonical routes (`/today`, `/plan`, `/accounts`, `/settings`) and keep legacy routes as 302 redirects.
- Nav highlights the current section; keyboard shortcut map (`g o/l/p/a/s`) wired in `static/js/shortcuts.js`.
- Integration tests update to assert 302 Location headers for the legacy URLs.
- Reference: ADR-0051 §1, §2.
- File: `phase-1-foundations/T-R06-nav-skeleton.md`.

### ◻ T-R07 [P] `/dev/components` stub → T-R04
- New route `GET /dev/components`, gated by `settings.env != "production"`.
- Stub renders an empty section per planned macro so Phase 2 has placeholders to fill.
- Reference: ADR-0053 §2.
- File: `phase-1-foundations/T-R07-dev-components-stub.md`.

### ◻ T-R08 [P] Stylelint rules → T-R02
- Add a stylelint rule rejecting `oklch`/`rgb`/`hsl` outside `tokens.css` and `fonts.css`.
- Hook into pre-commit stylelint stage.
- Reference: ADR-0052 §2.
- File: `phase-1-foundations/T-R08-stylelint-rules.md`.

### ◻ T-R09 [S] Visual-regression baseline canary → T-R07
- Capture Playwright baselines for `/dev/components` at D (1440) · T (1024) · M (375).
- Commit baselines under `tests/visual/baseline/`.
- `just test-visual` passes.
- Reference: ADR-0027 §Visual regression.
- File: `phase-1-foundations/T-R09-visual-regression-canary.md`.

### ◻ T-R10 [S] Phase-1 CI gate → T-R01..T-R09
- `just ci` green; coverage ≥ 90%; `tailwind-check` + `stylelint` + `token-diff` hooks all pass.
- Dated line in `docs/CHANGELOG.md`.
- File: `phase-1-foundations/T-R10-phase1-ci-gate.md`.

### ◻ T-R63 [P] View Transitions wiring → T-R04
- Feature-detect `document.startViewTransition` in `base.html`; wire HTMX `hx-swap="... transition:true"` global default for tab changes + promote-in-place.
- `prefers-reduced-motion` disables (ADR-0050 §5).
- Reference: ADR-0056 §7.
- File: `phase-1-foundations/T-R63-view-transitions.md`.

### ◻ T-R64 [P] Keyboard shortcut map → T-R06
- Dedicated `static/js/shortcuts.js` module registering `g o/l/p/a/s`, `n`, `/`, `[`, `]`, `?`, `⎋`.
- Input-guard against `<input>` / `<textarea>` / `[contenteditable]`.
- Opens the cheatsheet modal (T-R62) on `?`.
- Reference: ADR-0051 §1, handoff §Keyboard.
- File: `phase-1-foundations/T-R64-shortcut-map.md`.

---

## Phase 2 — Component primitives (T-R11..T-R24)

Owner: `web/templates/_partials/components/`. Mostly parallel within phase.

### ◻ T-R11 [P] `amount` macro → T-R10
- `_partials/components/_amount.html`.
- Signature: `amount(minor, currency, direction=None, formula=False, fx_hint=None, size="base")`.
- Plex Mono tabular, sign + currency suffix + ƒ chip + FX hint tooltip.
- Reference: ADR-0053 §1 (Amount).
- File: `phase-2-primitives/T-R11-amount-macro.md`.

### ◻ T-R12 [P] `category_pill` macro → T-R10
- `_pill.html`; reads `category.color_hue` (ADR-0048) with direction default fallback.
- Reference: ADR-0053 §1 (Category pill), ADR-0048.
- File: `phase-2-primitives/T-R12-category-pill-macro.md`.

### ◻ T-R13 [P] `direction_badge` macro → T-R10
- `_direction_badge.html`; glyph + optional label.
- Reference: ADR-0053 §1 (Direction badge).
- File: `phase-2-primitives/T-R13-direction-badge-macro.md`.

### ◻ T-R14 [P] `pace_tag` + `overdue_chip` macros → T-R10
- `_pace_tag.html` and `_overdue_chip.html`; three pace states + overdue row class.
- Reference: ADR-0053 §1 (Pace tag, Overdue chip).
- File: `phase-2-primitives/T-R14-pace-overdue-macros.md`.

### ◻ T-R15 [P] `button` macro → T-R10
- `_button.html` with variants primary / default / ghost; `shortcut` → `<kbd>`.
- Reference: ADR-0053 §1 (Buttons).
- File: `phase-2-primitives/T-R15-button-macro.md`.

### ◻ T-R16 [P] `segmented` macro → T-R10
- `_segmented.html`; supports HTMX `hx-get`.
- Reference: ADR-0053 §1 (Segmented control), ADR-0028.
- File: `phase-2-primitives/T-R16-segmented-macro.md`.

### ◻ T-R17 [P] `filter_chip_row` macro → T-R10
- `_filter_chips.html`; date range / category / account / direction / search with `/` hint.
- Reference: ADR-0053 §1 (Filter row).
- File: `phase-2-primitives/T-R17-filter-chip-row-macro.md`.

### ◻ T-R18 [P] `table_row` macro → T-R10
- `_table_row.html`; grid row with hairline divider; actions right-aligned; `@media (hover: none)` always-visible actions.
- Reference: ADR-0053 §1 (Table row).
- File: `phase-2-primitives/T-R18-table-row-macro.md`.

### ◻ T-R19 [P] `heatmap_cell` macro → T-R10
- `_heatmap_cell.html`; sqrt scaling capped at 1,600; tier markers for one-off / recurring / default / unset.
- Reference: ADR-0053 §1 (Heatmap cell), handoff screen 1h.
- File: `phase-2-primitives/T-R19-heatmap-cell-macro.md`.

### ◻ T-R20 [P] `progress_bar` macro → T-R10
- `_progress_bar.html`; segmented spent / committed (diagonal hatch) / left variant.
- Reference: ADR-0053 §1 (Progress bar).
- File: `phase-2-primitives/T-R20-progress-bar-macro.md`.

### ◻ T-R21 [P] `top_bar_add` macro → T-R10
- `_top_bar_add.html`; context-aware (planned / recurring / actual).
- Reference: ADR-0053 §1 (Add).
- File: `phase-2-primitives/T-R21-top-bar-add-macro.md`.

### ◻ T-R22 [P] `period_header` macro → T-R10
- `_period_header.html`; shared between Today and Plan tabs.
- Reference: ADR-0051 §3, §5; ADR-0041 anchor window.
- File: `phase-2-primitives/T-R22-period-header-macro.md`.

### ◻ T-R23 [S] `/dev/components` population → T-R11..T-R22
- Fill the stub with every macro + representative inputs.
- Section anchors so Playwright assertions pin to a specific primitive.
- File: `phase-2-primitives/T-R23-dev-components-populate.md`.

### ◻ T-R24 [S] Primitive visual-regression baselines → T-R23
- Regenerate baselines at D/T/M for `/dev/components`.
- Commit baselines; `just test-visual` green.
- File: `phase-2-primitives/T-R24-primitives-vr-baselines.md`.

### ◻ T-R61 [P] `toast` macro + Undo wiring → T-R10
- `_partials/components/_toast.html` with variants info / success / destructive.
- `#toast-root` consumer in `base.html`; HTMX `HX-Trigger: {"toast": {...}}` dispatches render; auto-dismiss 4 s; Undo button posts to the write's inverse endpoint.
- Covers "Promoted księgowa · Undo" per handoff §Interactions.
- Reference: ADR-0053 (add row to §1), ADR-0056 §1.
- File: `phase-2-primitives/T-R61-toast-macro.md`.

### ◻ T-R62 [P] `?` cheatsheet modal → T-R10, T-R64
- `_partials/components/_cheatsheet.html` listing every shortcut from ADR-0051 §1 + ADR-0056.
- Opens via `?` keybinding (T-R64) or Settings link on mobile.
- Reference: handoff §Keyboard, ADR-0056 §9.
- File: `phase-2-primitives/T-R62-cheatsheet-modal.md`.

---

## Phase 3 — Screen rebuild (T-R25..T-R39)

Owner: `web/templates/{today,ledger,plan,accounts,settings}/`.

### ◻ T-R25 [S] Today → T-R24
- Hero (left-per-day) + Can-I-afford input + Net worth card + Upcoming panel.
- Depends on `services.upcoming.list_upcoming` (exists) and `services.today.afford` (Phase 4 T-R40).
- Reference: ADR-0051 §3, handoff `docs/application_redesign_handoff/docs/03-screen-specs.md` §Today.
- File: `phase-3-screens/T-R25-today.md`.

### ◻ T-R26 [S] Ledger · Actual → T-R24
- Day-grouped rows; new chip filter row; row shape via `table_row` macro.
- Reference: handoff §Ledger · Actual.
- File: `phase-3-screens/T-R26-ledger-actual.md`.

### ◻ T-R27 [S] Ledger · Planned → T-R24
- Columns: due / description / category / amount / status / actions.
- Reference: handoff §Ledger · Planned.
- File: `phase-3-screens/T-R27-ledger-planned.md`.

### ◻ T-R28 [S] Ledger · Recurring → T-R24, T-R26
- Grouped Monthly / Yearly; chevron expands overrides + formula derivation.
- Reference: handoff §Ledger · Recurring, ADR-0038, ADR-0047.
- File: `phase-3-screens/T-R28-ledger-recurring.md`.

### ◻ T-R29 [S] Plan shell + Period header → T-R22
- Shared tab shell for Budget · Year · Forecast · Analytics; period header component sits above tabs.
- Reference: ADR-0051 §5, handoff §Plan.
- File: `phase-3-screens/T-R29-plan-shell.md`.

### ◻ T-R30 [S] Plan · Budget → T-R29
- Rules table + period hero + Override slide-over (reuses Phase 11 override form).
- Reference: handoff §Plan · Budget, ADR-0031.
- File: `phase-3-screens/T-R30-plan-budget.md`.

### ✅ T-R31 [S] Plan · Year → T-R19, T-R29
- Heatmap grid + cell edit popover (Alpine or native CSS Anchor Positioning).
- Reference: handoff §Plan · Year, ADR-0056 §2.
- File: `phase-3-screens/T-R31-plan-year.md`.

### ◻ T-R32 [S] Plan · Forecast → T-R29, Phase 5 chart ready
- SVG line + area chart; monthly table below (reuse ADR-0043 shape).
- Reference: handoff §Plan · Forecast, ADR-0043, ADR-0054.
- File: `phase-3-screens/T-R32-plan-forecast.md`.

### ◻ T-R33 [S] Plan · Analytics → T-R29, T-R43, Phase 5 chart ready
- Spend by category + income vs expense + largest items.
- Reference: handoff §Plan · Analytics, ADR-0054.
- File: `phase-3-screens/T-R33-plan-analytics.md`.

### ◻ T-R34 [S] Accounts → T-R24, T-R42
- Sparkline + last-checked column + ⋯ menu.
- Reference: handoff §Accounts, ADR-0024 (liability).
- File: `phase-3-screens/T-R34-accounts.md`.

### ◻ T-R35 [S] Settings · Categories → T-R24, T-R44
- Groups expense / income / system; archive affordance; income-anchor as first control.
- Reference: handoff §Settings · Categories, ADR-0048, ADR-0051 §7.
- File: `phase-3-screens/T-R35-settings-categories.md`.

### ◻ T-R36 [S] Settings · Currency & FX → T-R24
- Read-only FX cache; base currency + timezone display.
- Reference: ADR-0051 §7.
- File: `phase-3-screens/T-R36-settings-fx.md`.

### ◻ T-R37 [S] Settings · Preferences → T-R24
- Mirror link to income-anchor control on Categories tab.
- Reference: ADR-0051 §7.
- File: `phase-3-screens/T-R37-settings-preferences.md`.

### ✅ T-R38 [S] Add entry modal → T-R24, T-R41
- Fixed / Formula paths; amount focused first on mobile.
- Reference: handoff §Add entry, ADR-0056 §4.
- File: `phase-3-screens/T-R38-add-entry-modal.md`.

### ✅ T-R39 [S] Reconcile slide-over reskin → T-R24
- Three steps in plain language; Record button states the signed amount.
- Reference: handoff §Reconcile slide-over, ADR-0011.
- File: `phase-3-screens/T-R39-reconcile-reskin.md`.

### ✅ T-R65 [S] Create account overlay reskin → T-R24, T-R34
- Rebuild handoff screen 2c: name · currency (immutable, filterable combobox) · free-text type · opening balance + as-of date · liability toggle · credit-limit (conditional per ADR-0030 §6).
- Reuses existing POST endpoints; close affordance per ADR-0030.
- Reference: handoff §Create account, ADR-0024, ADR-0030.
- File: `phase-3-screens/T-R65-create-account-overlay.md`.

### ✅ T-R66 [S] Create category overlay reskin → T-R24, T-R35
- Rebuild handoff screen 2d: name · direction (Expense / Income only — ADR-0023 scope) · colour (direction default or 10 swatches) · live preview of pill + badge.
- Reference: handoff §Create category, ADR-0048, ADR-0023.
- File: `phase-3-screens/T-R66-create-category-overlay.md`.

### ✅ T-R67 [S] Accounts ⋯ menu → T-R24, T-R34
- Row ⋯ opens popover with Edit · Snapshot · Delete per handoff §Accounts "described, not drawn".
- Edit opens the Create-account overlay (T-R65) pre-filled; Snapshot posts to existing `/accounts/{id}/snapshots`; Delete soft-deletes via existing endpoint with `hx-confirm`.
- Reference: ADR-0051 §6.
- File: `phase-3-screens/T-R67-accounts-row-menu.md`.

### ✅ T-R69 [S] Ledger bulk-select toolbar → T-R26, T-R27
- Row checkbox + sticky header toolbar on selection: Export CSV · Export Parquet · Bulk delete (Actual + Planned only).
- Reuses existing export endpoints (F1.4) with current filter + selected row ids.
- Reference: handoff §Ledger · Actual "Bulk actions and export appear as a toolbar when rows are selected."
- File: `phase-3-screens/T-R69-ledger-bulk-toolbar.md`.

### ✅ T-R70 [S] "Recently deleted" surface → T-R26
- Row ⋯ menu + `/ledger?view=recently-deleted` segmented-control extra tab (or dedicated panel) lists archived transactions + categories with Restore action.
- Reuses soft-delete repository helpers (ADR-0019, ADR-0022).
- Reference: handoff §Ledger · Actual "Deleted = archived; restorable from ⋯ or 'Recently deleted'."
- File: `phase-3-screens/T-R70-recently-deleted.md`.

---

## Phase 4 — Backend additions (T-R40..T-R46) — parallel-safe with Phase 3

Owner: `routers/` + `services/`.

### ◻ T-R40 [P] `GET /today/afford?amount=` → T-R10
- `services.today.afford(amount_minor)` returns `(per_day_minor, delta_minor, pace_tag)`.
- Debounced HTMX preview; no DB write.
- Reference: ADR-0056 §3.
- File: `phase-4-backend/T-R40-today-afford.md`.

### ◻ T-R41 [P] `POST /recurring/formula/preview` → T-R10
- `services.recurring.formula.preview(terms)` returns computed value or 422 with inline error.
- Reference: ADR-0047, ADR-0056 §4.
- File: `phase-4-backend/T-R41-formula-preview.md`.

### ◻ T-R42 [P] `GET /accounts/last-checked` → T-R10
- `services.accounts.last_checked()` returns latest snapshot or reconcile date per account.
- Reference: ADR-0056 §6.
- File: `phase-4-backend/T-R42-accounts-last-checked.md`.

### ◻ T-R43 [P] `GET /plan/analytics` bundle → T-R10
- `services.analytics.bundle(period)` returns spend-by-category + 12-month averages + income-vs-expense + largest items.
- Replaces Plotly-backed `/analytics` service.
- Reference: ADR-0056 §6.
- File: `phase-4-backend/T-R43-analytics-bundle.md`.

### ◻ T-R44 [P] Category archive / restore → T-R10
- `POST /categories/{id}/archive` + `POST /categories/{id}/restore`.
- Uses existing soft-delete repository helper.
- Reference: ADR-0056 §6, ADR-0022.
- File: `phase-4-backend/T-R44-category-archive.md`.

### ◻ T-R45 [P] Batch promote-due → T-R10
- `POST /recurring/batch/promote-due` + `POST /planned/batch/promote-due`.
- One transaction, returns summary for Undo toast.
- Reference: ADR-0056 §6, ADR-0038, ADR-0012.
- File: `phase-4-backend/T-R45-batch-promote-due.md`.

### ◻ T-R46 [S] HTMX event wiring audit → T-R40..T-R45
- Verify every new endpoint fires the right `HX-Trigger` events; document in `routers/README.md`.
- File: `phase-4-backend/T-R46-htmx-event-audit.md`.

---

## Phase 5 — Charts (T-R47..T-R50)

### ◻ T-R47 [S] `src/budget_planner/web/charts.py` → T-R24
- Three pure functions returning SVG geometry: `line_area(points)`, `grouped_bars(groups)`, `horizontal_bars(items)`.
- Unit tests on representative input.
- Reference: ADR-0054 §1, §2.
- File: `phase-5-charts/T-R47-charts-module.md`.

### ◻ T-R48 [S] Forecast chart template → T-R47, T-R32
- `templates/plan/_forecast_chart.html` renders SVG + data-table fallback inside `<details>`.
- `role="img"` + `aria-labelledby` + figcaption.
- File: `phase-5-charts/T-R48-forecast-chart.md`.

### ◻ T-R49 [S] Analytics chart templates → T-R47, T-R33
- Three charts: spend-by-category list, income vs expense bars, largest items list.
- Each with data-table fallback.
- File: `phase-5-charts/T-R49-analytics-charts.md`.

### ◻ T-R50 [S] Plotly removal → T-R48, T-R49
- Delete Plotly JS from `static/vendor/`, remove any `to_plotly_figure` helpers, drop `plotly` from imports.
- Verify bundle delta ≥ 1.5 MB.
- Reference: ADR-0054.
- File: `phase-5-charts/T-R50-plotly-removal.md`.

### ◻ T-R68 [S] `sparkline()` helper + Accounts trend column → T-R47, T-R34
- Add `sparkline(points)` to `src/budget_planner/web/charts.py` — narrow-aspect `line_area` variant with no axes.
- Service helper `services.accounts.trend(account_id, days=30)` returns daily balance points.
- Accounts table row renders inline SVG sparkline (handoff screen 1j shows it).
- Reference: ADR-0054 §Follow-ups, handoff §Accounts.
- File: `phase-5-charts/T-R68-sparkline-accounts.md`.

---

## Phase 6 — Responsive (T-R51..T-R56)

### ◻ T-R51 [S] Mobile tab bar → Phase 3 screens green
- Bottom-fixed nav with four tabs + centre `+ Add`; tap targets ≥ 44 px.
- Reference: ADR-0055 §2.
- File: `phase-6-responsive/T-R51-mobile-tab-bar.md`.

### ✅ T-R52 [S] `+ Add` bottom sheet → T-R51, T-R38
- `<dialog>` + CSS translate; three choice tiles then form swap.
- Dismiss on 2xx + popstate (ADR-0030).
- Reference: ADR-0055 §3.
- File: `phase-6-responsive/T-R52-add-bottom-sheet.md`.

### ✅ T-R53 [S] Narrow numeric table scroll wrappers → T-R30, T-R31, T-R33
- Reuse `.ledger-scroll` or new `.table-scroll` with sticky first column.
- Fixes `/budget`, `/analytics`, `/forecast` overflow findings.
- Reference: ADR-0055 §4.
- File: `phase-6-responsive/T-R53-narrow-table-scroll.md`.

### ✅ T-R54 [S] Year grid → category cards (mobile) → T-R31
- At ≤ 640 px replace heatmap with per-category horizontal strip cards.
- Cell tap opens the Phase 3 cell edit popover.
- Reference: ADR-0055 §5.
- File: `phase-6-responsive/T-R54-year-cards-mobile.md`.

### ✅ T-R55 [S] Settings tab bar on mobile → T-R35, T-R36, T-R37
- Satisfied by the T-R53 `.rd-segmented` mobile scroll rule — Settings tab bar already fits 375 px without horizontal doc scroll (visual audit clean).
- Settings reached from Today header on mobile; tab bar scrolls at narrow widths.
- Reference: ADR-0055 §2.
- File: `phase-6-responsive/T-R55-settings-mobile.md`.

### ✅ T-R56 [S] Mobile visual regression baselines → T-R51..T-R55
- Regenerate baselines at 375 px for every v2 route.
- `frontend-visual-audit` returns zero overflow findings.
- File: `phase-6-responsive/T-R56-mobile-vr-baselines.md`.

---

## Phase 7 — Cleanup (T-R57..T-R60) — lands one release after v2 cut

### ◻ T-R57 [S] Retire v1 → v2 302 redirects → v2 shipped ≥ 1 release
- Remove `RedirectResponse` shims in affected routers; delete legacy route handlers.
- File: `phase-7-cleanup/T-R57-retire-legacy-routes.md`.

### ◻ T-R58 [S] Delete FAB → T-R57
- Remove template partial + CSS + JS; grep returns zero hits.
- Amends ADR-0026 (already noted historical in that ADR).
- File: `phase-7-cleanup/T-R58-delete-fab.md`.

### ◻ T-R59 [S] Retire `#drawer-root` → T-R57
- Remove the slot from `base.html`; simplify `overlay-stack.js` if applicable.
- File: `phase-7-cleanup/T-R59-retire-drawer-root.md`.

### ◻ T-R60 [S] Dead-CSS prune + close v2 → T-R57..T-R59
- `stylelint` + `knip`-style tool identify dead CSS classes; prune.
- Append "✅ v2 shipped" line to top of `tasks.md`.
- Dated entry in `docs/CHANGELOG.md`.
- File: `phase-7-cleanup/T-R60-dead-css-prune.md`.

---

## Deferred past v2 (require ADR before promotion)

- Dark mode / theme switcher.
- `⌘K` command palette (handoff screen 1m kept as reference).
- Hover-only row actions on Ledger · Recurring.
- Additional currency examples in design mocks.
- CSV import (still deferred past v3 as well — see ADR-0020).
- Any schema change (every v2 ADR explicitly commits to zero migrations).
