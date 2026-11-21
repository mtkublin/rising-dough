# Feature-parity inventory

> **Task**: T-UT05 (docs only). **Decision**: [ADR-0106](../../adr/0106-ui-behaviour-test-harness.md) section 5. **Plan**: [README.md](README.md), [tasks.md](tasks.md).
> **Inventory date**: 2026-11-20, from `src/budget_planner/web/routers/*.py` (route list read from the live `app` object), `src/budget_planner/web/templates/**`, and the handoff `docs/design/rising-dough-frontend/` (`index.html`, `README.md`, every page).
> **Next step**: none. T-UT06 is done (2026-11-21): all 16 gap rows carry their resolution in the **Decision** column (designer answers and operator decisions, [ADR-0132](../../adr/0132-redesign-scope-decisions-from-the-designer-change-request.md)); copied to `../ui-redesign/derived.md`. The Status column keeps the 2026-11-20 inventory values.

## Summary

| Status | Rows | Meaning |
|---|---|---|
| `mapped` | 98 | Current feature has a handoff page, overlay or fragment. Differences are in Notes; they are behaviour or layout deltas, not gaps. |
| `no board` | 9 | Current feature the handoff does not draw. Resolved 2026-11-21, see Decision. |
| `handoff-only` | 7 | Drawn in the handoff, no counterpart in the current app (a new feature; needs its own requirement before wiring). Resolved 2026-11-21, see Decision. |
| `n/a` | 3 | Route with no user-visible surface (operator, framework or developer endpoints), listed so the route index is complete. |
| **Total** | 117 | |

**Gaps: 16, all resolved 2026-11-21** (9 `no board`, 7 `handoff-only`). Routes covered: 116 of 116. Handoff pages covered: 91 of 91 (plus `index.html`, `components.html` and `charts/*` as reference pages, see appendix B).

## How to read this

- **Handoff** column paths are relative to `docs/design/rising-dough-frontend/pages/` and written without `.html` (for example `overlays/reset-password` is `pages/overlays/reset-password.html`). `components.html` and `charts/...` are relative to the handoff root. Names in parentheses are fragments (`<!-- fragment: ... -->`) inside those pages.
- **Current template** paths are relative to `src/budget_planner/web/templates/`.
- **Route(s)** are `METHOD /path` exactly as registered (query strings such as `?tab=` are shown where they select the state). Legacy redirect routes have their own rows so the route index stays complete.
- `mapped` rows can still carry differences in Notes (placement, wording, key map, scopes). Those are redesign work, not gaps; only `no board` and `handoff-only` rows need an operator decision.
- Open design questions already tracked in `../ui-redesign/derived.md` (bulk-select entry point, inline promote variant, `g o` vs `g t`) are cross-referenced in Notes, not re-decided here.


## Shell and shared components

| ID | Surface | Feature / state | Route(s) | Current template | Handoff | Status | Notes | Decision |
|---|---|---|---|---|---|---|---|---|
| SH01 | Shell | Root redirect to Today | `GET /` | none (303 to `/today`) | `today` | mapped | Redirect only; the handoff has no routing. | |
| SH02 | Shell | Primary navigation: desktop rail, wordmark, active item, Settings link; mobile bottom tab bar with centre "+" | — | `partials/_nav.html`, `partials/_tabbar.html`, `base.html` | `today`, `accounts` (shell on every page) | mapped | Handoff md breakpoint 768 px switches rail to tab bar. App nav matches (Today, Ledger, Plan, Accounts, Settings). | |
| SH03 | Shell | Sign out (rail footer, mobile account bar) | `POST /auth/logout` | `partials/_nav.html`, `base.html` | `today` (header "sign out") | mapped | | |
| SH04 | Shell | New-entry entry points: rail and tab-bar "+", top-bar add button, key `n`; chips Happened / Planned / Repeats | `GET /add` | `partials/_add_entry_overlay.html`, `partials/_slideover.html`, `_partials/components/_top_bar_add.html` | `overlays/new-entry--happened`, `overlays/new-entry--planned`, `overlays/new-entry--repeats-fixed`, `overlays/new-entry--repeats-formula`, `overlays/new-entry--error`, `overlays/new-entry--phone-sheet` | mapped | Form contents are rows L15, L21, L25. Handoff draws it as a centred dialog (bottom sheet on phone); app uses a slide-over. | |
| SH05 | Shell | Command palette (Ctrl/Cmd K): filter, arrow keys, run | — (client side) | `partials/_palette.html`, `static/js/palette.js` | `overlays/command-palette`, `overlays/command-palette--filtered`, `overlays/command-palette--no-match` | mapped | App palette lists "Go to Budget `g b`"; handoff lists Plan `g p`. | |
| SH06 | Shell | Keyboard shortcuts cheatsheet (`?`) and key map | — (client side) | `partials/_shortcuts.html`, `partials/_cheatsheet.html`, `static/js/shortcuts.js` | `overlays/shortcuts` | mapped | App: `g o/l/a/b/s`, `n`, `/`, `[ ]`, `?`, Ctrl K, Esc. Handoff: `g o/l/p/a/s` (no `g b`), same others. Key map change is a behaviour change for the redesign. | |
| SH07 | Shell | Flash regions (polite and assertive), success flash after save | — | `base.html`, `partials/_flash.html` | `today--flash` | mapped | Handoff fragment `flash/success`. | |
| SH08 | Shell | Undo toast with auto-dismiss, driven by `HX-Trigger` `toast` payload with `undo_url` | via `POST /planned/batch/undo`, `POST /recurring/batch/undo` (see L24) | `_partials/components/_toast.html` | `today--flash` (fragment `toast/undo`) | mapped | Handoff dismisses after 8 s, pauses on hover/focus. Undo is wired only for batch promote and delete/archive responses in the app. | |
| SH09 | Shell | Row action menu (kebab) component | — | `_partials/kebab_menu.html`, `static/js/kebab.js` | `overlays/row-menu--transaction`, `overlays/row-menu--planned`, `overlays/row-menu--recurring`, `overlays/row-menu--account`, `overlays/row-menu--upcoming`, `overlays/row-menu--budget` | mapped | Actions per menu are listed in the owning feature rows. Handoff uses native popover, bottom action sheet on phone. | |
| SH10 | Shell | Category picker combobox (type to filter, arrows, Enter) | — | `_partials/combobox.html`, `static/js/combobox.js` | `overlays/category-picker`, `overlays/category-picker--no-match` | mapped | Handoff phone variant is a bottom sheet. | |
| SH11 | Shell | Form validation error summary (422 re-render of a dialog) | — (every form POST) | `partials/_form_errors.html` | `errors/422` (fragment `forms/error-summary`) | mapped | Per-form error states are in their own rows. | |
| SH12 | Shell | Theme switch (system, light, dark), saved per browser | — | none | `settings/preferences` | handoff-only | App ships a single theme. Handoff expects `theme.js` and a Preferences control. Needs a requirement before wiring. | app change, redesign release (designer + operator 2026-11-21): theme switch ships with the whole migration; default system; full light set drawn (ADR-0132 §8) |
| SH13 | Shell | Export CSV / Parquet (transactions, planned) | `GET /transactions/export`, `GET /planned/export` | links only in `transactions/index.html`, `planned/index.html` (not rendered; `/transactions` and `/planned` redirect) | — | no board | Endpoints are live but the current Ledger UI has no link to them. Decide: surface, drop, or keep API-only. | board now exists (designer 2026-11-21): `export` menu beside the Ledger tabs (actual, planned), csv or parquet, current tab and filters, kept on phone; Recurring has none. App change: add the control (ADR-0132 §6) |
| SH14 | Shell | Developer component gallery | `GET /dev/components` | `dev/components.html` | `components.html` (reference page) | n/a | Internal gallery; the handoff `components.html` is its analogue, not a user feature. | |
| SH15 | Shell | Operator endpoints: health, readiness, replication, audit tail | `GET /health`, `GET /ready`, `GET /health/replication`, `GET /debug/audit-tail` | none (JSON/plain) | — | n/a | Not user visible. Covered by contract tests (T-UT04a). | |
| SH16 | Shell | Static files and OpenAPI/docs endpoints | `GET /openapi.json`, `GET /docs`, `GET /docs/oauth2-redirect` | none | — | n/a | Framework defaults and the `/static` mount (not in the router list). Whether `/docs` should stay enabled is a security question, not a parity one. | |

