# Sourdough Redesign — Tasks

> **After the redesign, `tests/architecture/allowlists/template_logic.toml` must be empty (burned to zero, ADR-0130 amendment 2026-11-21); new templates add no entries.** Remediation T-Q237 and T-Q273 only burn down templates that survive the redesign; every other entry is deleted by this plan (surface tasks flip `removal.md` rows to `deleted` and delete the matching `template_logic.toml` entries; T-UR15 is not done while the file has an entry).

> **Transfer note (T-Q273, 2026-11-22): `template_logic.toml` holds 83 entries over 55 old templates; none survives, so remediation burned none.** Each surface task deletes the entries of the templates it removes (rule counts are one per expression; the new templates must not reproduce them: compute in the view model, use the `money` / `money_num` / `pct` / named date filters, no `{% set %}`, no literal currency codes, no `|float`).
> | Owner | Entries (templates) |
> |---|---|
> | T-UR04 (shared) | `_partials/combobox`, `_partials/segmented`, `_partials/components/{_amount,_button,_direction_badge,_heatmap_cell,_pace_tag,_period_header,_pill,_planned_net,_progress_bar,_segmented,_sparkline,_top_bar_add}`, `partials/{_flash,_nav,_pagination,_tabbar}`, `partials/transactions/{_form,_table}` |
> | T-UR06 | `errors/{404,409,422,500}` |
> | T-UR08 | `accounts/index`, `partials/accounts/{_card,_reconcile_modal,_row,_snapshot_item}` |
> | T-UR09, T-UR10 | `ledger/{index,_table,_recently_deleted}`, `partials/planned/{_form,_promote_inline_row,_row}`, `partials/recurring/{_form,_override_form,_promote_inline_row,_row}`, `recurring/index` |
> | T-UR13 | `partials/categories/_form`, `settings/{_drawer,_fx,_tabs,index}` |
> | T-UR14 | `settings/{_password_form,security}`, `settings/users/{_password-toast,_row,list}` |
> | T-UR15 | `dev/components` (3 currency literals; port from the handoff) |

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
- **`template_logic.toml` (ADR-0130 amendment 2026-11-21):** after the redesign the allowlist must be empty; new templates add no entries; surface tasks delete the entries of the templates they remove.
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

## Phase 2b — Scope added by the designer answers (2026-11-21, [ADR-0134](../../adr/0134-redesign-scope-decisions-from-the-designer-change-request.md))

