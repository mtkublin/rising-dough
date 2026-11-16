# Sourdough Redesign — Tasks

> Plan: [README.md](README.md). Decision: [ADR-0107](../../adr/0107-sourdough-redesign-from-designer-handoff.md). Handoff: `docs/design/rising-dough-frontend/` (its `README.md` is required reading for every task).
> Legend: `[P]` parallel-safe within its phase, `[S]` sequential, `→ T-URxx` depends on upstream task.
> Every Phase 2 task follows the per-surface loop and definition of done in [README.md](README.md#per-surface-loop-test-first).

---

## Phase 0 — Entry

### ◻ T-UR00 [S] Entry gate and open design questions
- UI test harness exit gate ✅ (T-UT12); quality-audit `[pre-v4-P3]` remediation ✅; ADR-0107 Accepted.
- Operator decisions recorded in `derived.md` for the handoff README §6 open items: visible bulk-select entry point (#7), inline promote variant, `g o` vs `g t` for Today, and every `no board` / `handoff-only` row from `../ui-test-harness/parity.md` (T-UT06).
- Work branch `ui/sourdough` created from the current `v3` (or `main` once v3 is merged).
- **Removal ledger** `removal.md` generated from `git ls-files` at the branch point: every file under `web/templates/`, `web/static/` (outside `rd/`), `tests/visual/baselines/`, plus the Tailwind/Node config, `justfile` recipes, pre-commit hooks and CI steps that exist only for the old frontend. Each row: path, owning surface task (or T-UR15 for shared files), status (`delete` / `keep: <reason>`). Only the kept-behaviour files from ADR-0107 §2 may be `keep`.
- `tests/architecture/test_old_frontend_removed.py`: reads `removal.md` and fails if a row marked `deleted` still exists, or if a new file appears under an old-frontend path (the old trees may only shrink). Starts green with nothing deleted.

---

## Phase 1 — Foundation (sequential core, then two parallel items)

### ◻ T-UR01 [S] Assets and toolchain → T-UR00
- **Deliverables**:
  - Handoff `static/` copied to `src/budget_planner/web/static/rd/` unchanged, minus `js/stand-in.js`.
  - `scripts/build_css_bundle.py` + `just css`: concatenates `rd/css/main.css`'s `@import` list in order into `rd/css/app.bundle.css`, preserving `@layer` order; pre-commit hook fails when the bundle is stale. Unit test on a small fixture tree.
  - stylelint runs with the handoff's `.stylelintrc.json` on `static/rd/css/**`; the old config keeps linting the old files until T-UR15.
  - Script tags as `type="module"`; theme script as classic `<head>` script; external icon sprite path.
- **Acceptance**: bundle byte-identical across two runs; `just lint` green; old pages render unchanged (crawler and visual on old UI unchanged).
- References: ADR-0107 §3–§4.

### ◻ T-UR02 [S] Base layout and shell → T-UR01
- **Deliverables**: `templates/layouts/base.html` per the handoff page shell: skip link, nav (desktop rail ≥ 768 px, bottom tab bar below), header, `#modal-root`, `#drawer-root`, `#toast-root`, `#flash-region`, global `#palette` and `#shortcuts` dialogs, CSRF meta for `htmx-csrf.js`, CSP nonce on any `<style>`. `fragments/flash/*`, `fragments/toast/undo`, `fragments/states/*`. The palette entries and shortcut targets come from the existing palette route data.
- **Test-first**: `tests/ui_map/shell.py` rewritten to the handoff markup and checked with `--target=mockup` before the template is written.
- **Acceptance**: a placeholder page extending the new base passes shell journeys (navigation, palette, shortcuts, theme switch); unmigrated pages still use the old base; crawler green on both.

### ◻ T-UR03 [P] Server-side value helpers → T-UR01
- **Deliverables** (pure functions + Jinja filters, unit-tested, ADR-0107 §5): category colour to `data-color` preset or nonce'd rule with the `--cat-edge` 3:1 contrast computation; block-character bar spans (20 / 10 cells, `--over`, `--none`); hero figure fit counts (`data-digits`, `data-marks`, `data-signs`); year-cell `data-state`; bar `aria-label` text.
- **Acceptance**: 100 % branch coverage on the helpers; every preset in `category-colors.css` round-trips.

### ◻ T-UR04 [P] Shared fragments and dialog plumbing → T-UR02
- **Deliverables**:
  - Fragments used by more than one surface: `fields/category-picker`, `fields/formula`, `fields/formula-component`, amount input, `forms/error-summary`, `popovers/period-picker`, `plan/period-nav`, row-menu shell, `ledger/pagination`.
  - Response helpers: render a dialog into `#modal-root`; POST success → swap row + OOB `flash/success`; delete/skip/restore → row removal + `toast/undo`; validation error → dialog re-render with `aria-invalid` + error summary (422).
  - Kept behaviour JS (`htmx-csrf.js`, `passkeys.js`) moved under `static/rd/js/` and adapted to the new markup hooks.
- **Acceptance**: contract tests for dialog/OOB behaviour green; each shared fragment rendered in a fragment-level test via the UI map.

---

## Phase 2 — Surfaces (parallel, orchestrator mode) → T-UR01..T-UR04

Each item owns its page templates, its surface-only fragments and overlays, its UI-map module and its router context changes. Shared fragments belong to T-UR04; a surface that needs a change there sends it back to the orchestrator as a follow-up instead of editing it.

**Each item also deletes its old files** as the last step before handoff: every `removal.md` row owned by the surface (old page templates, partials only it includes, its old CSS sheet, its old JS, its old visual baselines, old-markup `id` / `data-testid` hooks go with the templates), plus Python left dead by the switch (view-model fields, router helpers or template filters only the old templates used; confirmed by `vulture` and coverage). Rows are flipped to `deleted` in the same commit. A file still referenced by an unmigrated surface stays, and its row moves to T-UR15.

### ◻ T-UR05 [P] Auth
- Handoff: `pages/auth/login`, `login--error`, `reauth`, `reauth--error`; `register`, `invite`, `invite--expired` only if T-UR00 decided to wire them.
- Routes: login, logout, re-auth, passkey login.

### ◻ T-UR06 [P] Errors
- Handoff: `pages/errors/404`, `409`, `422`, `500`; `offline` per the T-UR00 decision.
- Error handlers render the new pages for full-page requests and the error summary fragment for HTMX requests.

### ◻ T-UR07 [P] Today
- Handoff: `pages/today` and its states (`--empty`, `--loading`, `--afford-over`, `--afford-invalid`, `--flash`); overlays `new-entry*` (happened, planned, repeats fixed, repeats formula, error, phone sheet), `promote--planned`, `promote--recurring`, `row-menu--upcoming`.
- Fragments: `today/upcoming-list`, `today/afford-result`, `rows/upcoming-row`, hero.
- The new-entry dialog is owned here; Ledger reuses it.

### ◻ T-UR08 [P] Accounts
- Handoff: `pages/accounts`, `accounts--empty`; overlays `new-account*`, `edit-account*`, `delete-account*`, `reconcile*`, `row-menu--account`.
- Fragments: `rows/account-row` (including the credit-limit line), `rows/reconcile-snapshot`, sparkline chart.

### ◻ T-UR09 [P] Ledger · actual → T-UR07
- Handoff: `pages/ledger/actual` (+ `--empty`, `--no-matches`, `--long`); overlays `edit-transaction*`, `row-menu--transaction`, `category-picker*`.
- Fragments: `ledger/filter-bar`, `ledger/bulk-bar`, `rows/transaction-row`, `rows/transaction-day`.

### ◻ T-UR10 [P] Ledger · planned, recurring, recently deleted → T-UR07
- Handoff: `pages/ledger/planned` (+ `--empty`), `recurring` (+ `--empty`), `recently-deleted`; overlays `edit-planned`, `edit-recurring*`, `override--occurrence`, `override--remove`, `row-menu--planned`, `row-menu--recurring`.
- Fragments: `rows/planned-row`, `rows/recurring-row`, `rows/deleted-planned`, `rows/deleted-category`.

### ◻ T-UR11 [P] Plan · budget and year
- Handoff: `pages/plan/budget`, `year`; overlays `override--budget-*`, `override--year-cell`, `period-picker*`, `row-menu--budget`.
- Fragments: `rows/budget-line`, `plan/unbudgeted-disclosure`, `rows/year-grid-row`, `rows/year-cell-editor`.

### ◻ T-UR12 [P] Plan · forecast and analytics
- Handoff: `pages/plan/forecast`, `analytics`; `charts/forecast`, `charts/income-vs-expense`, `charts/spend-by-category`.
- Fragments: `rows/forecast-month`, `rows/analytics-category`, `charts/*`. SVG geometry from the server per the handoff's chart notes (amends ADR-0054).

### ◻ T-UR13 [P] Settings · categories, currency and FX, preferences
- Handoff: `pages/settings/categories`, `currency-fx`, `preferences`; overlays `new-category*`, `edit-category`, `archive-category`.
- Fragments: `rows/category-row`. Theme switch (`theme-switch.js`) on Preferences.

### ◻ T-UR14 [P] Settings · security and users
- Handoff: `pages/settings/security` (+ `--error`), `users`; overlay `edit-user`.
- Fragments: `rows/session-row`, `rows/user-row`. Passkey add / remove keeps `passkeys.js` behaviour.

---

## Phase 3 — Cutover

### ◻ T-UR15 [S] Delete the old frontend (final sweep) → T-UR05..T-UR14
- **Files**: every remaining `removal.md` row: old `base.html`, what is left of `_partials/`, `partials/` and the per-feature template directories, `app.css`, `rising-dough.css`, `tailwind.css`, `tailwind.src.css`, `tokens.css`, `fonts.css`, `auth.css`, `settings-*.css`, old fonts, `favicon.svg`, old `static/js/*` (the kept behaviour JS already moved to `rd/js/` in T-UR04), remaining old visual baselines. Port `dev/components.html` from the handoff's `components.html`.
- **Toolchain**: Tailwind npm dependency and config, `just css-watch` and the Tailwind part of `just css`, the `tailwind-check` pre-commit hook, the old stylelint config, Tailwind steps in CI workflows and the Dockerfile.
- **Dead Python**: anything only the old frontend used (old-template view-model fields, helpers, filters, the v2 legacy redirects if T-UR00 decides they have served their purpose), found with `vulture` plus coverage on the full suite.
- **Harness leftovers**: allowlist entries and UI-map names that pointed at old markup; the old-UI `xfail`s that no longer apply.
- **Docs**: `CLAUDE.md` (stack: Tailwind gone), `docs/requirements.md` §3 stack and tooling lines, the `frontend-visual-audit` skill and any agent briefs that name old paths; ADR-0052, ADR-0053, ADR-0055 marked `Superseded by ADR-0107` and ADR-0050 marked superseded for visual direction, in the files and in `docs/adr/README.md`.
- **Operator**: delete the untracked `data/rising-dough-frontend/` copy from the main checkout (if not done after T-UT01).
- **Acceptance**: every `removal.md` row is `deleted` or `keep` with an ADR-0107 §2 reason; `test_old_frontend_removed.py` green; `grep -r` finds no reference to a removed path, `tailwind`, `app.css` or `rising-dough.css` outside `docs/adr/` and `docs/CHANGELOG.md`; `just ci` green; crawler inventory diff reviewed.

### ◻ T-UR16 [S] Full validation → T-UR15
- Crawler, all journeys, `just test-e2e-browsers` (Firefox, WebKit), axe on every page at 375 and 1440 in both themes, visual diff on every handoff page, `frontend-visual-audit` sweep at 320 / 375 / 768 / 1024 / 1440 / 1920 on every route, budgets from README (gzip sizes, LCP / CLS / INP on `/today`, `/ledger`, `/plan`), keyboard map (`g o/l/p/a/s`, `n`, `/`, `[` `]`, `?`, `⌘K`), reduced motion.
- Findings fixed or triaged with the operator; results attached to the release PR.

### ◻ T-UR17 [S] Release → T-UR16
- PR `ui/sourdough` → integration branch, then to `main` with a green `drill-gate` on its head SHA (ADR-0099). Smoke on drill (`mode=explore`) with the operator clicking through.
- ADR-0107 flipped to Accepted (if not already), `docs/CHANGELOG.md` entry, `derived.md` final.