## Auth and errors

| ID | Surface | Feature / state | Route(s) | Current template | Handoff | Status | Notes | Decision |
|---|---|---|---|---|---|---|---|---|
| AU01 | Auth | Sign in with email and password | `GET /auth/login`, `POST /auth/login` | `auth/login.html`, `auth/_layout.html` | `auth/login` | mapped | | |
| AU02 | Auth | Sign-in error state (bad credentials, rate limited) | `POST /auth/login` | `auth/login.html` | `auth/login--error` | mapped | Handoff shows one error variant; confirm lockout / rate-limit copy in T-UT04a. | |
| AU03 | Auth | Sign in with passkey | `POST /auth/login/begin`, `POST /auth/login/finish` | `auth/login.html`, `static/js/passkeys.js` | `auth/login` (button "sign in with passkey") | mapped | | |
| AU04 | Auth | Re-authenticate for sensitive actions (password) | `GET /auth/reauth`, `POST /auth/reauth` | `auth/reauth.html` | `auth/reauth` | mapped | | |
| AU05 | Auth | Re-authenticate error state | `POST /auth/reauth` | `auth/reauth.html` | `auth/reauth--error` | mapped | | |
| AU06 | Auth | Re-authenticate with passkey | `POST /auth/reauth/begin`, `POST /auth/reauth/finish` | `auth/reauth.html`, `static/js/passkeys.js` | `auth/reauth` | mapped | | |
| AU07 | Auth | First-run registration (create the first account) | — | none | `auth/register` | handoff-only | App has no self-registration; the first user comes from seed/CLI. `GET /auth/register` is a different legacy route (AU15). Needs a requirement first. | app change, redesign release: first-run page on a new path (`/setup`), only while no users exist and no bootstrap admin is configured; account becomes admin (ADR-0132 §9) Handoff pages: `auth/register`, `auth/register--error`. |
| AU08 | Auth | Accept an invitation (set password from link) | — | none | `auth/invite` | handoff-only | No invite model in the app (admins create users directly, row ST09). | app change, redesign release: invite page, email fixed by invite, person adds name and credential (ADR-0132 §10) Handoff pages: `auth/invite`, `auth/invite--invalid`, `auth/invite--used`. |
| AU09 | Auth | Invitation expired | — | none | `auth/invite--expired` | handoff-only | As AU08. | app change, redesign release: expired, already-used and invalid-link states; expired asks to get an admin to resend (ADR-0132 §10) Handoff pages: `auth/invite--expired`, `auth/invite--invalid`, `auth/invite--used`. |
| AU10 | Errors | Error 404 | — (exception handler) | `errors/404.html`, `errors/_shell.html` | `errors/404` | mapped | App shell is minimal (eyebrow, heading, "Back to dashboard"). Admin routes return the standard 404 for non-admins. | |
| AU11 | Errors | Error 409 | — (exception handler) | `errors/409.html` | `errors/409` | mapped | | |
| AU12 | Errors | Error 422 | — (exception handler) | `errors/422.html` | `errors/422` | mapped | | |
| AU13 | Errors | Error 500 | — (exception handler) | `errors/500.html` | `errors/500` | mapped | | |
| AU14 | Errors | Offline page | — | none (no service worker) | `errors/offline` | handoff-only | No PWA/offline support in v1 scope. | app change, redesign release, partly deferred: offline page and states kept; save-failure path (dialog keeps typed input) in the release; service worker deferred (ADR-0132 §4) |
| AU15 | Auth | Legacy redirects into Security: passkey registration page, sessions page | `GET /auth/register`, `GET /auth/sessions` | none (redirect to `/settings/security`) | `settings/security` | mapped | Redirect only (ADR-0075). | |

## Today

| ID | Surface | Feature / state | Route(s) | Current template | Handoff | Status | Notes | Decision |
|---|---|---|---|---|---|---|---|---|
| TD01 | Today | Hero: left to spend, per-day figure, days to next income / anchor | `GET /today` | `today/index.html` | `today` | mapped | | |
| TD02 | Today | Empty state (no data) | `GET /today` | `today/index.html` | `today--empty` | mapped | | |
| TD03 | Today | Loading state of the upcoming panel | `GET /today/upcoming` | `today/_upcoming.html` | `today--loading` | mapped | Handoff skeleton fragment `states/loading`. | |
| TD04 | Today | Upcoming list: overdue / due today / next 7 days / later groups, range 7 days, 30 days, all | `GET /today/upcoming` | `today/_upcoming.html`, `_partials/overdue_row.html` | `today` (fragments `today/upcoming-list`, `rows/upcoming-row`) | mapped | Handoff sections: Overdue, Due today, Next 30 days. App groups Next 7 days / Later. | |
| TD05 | Today | Upcoming row actions: promote (inline row), edit, skip next, override occurrence | `GET /planned/{planned_id}/promote/inline`, `GET /recurring/{rule_id}/promote/inline`, `POST /recurring/{rule_id}/skip-next` (see L23, L26, L28, L29) | `today/_upcoming.html` | `overlays/row-menu--upcoming` | mapped | Handoff opens the promote dialog instead of an inline row (see L23b). | |
| TD06 | Today | "Can I afford it?" amount check, result states | `GET /today/afford`, `GET /afford` | `today/_afford_preview.html`, `today/index.html` | `today` (fragment `today/afford-result`) | mapped | `/afford` is an alias of `/today/afford`. | |
| TD07 | Today | Afford result: over budget | `GET /today/afford` | `today/_afford_preview.html` | `today--afford-over` | mapped | | |
| TD08 | Today | Afford input invalid | `GET /today/afford` | `today/_afford_preview.html` | `today--afford-invalid` | mapped | | |
| TD09 | Today | Success flash after an action on Today | — | `partials/_flash.html` | `today--flash` | mapped | See SH07. | |
| TD10 | Today | Net-worth card: top account balances, "All N accounts", "Forecast" links | `GET /today` | `today/index.html` (netcard) | — | no board | Correction 2026-11-21: the Today board does draw this card (total, assets and liabilities, links); only the per-account list was dropped. | board exists (designer 2026-11-21): the Today board already draws total, assets and liabilities, "all N accounts", "forecast"; the per-account list was dropped on purpose. Parity row was wrong (ADR-0132 §2) |
| TD11 | Today | Promote all due, add planned, add recurring buttons in the Upcoming header | `POST /planned/batch/promote-due`, `POST /recurring/batch/promote-due` (see L24) | `today/index.html` | `today` ("promote all due") | mapped | Handoff shows promote-all-due with the success flash; add buttons go through the new-entry dialog. | |