These land in the redesign release (ADR-0107 §8). Each needs its own requirement text first (done in `docs/requirements.md`, ADR-0134 Consequences) and the per-surface loop in [README.md](README.md#per-surface-loop-test-first). Not started.

### ◻ T-UR18 [S] Invite email: cost evaluation (operator)
- Evaluate mail provider, Terraform and secret cost for sending invite email. Output: go or no-go recorded in ADR-0134 (amendment). On no-go the switch of T-UR19 stays off and the code is kept. ADR-0134 §1.

### ◻ T-UR19 [S] Invite email behind a config switch → T-UR18, T-UR20
- Send the invite email through an injected port (ADR-0021), behind a config switch, default off. No secret committed; Terraform and secret only if T-UR18 is go. ADR-0134 §1, ADR-0099.

### ◻ T-UR20 [P] Invites, add user, user row menu, forced change → T-UR14
- Invite model (migration), create invite with email and role, pending row with expiry, row menu copy link / resend / revoke; invite pages (AU08 and expired, used, invalid AU09); add user dialog with one-time credential dialog (not toast), duplicate email refused; reset and delete user with confirms (ledger entries stay); forced change page (ST10). Edit user dialog (name and member/admin, email read-only) as the first row-menu item before reset and delete; an admin's own row has no menu. Server-side guards, not only the hidden menu: edit refuses self-demotion and demoting the last admin and does not change the email (today `services/users.edit_user` allows self-demotion with a second admin and edits email; fix with tests asserting DB rows); delete keeps refusing self and last admin. ADR-0134 §10, §11, ADR-0061, ADR-0073.

### ◻ T-UR21 [P] First-run `/setup` page with one-time token → T-UR05
- Page on `/setup` (not `/auth/register*`), reachable only while no users exist and no bootstrap admin is configured, and only with a valid single-use setup token; 404 without it (no oracle). Token invalidated once the first admin is created, never committed, never logged. Errors: invalid email, credential under 12 characters, mismatch. Once any user exists it redirects to sign in. ADR-0134 §9.

### ◻ T-UR22 [S] Drills: bootstrap admin off by default, setup token in workflow output → T-UR21
- Keep `BUDGET_PLANNER_ADMIN_EMAIL` and Terraform `admin_email` (ADR-0061 §3) but off by default for drill deploys. Drill pipeline generates the per-deploy setup token and surfaces it in the job summary or the explore-drill URL (`/setup?token=...`). Prod behaviour unchanged. ADR-0134 §9, ADR-0099.

### ◻ T-UR23 [P] Account delete rule (blocked dialog) → T-UR08
- Service refuses delete while any transaction, planned or recurring item references the account; dialog links to them; state blocked by recurring only; final confirm otherwise. Tests assert DB state and audit. Requirement F2.8. ADR-0134 §3.

### ◻ T-UR24 [P] Remove inline promote routes → T-UR07, T-UR10
- Delete `GET /planned/{planned_id}/promote/inline`, `GET /recurring/{rule_id}/promote/inline`, their templates, UI-map names and route allowlist entries. ADR-0134 §5.

### ◻ T-UR25 [P] Offline save-failure handling → T-UR04
- HTMX request failure (no response) keeps an open dialog's typed input and shows the offline state (`errors/offline` markup); no service worker. ADR-0134 §4, ADR-0113.

### ◻ T-UR26 [deferred] Service worker for failed full page loads
- Deferred beyond the redesign release; needs its own ADR (ADR-0123, ADR-0113 CSP). Tracked here so the offline page is not wired to full-page failures until then. ADR-0134 §4.

### ◻ T-UR27 [P] Theme switch → T-UR13
- Preferences Appearance control (system, light, dark), default system, per browser, full light set. ADR-0134 §8.

### ◻ T-UR28 [P] Ledger export menu and credit-limit line → T-UR09
- `export` menu beside the Ledger Actual and Planned tabs (csv, parquet, current tab and filters, kept on phone, none on Recurring); credit-limit line under the account in new entry, edit and phone sheet (pink with `role=alert` over limit, saving allowed). ADR-0134 §2, §6.

---

## Phase 3 — Cutover

### ◻ T-UR15 [S] Delete the old frontend (final sweep) → T-UR05..T-UR14
- **Files**: every remaining `removal.md` row: old `base.html`, what is left of `_partials/`, `partials/` and the per-feature template directories, `app.css`, `rising-dough.css`, `tailwind.css`, `tailwind.src.css`, `tokens.css`, `fonts.css`, `auth.css`, `settings-*.css`, old fonts, `favicon.svg`, old `static/js/*` (the kept behaviour JS already moved to `rd/js/` in T-UR04), remaining old visual baselines. Port `dev/components.html` from the handoff's `components.html`.
- **Toolchain**: Tailwind npm dependency and config, `just css-watch` and the Tailwind part of `just css`, the `tailwind-check` pre-commit hook, the old stylelint config, Tailwind steps in CI workflows and the Dockerfile.
- **Dead Python**: anything only the old frontend used (old-template view-model fields, helpers, filters, the v2 legacy redirects if T-UR00 decides they have served their purpose), found with `vulture` plus coverage on the full suite.
- **Harness leftovers**: allowlist entries and UI-map names that pointed at old markup; the old-UI `xfail`s that no longer apply.
- **Docs**: `CLAUDE.md` (stack: Tailwind gone), `docs/requirements.md` §3 stack and tooling lines, the `frontend-visual-audit` skill and any agent briefs that name old paths; ADR-0052, ADR-0053, ADR-0055 marked `Superseded by ADR-0107` and ADR-0050 marked superseded for visual direction, in the files and in `docs/adr/README.md`.
- **Operator**: delete the untracked `data/rising-dough-frontend/` copy from the main checkout (if not done after T-UT01).
- **Acceptance**: `tests/architecture/allowlists/template_logic.toml` is empty (ADR-0130 amendment 2026-11-21); every `removal.md` row is `deleted` or `keep` with an ADR-0107 §2 reason; `test_old_frontend_removed.py` green; `grep -r` finds no reference to a removed path, `tailwind`, `app.css` or `rising-dough.css` outside `docs/adr/` and `docs/CHANGELOG.md`; `just ci` green; crawler inventory diff reviewed.

### ◻ T-UR16 [S] Full validation → T-UR15
- Crawler, all journeys, `just test-e2e-browsers` (Firefox, WebKit), axe on every page at 375 and 1440 in both themes, visual diff on every handoff page, `frontend-visual-audit` sweep at 320 / 375 / 768 / 1024 / 1440 / 1920 on every route, budgets from README (gzip sizes, LCP / CLS / INP on `/today`, `/ledger`, `/plan`), keyboard map (`g o/l/p/a/s`, `n`, `/`, `[` `]`, `?`, `⌘K`), reduced motion.
- Findings fixed or triaged with the operator; results attached to the release PR.
- **Hardening (from v3 T-D140d, ADR-0113)**: drop inline `style=` attributes and remove `'unsafe-inline'` from `style-src` in the prod CSP (from v3 T-D140d, ADR-0113). The Caddyfile CSP lives in `terraform/cloud-init/compose/Caddyfile.tpl`; the e2e CSP guard (T-D140c) parses it. Acceptance: no `style="` attribute in any rendered page (crawler and axe runs), and the CSP guard passes with `style-src 'self'` only.

### ◻ T-UR17 [S] Release → T-UR16
- PR `ui/sourdough` → integration branch, then to `main` with a green `drill-gate` on its head SHA (ADR-0099). Smoke on drill (`mode=explore`) with the operator clicking through.
- ADR-0107 flipped to Accepted (if not already), `docs/CHANGELOG.md` entry, `derived.md` final.