## Ledger

| ID | Surface | Feature / state | Route(s) | Current template | Handoff | Status | Notes | Decision |
|---|---|---|---|---|---|---|---|---|
| L01 | Ledger | Ledger page with view tabs Actual / Planned / Recurring, `[ ]` cycles tabs | `GET /ledger` | `ledger/index.html` | `ledger/actual`, `ledger/planned`, `ledger/recurring` | mapped | | |
| L02 | Ledger | Actual view: day groups, transaction rows, daily nets, paging | `GET /ledger/table`, `GET /transactions/table` | `ledger/_table.html`, `partials/transactions/_table.html`, `partials/transactions/_row.html` | `ledger/actual`, `ledger/actual--long` | mapped | `GET /transactions/table` is a legacy fragment; check whether anything still calls it. | |
| L03 | Ledger | Actual: empty | `GET /ledger` | `partials/transactions/_empty.html` | `ledger/actual--empty` | mapped | | |
| L04 | Ledger | Actual: filters match nothing | `GET /ledger/table` | `ledger/_table.html` | `ledger/actual--no-matches` | mapped | | |
| L05 | Ledger | Planned: empty | `GET /ledger?view=planned` | `ledger/_table.html` | `ledger/planned--empty` | mapped | | |
| L06 | Ledger | Recurring: empty | `GET /ledger?view=recurring` | `ledger/_table.html` | `ledger/recurring--empty` | mapped | | |
| L07 | Ledger | Filter bar: date range, category, account, direction, search; phone filters toggle | `GET /ledger/table` | `ledger/index.html`, `partials/transactions/_filter_form.html` | `ledger/actual` (fragment `ledger/filter-bar`) | mapped | | |
| L08 | Ledger | Pagination | `GET /ledger/table` | `ledger/_table.html`, `partials/_pagination.html` | `ledger/actual` (fragment `ledger/pagination`) | mapped | | |
| L09 | Ledger | Planned view: rows with due date, status, promote / edit / delete | `GET /ledger/table`, `GET /planned/table` | `ledger/_table.html`, `partials/planned/_table.html`, `partials/planned/_row.html` | `ledger/planned` | mapped | `GET /planned/table` is a legacy fragment. | |
| L10 | Ledger | Recurring view: rows with next due, expandable formula and overrides | `GET /ledger/table` | `ledger/_table.html`, `partials/recurring/_row.html` | `ledger/recurring` | mapped | Handoff `expand.js` disclosure. | |
| L11 | Ledger | Monthly cash-flow summary strip above the Recurring view | `GET /ledger` | `ledger/index.html` (`rd-recurring-strip`) | — | no board | | dropped (designer 2026-11-21): covered by the Recurring hero (out, in, net per month); no separate strip (ADR-0132 §2) |
| L12 | Ledger | Bulk selection and bulk bar (delete selected) | per-row `POST /transactions/{txn_id}/delete`, `POST /planned/{planned_id}/delete` | `static/js/bulk-select.js`, `ledger/index.html` (`data-bulk-toolbar`) | `ledger/actual` (fragment `ledger/bulk-bar`) | mapped | Handoff has no visible entry point (README section 6.7); open question 1 in `ui-redesign/derived.md`. App deletes per row; no atomic bulk endpoint. | |
| L13 | Ledger | Recently deleted: transactions, planned, categories with restore | `GET /ledger/recently-deleted`, `POST /transactions/{txn_id}/restore`, `POST /planned/{planned_id}/restore`, `POST /categories/{category_id}/restore` | `ledger/_recently_deleted.html` | `ledger/recently-deleted` | mapped | Handoff fragments `rows/deleted-planned`, `rows/deleted-category`. | |
| L14 | Ledger | Legacy list URLs redirect into the Ledger views | `GET /transactions`, `GET /planned`, `GET /recurring` | none (302 to `/ledger?view=...`) | `ledger/actual`, `ledger/planned`, `ledger/recurring` | mapped | Redirect only. | |
| L15 | Ledger | New transaction (happened) form | `GET /transactions/new`, `POST /transactions` | `partials/transactions/_form.html` | `overlays/new-entry--happened`, `overlays/new-entry--error` | mapped | Also opened via `GET /add?when=happened` (SH04). | |
| L16 | Ledger | Edit transaction | `GET /transactions/{txn_id}/edit`, `POST /transactions/{txn_id}` | `partials/transactions/_form.html` | `overlays/edit-transaction`, `overlays/edit-transaction--error` | mapped | | |
| L17 | Ledger | Transit transfer between accounts (destination account) | `GET /transactions/new`, `GET /transactions/{txn_id}/edit` | `partials/transactions/_form.html` | `overlays/edit-transaction--transit` | mapped | Handoff `reveal.js` shows the destination only for Transit. | |
| L18 | Ledger | Credit-limit preview while entering a transaction on a liability account | `GET /transactions/_limit_preview` | `partials/transactions/_limit_preview.html` | — | no board | Handoff draws the credit line only on the account row (AC01). | board now exists (designer 2026-11-21): line under the account in new entry, edit and phone sheet; over limit turns pink with a warning mark (`role=alert`), saving allowed. App change: restyle the hint (ADR-0132 §2) Handoff pages: `overlays/new-entry--over-limit`. |
| L19 | Ledger | Delete transaction with undo | `POST /transactions/{txn_id}/delete` | `ledger/_table.html` (row menu) | `overlays/row-menu--transaction` | mapped | Handoff delete = row removal plus `toast/undo`. Restore is in L13. | |
| L20 | Ledger | New planned entry | `GET /planned/new`, `POST /planned` | `partials/planned/_form.html` | `overlays/new-entry--planned` | mapped | | |
| L21 | Ledger | Edit planned entry | `GET /planned/{planned_id}/edit`, `POST /planned/{planned_id}` | `partials/planned/_form.html` | `overlays/edit-planned` | mapped | | |
| L22 | Ledger | Delete planned entry with undo | `POST /planned/{planned_id}/delete` | `ledger/_table.html` (row menu) | `overlays/row-menu--planned` | mapped | | |
| L23 | Ledger | Promote planned entry to a transaction (dialog) | `GET /planned/{planned_id}/promote`, `POST /planned/{planned_id}/promote` | `partials/planned/_promote_modal.html` | `overlays/promote--planned` | mapped | | |
| L23b | Ledger | Promote planned / recurring as an inline row variant | `GET /planned/{planned_id}/promote/inline`, `GET /recurring/{rule_id}/promote/inline` | `partials/planned/_promote_inline_row.html`, `partials/recurring/_promote_inline_row.html` | — | no board | Handoff drops the inline variant (README section 6, open question 2 in `derived.md`). | dropped (designer 2026-11-21, operator 2026-11-21): promote is dialog-only; remove the two `promote/inline` routes in the redesign (ADR-0132 §5) |
| L24 | Ledger | Promote all due (planned and recurring) with batch undo | `POST /planned/batch/promote-due`, `POST /planned/batch/undo`, `POST /recurring/batch/promote-due`, `POST /recurring/batch/undo` | `today/index.html`, `ledger/index.html` | `today` ("promote all due"), `today--flash` | mapped | Undo is a toast (SH08). | |
| L25 | Ledger | New recurring rule: fixed amount | `GET /recurring/new`, `POST /recurring` | `partials/recurring/_form.html` | `overlays/new-entry--repeats-fixed` | mapped | | |
| L25b | Ledger | New recurring rule: formula amount | `GET /recurring/new`, `POST /recurring` | `partials/recurring/_form.html` | `overlays/new-entry--repeats-formula` | mapped | | |
| L25c | Ledger | Formula live preview | `POST /recurring/formula/preview` | `partials/recurring/_formula_preview.html` | `overlays/edit-recurring--formula` (fragments `fields/formula`, `fields/formula-component`) | mapped | | |
| L26 | Ledger | Edit recurring rule: fixed | `GET /recurring/{rule_id}/edit`, `POST /recurring/{rule_id}` | `partials/recurring/_form.html` | `overlays/edit-recurring--fixed` | mapped | | |
| L26b | Ledger | Edit recurring rule: formula, empty formula, picking components, incomplete formula | `GET /recurring/{rule_id}/edit`, `POST /recurring/{rule_id}` | `partials/recurring/_form.html` | `overlays/edit-recurring--formula`, `overlays/edit-recurring--empty`, `overlays/edit-recurring--picking`, `overlays/edit-recurring--incomplete` | mapped | | |
| L27 | Ledger | Deactivate recurring rule | `POST /recurring/{rule_id}/deactivate` | `ledger/_table.html` (row menu) | `overlays/row-menu--recurring` | mapped | App has no restore for a deactivated rule; handoff menu has "delete" with undo toast. | |
| L28 | Ledger | Skip next occurrence | `POST /recurring/{rule_id}/skip-next` | `ledger/_table.html`, `today/_upcoming.html` | `overlays/row-menu--recurring`, `overlays/row-menu--upcoming` | mapped | | |
| L29 | Ledger | Override one occurrence (amount/date), remove an override | `GET /recurring/{rule_id}/overrides/new`, `POST /recurring/{rule_id}/overrides`, `POST /recurring/{rule_id}/overrides/{occurrence_date}/delete` | `partials/recurring/_override_form.html`, `ledger/_table.html` | `overlays/override--occurrence` | mapped | Handoff `override--remove` is the budget-override removal (row PL05), not this one. | |
| L30 | Ledger | Promote recurring occurrence (dialog) | `GET /recurring/{rule_id}/promote`, `POST /recurring/{rule_id}/promote` | `partials/recurring/_promote_modal.html` | `overlays/promote--recurring` | mapped | | |

## Plan and Budget

| ID | Surface | Feature / state | Route(s) | Current template | Handoff | Status | Notes | Decision |
|---|---|---|---|---|---|---|---|---|
| PL01 | Plan | Plan page with tabs Budget / Year / Forecast / Analytics | `GET /plan` | `plan/index.html` | `plan/budget`, `plan/year`, `plan/forecast`, `plan/analytics` | mapped | Tab chosen by `?tab=`. | |
| PL02 | Plan | Budget tab: category lines, planned / actual / used bar / remaining | `GET /plan` | `plan/_budget_tab.html` | `plan/budget` (fragment `rows/budget-line`) | mapped | Handoff bars are block characters, 20 cells (10 on phone). | |
| PL03 | Plan | Left to spend per day and income anchor line on the Budget tab | `GET /plan` | `plan/_budget_tab.html` | `plan/budget` | mapped | | |
| PL04 | Plan | Period navigation: previous / next month and year, month picker popover | `GET /plan` | `plan/index.html` | `plan/budget` (fragments `plan/period-nav`, `popovers/period-picker`), `overlays/period-picker`, `overlays/period-picker--year` | mapped | Handoff uses `hx-push-url` with `?period=YYYY-MM` / `?year=`; app uses `?year=&month=`. | |
| PL05 | Plan | Budget override for a category: this month / every month / default, and remove | `GET /budget/rules/{category_id}/overrides/new`, `POST /budget/rules/{category_id}/overrides` | `partials/budget/_override_form.html` | `overlays/override--budget-month`, `overlays/override--budget-every`, `overlays/override--budget-default`, `overlays/override--remove`, `overlays/row-menu--budget` | mapped | App scopes are one-off / recurring / default (radio `tier`); there is no "remove override" confirm in the app. | |
| PL06 | Plan | Year grid tab: categories by 12 months, cell states, legend, phone cards | `GET /plan?tab=year`, `GET /budget/yearly` | `plan/_year_tab.html`, `budget/_yearly.html` | `plan/year`, `charts/year-grid` (fragment `rows/year-grid-row`) | mapped | | |
| PL07 | Plan | Year grid inline cell editor (set one-off, recurring, default) | `POST /budget/one-off/{category_id}/{year}/{month}`, `POST /budget/recurring/{category_id}/{month}`, `POST /budget/defaults/{category_id}` | `plan/_year_tab.html`, `budget/_yearly.html` | `overlays/override--year-cell` (fragment `rows/year-cell-editor`) | mapped | Handoff cell editor has no board (derived from the design system). | |
| PL08 | Plan | Unbudgeted categories disclosure | `GET /plan` | `plan/_budget_tab.html` (on Budget tab) | `plan/year` (fragment `plan/unbudgeted-disclosure`) | mapped | Handoff shows it on the Year tab; app shows it on the Budget tab. | |
| PL09 | Plan | Forecast tab: projected balance chart, horizon, summary, monthly table | `GET /plan?tab=forecast`, `GET /forecast`, `GET /forecast/view` | `plan/_forecast_tab.html`, `forecast/index.html`, `partials/forecast/_chart.html`, `partials/forecast/_table.html`, `partials/forecast/_view.html` | `plan/forecast`, `charts/forecast` (fragments `charts/forecast`, `rows/forecast-month`) | mapped | `/forecast` and `/forecast/view` are the standalone page and its fragment, still live. | |
| PL10 | Plan | Analytics tab: spend by category, income vs expense, largest single items | `GET /plan/analytics`, `GET /plan?tab=analytics` | `plan/_analytics_tab.html`, `plan/_analytics_bundle.html` | `plan/analytics`, `charts/spend-by-category`, `charts/income-vs-expense` | mapped | Sparkline chart `charts/sparkline` is the hero/row sparkline (see AC01). | |
| PL11 | Plan | Legacy Budget page (summary, rules with defaults, yearly) | `GET /budget`, `GET /budget/manage`, `GET /budget-legacy`, `GET /analytics` | `budget/index.html`, `budget/_yearly.html` | `plan/budget` | mapped | `/budget` is still a live, separate page; `/budget/manage`, `/analytics`, `/budget-legacy` redirect. The handoff has no standalone Budget page. | |
| PL12 | Plan | Set income anchor category | `POST /budget/preferences/income-anchor` | `settings/_categories.html` | `settings/categories` ("INCOME ANCHOR") | mapped | | |

## Accounts

| ID | Surface | Feature / state | Route(s) | Current template | Handoff | Status | Notes | Decision |
|---|---|---|---|---|---|---|---|---|
| AC01 | Accounts | Accounts list: net worth, totals, per-account balance, credit line on liabilities | `GET /accounts` | `accounts/index.html`, `partials/accounts/_row.html`, `partials/accounts/_totals.html`, `partials/accounts/_fortune_split.html` | `accounts`, `charts/sparkline` (fragment `rows/account-row`) | mapped | | |
| AC02 | Accounts | Accounts: empty | `GET /accounts` | `accounts/index.html` | `accounts--empty` | mapped | | |
| AC03 | Accounts | "Last checked" freshness per account | `GET /accounts/last-checked` | `partials/accounts/_last_checked.html` | `accounts` ("checked" column) | mapped | | |
| AC04 | Accounts | New account (empty, filled, validation error) | `GET /accounts/new`, `POST /accounts` | `partials/accounts/_form.html` | `overlays/new-account`, `overlays/new-account--filled`, `overlays/new-account--error` | mapped | | |
| AC05 | Accounts | Edit account (asset and liability with credit limit) | `GET /accounts/{account_id}/edit`, `POST /accounts/{account_id}` | `partials/accounts/_form.html` | `overlays/edit-account`, `overlays/edit-account--liability` | mapped | | |
| AC06 | Accounts | Delete account | `POST /accounts/{account_id}/delete` | `accounts/index.html`, `partials/accounts/_row.html` | `overlays/delete-account` | mapped | Handoff uses an alertdialog confirm; app posts straight from the menu. | |
| AC07 | Accounts | Delete account refused because it still has transactions | `POST /accounts/{account_id}/delete` | none | `overlays/delete-account--blocked` | handoff-only | `delete_account` soft-deletes unconditionally; the blocking rule does not exist. Needs a requirement before wiring. | app change, redesign release: refuse delete while any transaction, planned or recurring item points at the account; dialog links to them; else final confirm (ADR-0132 §3) Handoff pages: `overlays/delete-account--blocked`, `overlays/delete-account--blocked-planned`. |
| AC08 | Accounts | Reconcile (asset and liability): compare balance, record adjustment | `GET /accounts/{account_id}/reconcile`, `POST /accounts/{account_id}/reconcile` | `partials/accounts/_reconcile_modal.html` | `overlays/reconcile`, `overlays/reconcile--liability` | mapped | | |
| AC09 | Accounts | Balance snapshots inside the reconcile panel | `POST /accounts/{account_id}/snapshot` | `partials/accounts/_snapshot_item.html`, `partials/accounts/_card.html` | `overlays/reconcile` (fragment `rows/reconcile-snapshot`) | mapped | | |
| AC10 | Accounts | Account row menu | — | `partials/accounts/_row.html` | `overlays/row-menu--account` | mapped | See SH09. | |

## Settings

| ID | Surface | Feature / state | Route(s) | Current template | Handoff | Status | Notes | Decision |
|---|---|---|---|---|---|---|---|---|
| ST01 | Settings | Settings page with tab strip (Categories, Currency & FX, Preferences, Security, Users for admins) | `GET /settings`, `GET /settings/close` | `settings/index.html`, `settings/_tabs.html`, `settings/_drawer.html` | `settings/categories` | mapped | `/settings/close` returns an empty fragment (legacy drawer). Tab chosen by `?tab=`. | |
| ST02 | Settings | Categories list grouped Expense / Income / System | `GET /settings?tab=categories` | `settings/_categories.html`, `partials/categories/_row.html` | `settings/categories` (fragment `rows/category-row`) | mapped | | |
| ST03 | Settings | New category (empty, filled, validation error) | `GET /categories/new`, `POST /categories` | `partials/categories/_form.html` | `overlays/new-category`, `overlays/new-category--filled`, `overlays/new-category--error` | mapped | | |
| ST04 | Settings | Edit category | `GET /categories/{category_id}/edit`, `POST /categories/{category_id}` | `partials/categories/_form.html` | `overlays/edit-category` | mapped | | |
| ST05 | Settings | Archive / restore / delete category | `POST /categories/{category_id}/archive`, `POST /categories/{category_id}/delete`, `POST /categories/{category_id}/restore` | `settings/_categories.html` | `overlays/archive-category` | mapped | App has both archive and delete endpoints (system categories answer 409); the handoff has one archive dialog. Restore lives in Recently deleted (L13). | |
| ST06 | Settings | Legacy categories URL redirects to Settings | `GET /categories` | none (302) | `settings/categories` | mapped | | |
| ST07 | Settings | Currency and FX tab: cached rates table | `GET /settings?tab=fx` | `settings/_fx.html` | `settings/currency-fx` | mapped | App table is read-only: pair, as-of, rate. Check the handoff page for extra controls in T-UT04. | |
| ST08 | Settings | Preferences tab: base currency and timezone (read-only) | `GET /settings?tab=prefs` | `settings/_prefs.html` | `settings/preferences` | mapped | Handoff adds Appearance (theme), see SH12. | |
| ST09 | Settings | Security: change password section | `GET /settings/password`, `POST /settings/password` | `settings/security.html`, `settings/password.html`, `settings/_password_form.html` | `settings/security` | mapped | App has a separate page; handoff has an inline section in Security. | |
| ST10 | Settings | Forced password change after admin reset (must-change gate) | `GET /settings/password`, `POST /settings/password` | `settings/password.html` ("Set a new password") | — | no board | Middleware redirects every page here until done. | board now exists (designer 2026-11-21): "Set a new password" (desktop, error, phone); kept for direct adds and resets (ADR-0132 §2, §10) Handoff pages: `auth/force-password`, `auth/force-password--error`. |
| ST11 | Settings | Security: passkey list, add, remove | `GET /settings/security`, `POST /auth/register/begin`, `POST /auth/register/finish`, `POST /auth/passkeys/{credential_id}/revoke` | `settings/security.html`, `static/js/passkeys.js` | `settings/security` | mapped | | |
| ST12 | Settings | Security: active sessions list and sign out a device | `POST /auth/sessions/{handle}/revoke` | `settings/security.html` | `settings/security` (fragment `rows/session-row`) | mapped | | |
| ST13 | Settings | Security: validation error states | `POST /settings/password`, `POST /auth/register/finish` | `settings/security.html` | `settings/security--error` | mapped | | |
| ST14 | Settings | Users list (admin only; 404 for others) | `GET /settings/users` | `settings/users/list.html`, `settings/users/_table.html`, `settings/users/_row.html` | `settings/users` (fragment `rows/user-row`) | mapped | App columns: user, role, added, last seen. Handoff: email, role, last seen, status (active / invited). | |
| ST15 | Settings | Add user directly (email, name, admin flag) with one-time generated password toast | `POST /settings/users` | `settings/users/list.html`, `settings/users/_add-errors.html`, `settings/users/_password-toast.html` | — | no board | Handoff draws an invite-link flow instead (row ST16). | board now exists (designer 2026-11-21): add user dialog (email, name, member/admin), one-time credential shown once in a dialog; duplicate email refused. Kept beside invites (ADR-0132 §10) Handoff pages: `overlays/add-user`, `overlays/add-user--error`, `overlays/one-time-password`. |
| ST16 | Settings | Invite someone by email and role, shows "invited, expires" status | — | none | `settings/users` ("create invite link") | handoff-only | No invite model in the app (see AU08, AU09). Needs a requirement first. | app change, redesign release: invites beside direct add; copy link, resend, revoke; email sending behind a config switch after a cost evaluation (ADR-0132 §1, §10) Handoff pages: `overlays/invite-user`, `overlays/invite-user--error`, `overlays/revoke-invite`. |
| ST17 | Settings | Edit user | `GET /settings/users/{user_id}/edit`, `POST /settings/users/{user_id}` | `settings/users/edit.html` | `overlays/edit-user` (restored by the 2026-11-21 delta) | board now exists | Kept by the designer: name + member/admin, email read-only, first item of the row menu, own row has no menu (ADR-0132 §11; T-UR20). | resolved | |
| ST18 | Settings | Reset a user's password | `POST /settings/users/{user_id}/reset-password` | `settings/users/_row.html`, `settings/users/_password-toast.html` | — | no board | | board now exists (designer 2026-11-21): row menu, reset, confirm, one-time credential dialog, forced change (ADR-0132 §10) Handoff pages: `overlays/reset-password`, `overlays/one-time-password`. |
| ST19 | Settings | Delete a user | `POST /settings/users/{user_id}/delete` | `settings/users/_row.html` | — | no board | | board now exists (designer 2026-11-21): row menu, delete user, destructive confirm; their ledger entries stay (ADR-0132 §10) Handoff pages: `overlays/delete-user`. |

## Gaps and their resolutions (T-UT06)

| ID | Status | Feature | Handoff reference | Decision |
|---|---|---|---|---|
| SH12 | `handoff-only` | Theme switch (system, light, dark), saved per browser | `settings/preferences` | app change, redesign release (designer + operator 2026-11-21): theme switch ships with the whole migration; default system; full light set drawn (ADR-0132 §8) |
| SH13 | `no board` | Export CSV / Parquet (transactions, planned) | — | board now exists (designer 2026-11-21): `export` menu beside the Ledger tabs (actual, planned), csv or parquet, current tab and filters, kept on phone; Recurring has none. App change: add the control (ADR-0132 §6) |
| AU07 | `handoff-only` | First-run registration (create the first account) | `auth/register` | app change, redesign release: first-run page on a new path (`/setup`), only while no users exist and no bootstrap admin is configured; account becomes admin (ADR-0132 §9) Handoff pages: `auth/register`, `auth/register--error`. |
| AU08 | `handoff-only` | Accept an invitation (set password from link) | `auth/invite` | app change, redesign release: invite page, email fixed by invite, person adds name and credential (ADR-0132 §10) Handoff pages: `auth/invite`, `auth/invite--invalid`, `auth/invite--used`. |
| AU09 | `handoff-only` | Invitation expired | `auth/invite--expired` | app change, redesign release: expired, already-used and invalid-link states; expired asks to get an admin to resend (ADR-0132 §10) Handoff pages: `auth/invite--expired`, `auth/invite--invalid`, `auth/invite--used`. |
| AU14 | `handoff-only` | Offline page | `errors/offline` | app change, redesign release, partly deferred: offline page and states kept; save-failure path (dialog keeps typed input) in the release; service worker deferred (ADR-0132 §4) |
| TD10 | `no board` | Net-worth card: top account balances, "All N accounts", "Forecast" links | — | board exists (designer 2026-11-21): the Today board already draws total, assets and liabilities, "all N accounts", "forecast"; the per-account list was dropped on purpose. Parity row was wrong (ADR-0132 §2) |
| L11 | `no board` | Monthly cash-flow summary strip above the Recurring view | — | dropped (designer 2026-11-21): covered by the Recurring hero (out, in, net per month); no separate strip (ADR-0132 §2) |
| L18 | `no board` | Credit-limit preview while entering a transaction on a liability account | — | board now exists (designer 2026-11-21): line under the account in new entry, edit and phone sheet; over limit turns pink with a warning mark (`role=alert`), saving allowed. App change: restyle the hint (ADR-0132 §2) Handoff pages: `overlays/new-entry--over-limit`. |
| L23b | `no board` | Promote planned / recurring as an inline row variant | — | dropped (designer 2026-11-21, operator 2026-11-21): promote is dialog-only; remove the two `promote/inline` routes in the redesign (ADR-0132 §5) |
| AC07 | `handoff-only` | Delete account refused because it still has transactions | `overlays/delete-account--blocked` | app change, redesign release: refuse delete while any transaction, planned or recurring item points at the account; dialog links to them; else final confirm (ADR-0132 §3) Handoff pages: `overlays/delete-account--blocked`, `overlays/delete-account--blocked-planned`. |
| ST10 | `no board` | Forced password change after admin reset (must-change gate) | — | board now exists (designer 2026-11-21): "Set a new password" (desktop, error, phone); kept for direct adds and resets (ADR-0132 §2, §10) Handoff pages: `auth/force-password`, `auth/force-password--error`. |
| ST15 | `no board` | Add user directly (email, name, admin flag) with one-time generated password toast | — | board now exists (designer 2026-11-21): add user dialog (email, name, member/admin), one-time credential shown once in a dialog; duplicate email refused. Kept beside invites (ADR-0132 §10) Handoff pages: `overlays/add-user`, `overlays/add-user--error`, `overlays/one-time-password`. |
| ST16 | `handoff-only` | Invite someone by email and role, shows "invited, expires" status | `settings/users` ("create invite link") | app change, redesign release: invites beside direct add; copy link, resend, revoke; email sending behind a config switch after a cost evaluation (ADR-0132 §1, §10) Handoff pages: `overlays/invite-user`, `overlays/invite-user--error`, `overlays/revoke-invite`. |
| ST18 | `no board` | Reset a user's password | — | board now exists (designer 2026-11-21): row menu, reset, confirm, one-time credential dialog, forced change (ADR-0132 §10) Handoff pages: `overlays/reset-password`, `overlays/one-time-password`. |
| ST19 | `no board` | Delete a user | — | board now exists (designer 2026-11-21): row menu, delete user, destructive confirm; their ledger entries stay (ADR-0132 §10) Handoff pages: `overlays/delete-user`. |

## Appendix A: Route index

Every route registered on the app, with the parity rows that cover it. Generated from the live route table on 2026-11-20 (116 method+path pairs; `HEAD` aliases omitted).

| Route | Rows |
|---|---|
| `GET /health` | SH15 |
| `GET /ready` | SH15 |
| `GET /health/replication` | SH15 |
| `GET /auth/login` | AU01 |
| `POST /auth/login` | AU01, AU02 |
| `POST /auth/login/begin` | AU03 |
| `POST /auth/login/finish` | AU03 |
| `POST /auth/logout` | SH03 |
| `GET /auth/register` | AU15 |
| `POST /auth/register/begin` | ST11 |
| `POST /auth/register/finish` | ST11, ST13 |
| `GET /auth/sessions` | AU15 |
| `POST /auth/sessions/{handle}/revoke` | ST12 |
| `POST /auth/passkeys/{credential_id}/revoke` | ST11 |
| `GET /auth/reauth` | AU04 |
| `POST /auth/reauth` | AU04, AU05 |
| `POST /auth/reauth/begin` | AU06 |
| `POST /auth/reauth/finish` | AU06 |
| `GET /transactions` | L14 |
| `GET /transactions/_limit_preview` | L18 |
| `GET /transactions/table` | L02 |
| `GET /transactions/new` | L15, L17 |
| `POST /transactions` | L15 |
| `GET /transactions/{txn_id}/edit` | L16, L17 |
| `POST /transactions/{txn_id}` | L16 |
| `POST /transactions/{txn_id}/delete` | L12, L19 |
| `POST /transactions/{txn_id}/restore` | L13 |
| `GET /transactions/export` | SH13 |
| `GET /accounts` | AC01, AC02 |
| `GET /accounts/last-checked` | AC03 |
| `GET /accounts/new` | AC04 |
| `POST /accounts` | AC04 |
| `GET /accounts/{account_id}/edit` | AC05 |
| `POST /accounts/{account_id}` | AC05 |
| `POST /accounts/{account_id}/delete` | AC06, AC07 |
| `POST /accounts/{account_id}/snapshot` | AC09 |
| `GET /accounts/{account_id}/reconcile` | AC08 |
| `POST /accounts/{account_id}/reconcile` | AC08 |
| `GET /categories` | ST06 |
| `GET /categories/new` | ST03 |
| `POST /categories` | ST03 |
| `GET /categories/{category_id}/edit` | ST04 |
| `POST /categories/{category_id}` | ST04 |
| `POST /categories/{category_id}/delete` | ST05 |
| `POST /categories/{category_id}/archive` | ST05 |
| `POST /categories/{category_id}/restore` | L13, ST05 |
| `GET /planned` | L14 |
| `POST /planned/batch/promote-due` | TD11, L24 |
| `POST /planned/batch/undo` | SH08, L24 |
| `GET /planned/table` | L09 |
| `GET /planned/new` | L20 |
| `POST /planned` | L20 |
| `GET /planned/{planned_id}/edit` | L21 |
| `POST /planned/{planned_id}` | L21 |
| `POST /planned/{planned_id}/delete` | L12, L22 |
| `POST /planned/{planned_id}/restore` | L13 |
| `GET /planned/{planned_id}/promote` | L23 |
| `GET /planned/{planned_id}/promote/inline` | TD05, L23b |
| `POST /planned/{planned_id}/promote` | L23 |
| `GET /planned/export` | SH13 |
| `GET /recurring` | L14 |
| `GET /recurring/new` | L25, L25b |
| `POST /recurring` | L25, L25b |
| `POST /recurring/batch/promote-due` | TD11, L24 |
| `POST /recurring/batch/undo` | SH08, L24 |
| `POST /recurring/formula/preview` | L25c |
| `GET /recurring/{rule_id}/edit` | L26, L26b |
| `POST /recurring/{rule_id}` | L26, L26b |
| `POST /recurring/{rule_id}/deactivate` | L27 |
| `GET /recurring/{rule_id}/overrides/new` | L29 |
| `POST /recurring/{rule_id}/overrides` | L29 |
| `POST /recurring/{rule_id}/overrides/{occurrence_date}/delete` | L29 |
| `GET /recurring/{rule_id}/promote` | L30 |
| `GET /recurring/{rule_id}/promote/inline` | TD05, L23b |
| `POST /recurring/{rule_id}/promote` | L30 |
| `POST /recurring/{rule_id}/skip-next` | TD05, L28 |
| `GET /budget/yearly` | PL06 |
| `GET /budget/rules/{category_id}/overrides/new` | PL05 |
| `POST /budget/rules/{category_id}/overrides` | PL05 |
| `GET /budget` | PL11 |
| `GET /budget/manage` | PL11 |
| `POST /budget/defaults/{category_id}` | PL07 |
| `POST /budget/recurring/{category_id}/{month}` | PL07 |
| `POST /budget/preferences/income-anchor` | PL12 |
| `POST /budget/one-off/{category_id}/{year}/{month}` | PL07 |
| `GET /forecast` | PL09 |
| `GET /forecast/view` | PL09 |
| `GET /analytics` | PL11 |
| `GET /settings` | ST01, ST02, ST07, ST08 |
| `GET /settings/close` | ST01 |
| `GET /settings/users` | ST14 |
| `POST /settings/users` | ST15 |
| `GET /settings/users/{user_id}/edit` | ST17 |
| `POST /settings/users/{user_id}` | ST17 |
| `POST /settings/users/{user_id}/reset-password` | ST18 |
| `POST /settings/users/{user_id}/delete` | ST19 |
| `GET /settings/password` | ST09, ST10 |
| `POST /settings/password` | ST09, ST10, ST13 |
| `GET /settings/security` | ST11 |
| `GET /debug/audit-tail` | SH15 |
| `GET /ledger` | L01, L03, L05, L06, L11 |
| `GET /ledger/table` | L02, L04, L07, L08, L09, L10 |
| `GET /ledger/recently-deleted` | L13 |
| `GET /` | SH01 |
| `GET /today` | TD01, TD02, TD10 |
| `GET /today/upcoming` | TD03, TD04 |
| `GET /today/afford` | TD06, TD07, TD08 |
| `GET /afford` | TD06 |
| `GET /add` | SH04 |
| `GET /plan` | PL01, PL02, PL03, PL04, PL06, PL08, PL09, PL10 |
| `GET /plan/analytics` | PL10 |
| `GET /budget-legacy` | PL11 |
| `GET /dev/components` | SH14 |
| `GET /openapi.json` | SH16 |
| `GET /docs` | SH16 |
| `GET /docs/oauth2-redirect` | SH16 |

## Appendix B: Handoff page index

Every page under `docs/design/rising-dough-frontend/pages/` with the parity rows that cover it (91 pages).

| Handoff page | Rows |
|---|---|
| `accounts` | SH02, AC01, AC03 |
| `accounts--empty` | AC02 |
| `auth/invite` | AU08 |
| `auth/invite--expired` | AU09 |
| `auth/login` | AU01, AU03 |
| `auth/login--error` | AU02 |
| `auth/reauth` | AU04, AU06 |
| `auth/reauth--error` | AU05 |
| `auth/register` | AU07 |
| `errors/404` | AU10 |
| `errors/409` | AU11 |
| `errors/422` | SH11, AU12 |
| `errors/500` | AU13 |
| `errors/offline` | AU14 |
| `ledger/actual` | L01, L02, L07, L08, L12, L14 |
| `ledger/actual--empty` | L03 |
| `ledger/actual--long` | L02 |
| `ledger/actual--no-matches` | L04 |
| `ledger/planned` | L01, L09, L14 |
| `ledger/planned--empty` | L05 |
| `ledger/recently-deleted` | L13 |
| `ledger/recurring` | L01, L10, L14 |
| `ledger/recurring--empty` | L06 |
| `overlays/archive-category` | ST05 |
| `overlays/category-picker` | SH10 |
| `overlays/category-picker--no-match` | SH10 |
| `overlays/command-palette` | SH05 |
| `overlays/command-palette--filtered` | SH05 |
| `overlays/command-palette--no-match` | SH05 |
| `overlays/delete-account` | AC06 |
| `overlays/delete-account--blocked` | AC07 |
| `overlays/edit-account` | AC05 |
| `overlays/edit-account--liability` | AC05 |
| `overlays/edit-category` | ST04 |
| `overlays/edit-planned` | L21 |
| `overlays/edit-recurring--empty` | L26b |
| `overlays/edit-recurring--fixed` | L26 |
| `overlays/edit-recurring--formula` | L25c, L26b |
| `overlays/edit-recurring--incomplete` | L26b |
| `overlays/edit-recurring--picking` | L26b |
| `overlays/edit-transaction` | L16 |
| `overlays/edit-transaction--error` | L16 |
| `overlays/edit-transaction--transit` | L17 |
| `overlays/new-account` | AC04 |
| `overlays/new-account--error` | AC04 |
| `overlays/new-account--filled` | AC04 |
| `overlays/new-category` | ST03 |
| `overlays/new-category--error` | ST03 |
| `overlays/new-category--filled` | ST03 |
| `overlays/new-entry--error` | SH04, L15 |
| `overlays/new-entry--happened` | SH04, L15 |
| `overlays/new-entry--phone-sheet` | SH04 |
| `overlays/new-entry--planned` | SH04, L20 |
| `overlays/new-entry--repeats-fixed` | SH04, L25 |
| `overlays/new-entry--repeats-formula` | SH04, L25b |
| `overlays/override--budget-default` | PL05 |
| `overlays/override--budget-every` | PL05 |
| `overlays/override--budget-month` | PL05 |
| `overlays/override--occurrence` | L29 |
| `overlays/override--remove` | PL05 |
| `overlays/override--year-cell` | PL07 |
| `overlays/period-picker` | PL04 |
| `overlays/period-picker--year` | PL04 |
| `overlays/promote--planned` | L23 |
| `overlays/promote--recurring` | L30 |
| `overlays/reconcile` | AC08, AC09 |
| `overlays/reconcile--liability` | AC08 |
| `overlays/row-menu--account` | SH09, AC10 |
| `overlays/row-menu--budget` | SH09, PL05 |
| `overlays/row-menu--planned` | SH09, L22 |
| `overlays/row-menu--recurring` | SH09, L27, L28 |
| `overlays/row-menu--transaction` | SH09, L19 |
| `overlays/row-menu--upcoming` | SH09, TD05, L28 |
| `overlays/shortcuts` | SH06 |
| `plan/analytics` | PL01, PL10 |
| `plan/budget` | PL01, PL02, PL03, PL04, PL11 |
| `plan/forecast` | PL01, PL09 |
| `plan/year` | PL01, PL06, PL08 |
| `settings/categories` | PL12, ST01, ST02, ST06 |
| `settings/currency-fx` | ST07 |
| `settings/preferences` | SH12, ST08 |
| `settings/security` | AU15, ST09, ST11, ST12 |
| `settings/security--error` | ST13 |
| `settings/users` | ST14, ST16 |
| `today` | SH01, SH02, SH03, TD01, TD04, TD06, TD11, L24 |
| `today--afford-invalid` | TD08 |
| `today--afford-over` | TD07 |
| `today--empty` | TD02 |
| `today--flash` | SH07, SH08, TD09, L24 |
| `today--loading` | TD03 |

Reference pages that are not features: `index.html` (link index with theme switch), `components.html` (every component and state, see SH14), `charts/index.html` and `charts/forecast`, `charts/income-vs-expense`, `charts/spend-by-category`, `charts/sparkline`, `charts/year-grid` (static SVG examples, mapped through PL09, PL10, PL06, AC01).
