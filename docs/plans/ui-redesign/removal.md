# Old-frontend removal ledger

Generated from `git ls-tree -r bd3c1b0a` (the `ui/sourdough` branch point, v3.2.0 live) for [T-UR00](tasks.md). Decision: [ADR-0107](../../adr/0107-sourdough-redesign-from-designer-handoff.md) §2 (what is replaced and what is kept) and §8 (old files are removed, not left behind).

## How it works

- Every file under `src/budget_planner/web/templates/` and `src/budget_planner/web/static/` (outside `static/rd/`) at the branch point has one row, plus the old visual baselines (`tests/visual/__snapshots__/`). The Tailwind/Node/CI pieces that exist only for the old frontend are listed in the non-file table.
- **Status vocabulary**: `delete` (still to remove), `deleted` (removed; the file no longer exists), `keep: <reason>` (only the kept-behaviour files of ADR-0107 §2 may be kept; the reason cites it).
- **Owner**: the surface task that deletes the row (T-UR05..T-UR14, per the owner map at the top of `tasks.md` and the Phase 2 surface list); a file shared by several surfaces or unclear belongs to T-UR15 (final sweep). A surface task that finds a file still referenced by an unmigrated surface moves its row to T-UR15.
- **Flipping a row**: the surface task deletes the file in the same commit that changes the row's status from `delete` to `deleted` (and deletes the matching `template_logic.toml` entries). Rows are never removed from the table.
- **Guard**: `tests/architecture/test_old_frontend_removed.py` reads the file tables (the ones headed `| Path |`). It fails when a `deleted` row still exists on disk, when a `delete` or `keep` row no longer exists, when a row path never existed at the branch point, and when a file appears under an old-frontend path that is not a row. New files are allowed only under the new roots of ADR-0107 §3, §4 (`templates/layouts/`, `templates/pages/`, `templates/fragments/`, `static/rd/`).
- File count at the branch point: 154 under `web/templates` + `web/static` (outside `rd/`) and 24 old snapshots. The brief named `tests/visual/baselines/`; that directory does not exist, the old baselines live in `tests/visual/__snapshots__/`. `tests/visual/reference/` holds the handoff-rendered references (ADR-0147) and is not old frontend.

## Files

| Path | Owner | Status | Note |
|---|---|---|---|
| `src/budget_planner/web/static/.gitkeep` | T-UR15 | delete | placeholder; the directory is populated by the redesign |
| `src/budget_planner/web/static/app.css` | T-UR15 | delete |  |
| `src/budget_planner/web/static/auth.css` | T-UR15 | delete | kept: rd-auth__* used by settings security/password until T-UR14 |
| `src/budget_planner/web/static/csrf.js` | T-UR15 | keep: ADR-0107 §2: shared token reader that `htmx-csrf.js` and `passkeys.js` load first; kept with them; copy in `rd/js/csrf.js` since T-UR04b, this old file stays until T-UR15 |  |
| `src/budget_planner/web/static/favicon.svg` | T-UR15 | delete |  |
| `src/budget_planner/web/static/fonts.css` | T-UR15 | delete |  |
| `src/budget_planner/web/static/fonts/LICENSE-OFL.txt` | T-UR15 | delete |  |
| `src/budget_planner/web/static/fonts/hanken-grotesk-normal-400-700-latin-ext.woff2` | T-UR15 | delete |  |
| `src/budget_planner/web/static/fonts/hanken-grotesk-normal-400-700-latin.woff2` | T-UR15 | delete |  |
| `src/budget_planner/web/static/fonts/ibm-plex-mono-normal-400-latin-ext.woff2` | T-UR15 | delete |  |
| `src/budget_planner/web/static/fonts/ibm-plex-mono-normal-400-latin.woff2` | T-UR15 | delete |  |
| `src/budget_planner/web/static/fonts/ibm-plex-mono-normal-500-latin-ext.woff2` | T-UR15 | delete |  |
| `src/budget_planner/web/static/fonts/ibm-plex-mono-normal-500-latin.woff2` | T-UR15 | delete |  |
| `src/budget_planner/web/static/fonts/ibm-plex-mono-normal-600-latin-ext.woff2` | T-UR15 | delete |  |
| `src/budget_planner/web/static/fonts/ibm-plex-mono-normal-600-latin.woff2` | T-UR15 | delete |  |
| `src/budget_planner/web/static/fonts/newsreader-italic-400-latin-ext.woff2` | T-UR15 | delete |  |
| `src/budget_planner/web/static/fonts/newsreader-italic-400-latin.woff2` | T-UR15 | delete |  |
| `src/budget_planner/web/static/fonts/newsreader-normal-400-600-latin-ext.woff2` | T-UR15 | delete |  |
| `src/budget_planner/web/static/fonts/newsreader-normal-400-600-latin.woff2` | T-UR15 | delete |  |
| `src/budget_planner/web/static/htmx-csrf.js` | T-UR15 | keep: ADR-0107 §2: CSRF header on HTMX requests, adapted to the new markup (copy in `rd/js/` since T-UR04b; this old file stays until T-UR15) |  |
| `src/budget_planner/web/static/js/account-form.js` | T-UR08 | delete |  |
| `src/budget_planner/web/static/js/app-init.js` | T-UR15 | delete |  |
| `src/budget_planner/web/static/js/budget-override.js` | T-UR11 | delete |  |
| `src/budget_planner/web/static/js/category-form.js` | T-UR13 | delete |  |
| `src/budget_planner/web/static/js/combobox.js` | T-UR15 | delete |  |
| `src/budget_planner/web/static/js/kebab.js` | T-UR15 | delete |  |
| `src/budget_planner/web/static/js/numeric-input.js` | T-UR15 | delete |  |
| `src/budget_planner/web/static/js/overlay-actions.js` | T-UR15 | delete |  |
| `src/budget_planner/web/static/js/palette.js` | T-UR15 | delete |  |
| `src/budget_planner/web/static/js/passkeys.js` | T-UR15 | keep: ADR-0107 §2: WebAuthn ceremonies, adapted to the new markup (copy in `rd/js/` since T-UR04b; this old file stays until T-UR15) |  |
| `src/budget_planner/web/static/js/rd-wire.js` | T-UR15 | delete |  |
| `src/budget_planner/web/static/js/reconcile-form.js` | T-UR08 | delete |  |
| `src/budget_planner/web/static/js/recurring-form.js` | T-UR10 | delete |  |
| `src/budget_planner/web/static/js/rising-dough.js` | T-UR15 | delete |  |
| `src/budget_planner/web/static/js/shortcuts.js` | T-UR15 | delete |  |
| `src/budget_planner/web/static/js/txn-form.js` | T-UR15 | delete |  |
| `src/budget_planner/web/static/js/users-admin.js` | T-UR14 | delete | ADR-0107 §2: behaviour kept only if the handoff `settings/users` page has no equivalent; T-UR14 decides, then sets `deleted` or `keep: <reason>` |
| `src/budget_planner/web/static/rising-dough.css` | T-UR15 | delete |  |
| `src/budget_planner/web/static/settings-security.css` | T-UR14 | delete |  |
| `src/budget_planner/web/static/settings-users.css` | T-UR14 | delete |  |
| `src/budget_planner/web/static/tailwind.css` | T-UR15 | delete |  |
| `src/budget_planner/web/static/tailwind.src.css` | T-UR15 | delete |  |
| `src/budget_planner/web/static/tokens.css` | T-UR15 | delete |  |
| `src/budget_planner/web/static/vendor/htmx-2.0.11.min.js` | T-UR15 | keep: ADR-0107 §2 keeps the HTMX endpoints and triggers; the HTMX runtime is a vendored library, not design |  |
| `src/budget_planner/web/templates/.gitkeep` | T-UR15 | delete | placeholder; the directory is populated by the redesign |
| `src/budget_planner/web/templates/_partials/combobox.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/_partials/components/_amount.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/_partials/components/_button.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/_partials/components/_direction_badge.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/_partials/components/_filter_chips.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/_partials/components/_heatmap_cell.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/_partials/components/_pace_tag.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/_partials/components/_period_header.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/_partials/components/_pill.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/_partials/components/_planned_net.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/_partials/components/_progress_bar.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/_partials/components/_segmented.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/_partials/components/_sparkline.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/_partials/components/_table_row.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/_partials/components/_toast.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/_partials/components/_top_bar_add.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/_partials/kebab_menu.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/_partials/overdue_row.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/_partials/segmented.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/_partials/slide_over_header.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/accounts/index.html` | T-UR08 | delete |  |
| `src/budget_planner/web/templates/auth/_layout.html` | T-UR05 | deleted |  |
| `src/budget_planner/web/templates/auth/login.html` | T-UR05 | deleted |  |
| `src/budget_planner/web/templates/auth/reauth.html` | T-UR05 | deleted |  |
| `src/budget_planner/web/templates/base.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/budget/_yearly.html` | T-UR11 | delete |  |
| `src/budget_planner/web/templates/budget/index.html` | T-UR11 | delete |  |
| `src/budget_planner/web/templates/budget/manage.html` | T-UR11 | delete |  |
| `src/budget_planner/web/templates/categories/index.html` | T-UR13 | delete |  |
| `src/budget_planner/web/templates/dev/components.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/errors/404.html` | T-UR06 | deleted |  |
| `src/budget_planner/web/templates/errors/409.html` | T-UR06 | deleted |  |
| `src/budget_planner/web/templates/errors/422.html` | T-UR06 | deleted |  |
| `src/budget_planner/web/templates/errors/500.html` | T-UR06 | deleted |  |
| `src/budget_planner/web/templates/errors/_shell.html` | T-UR06 | deleted |  |
| `src/budget_planner/web/templates/forecast/index.html` | T-UR12 | delete |  |
| `src/budget_planner/web/templates/ledger/_recently_deleted.html` | T-UR10 | delete |  |
| `src/budget_planner/web/templates/ledger/_table.html` | T-UR09 | delete |  |
| `src/budget_planner/web/templates/ledger/index.html` | T-UR09 | delete |  |
| `src/budget_planner/web/templates/partials/_add_entry_overlay.html` | T-UR07 | delete |  |
| `src/budget_planner/web/templates/partials/_cheatsheet.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/partials/_direction_badge.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/partials/_flash.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/partials/_form_errors.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/partials/_money.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/partials/_nav.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/partials/_pagination.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/partials/_palette.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/partials/_shortcuts.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/partials/_slideover.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/partials/_slideover_page.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/partials/_tabbar.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/partials/accounts/_card.html` | T-UR08 | delete |  |
| `src/budget_planner/web/templates/partials/accounts/_form.html` | T-UR08 | delete |  |
| `src/budget_planner/web/templates/partials/accounts/_fortune_split.html` | T-UR08 | delete |  |
| `src/budget_planner/web/templates/partials/accounts/_reconcile_modal.html` | T-UR08 | delete |  |
| `src/budget_planner/web/templates/partials/accounts/_row.html` | T-UR08 | delete |  |
| `src/budget_planner/web/templates/partials/accounts/_snapshot_item.html` | T-UR08 | delete |  |
| `src/budget_planner/web/templates/partials/accounts/_totals.html` | T-UR08 | delete |  |
| `src/budget_planner/web/templates/partials/budget/_override_form.html` | T-UR11 | delete |  |
| `src/budget_planner/web/templates/partials/categories/_form.html` | T-UR13 | delete |  |
| `src/budget_planner/web/templates/partials/categories/_row.html` | T-UR13 | delete |  |
| `src/budget_planner/web/templates/partials/forecast/_chart.html` | T-UR12 | delete |  |
| `src/budget_planner/web/templates/partials/forecast/_table.html` | T-UR12 | delete |  |
| `src/budget_planner/web/templates/partials/forecast/_view.html` | T-UR12 | delete |  |
| `src/budget_planner/web/templates/partials/planned/_form.html` | T-UR10 | delete |  |
| `src/budget_planner/web/templates/partials/planned/_promote_inline_row.html` | T-UR10 | delete |  |
| `src/budget_planner/web/templates/partials/planned/_promote_modal.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/partials/planned/_row.html` | T-UR10 | delete |  |
| `src/budget_planner/web/templates/partials/planned/_table.html` | T-UR10 | delete |  |
| `src/budget_planner/web/templates/partials/recurring/_form.html` | T-UR10 | delete |  |
| `src/budget_planner/web/templates/partials/recurring/_formula_preview.html` | T-UR10 | delete |  |
| `src/budget_planner/web/templates/partials/recurring/_override_form.html` | T-UR10 | delete |  |
| `src/budget_planner/web/templates/partials/recurring/_promote_inline_row.html` | T-UR10 | delete |  |
| `src/budget_planner/web/templates/partials/recurring/_promote_modal.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/partials/recurring/_row.html` | T-UR10 | delete |  |
| `src/budget_planner/web/templates/partials/transactions/_empty.html` | T-UR09 | delete |  |
| `src/budget_planner/web/templates/partials/transactions/_filter_form.html` | T-UR09 | delete |  |
| `src/budget_planner/web/templates/partials/transactions/_form.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/partials/transactions/_limit_preview.html` | T-UR09 | delete |  |
| `src/budget_planner/web/templates/partials/transactions/_row.html` | T-UR09 | delete |  |
| `src/budget_planner/web/templates/partials/transactions/_table.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/plan/_analytics_bundle.html` | T-UR12 | delete |  |
| `src/budget_planner/web/templates/plan/_analytics_tab.html` | T-UR12 | delete |  |
| `src/budget_planner/web/templates/plan/_budget_tab.html` | T-UR11 | delete |  |
| `src/budget_planner/web/templates/plan/_forecast_tab.html` | T-UR12 | delete |  |
| `src/budget_planner/web/templates/plan/_year_tab.html` | T-UR11 | delete |  |
| `src/budget_planner/web/templates/plan/index.html` | T-UR15 | delete |  |
| `src/budget_planner/web/templates/planned/index.html` | T-UR10 | delete |  |
| `src/budget_planner/web/templates/recurring/index.html` | T-UR10 | delete |  |
| `src/budget_planner/web/templates/settings/_categories.html` | T-UR13 | delete |  |
| `src/budget_planner/web/templates/settings/_drawer.html` | T-UR13 | delete |  |
| `src/budget_planner/web/templates/settings/_fx.html` | T-UR13 | delete |  |
| `src/budget_planner/web/templates/settings/_password_form.html` | T-UR14 | delete |  |
| `src/budget_planner/web/templates/settings/_prefs.html` | T-UR13 | delete |  |
| `src/budget_planner/web/templates/settings/_tabs.html` | T-UR13 | delete |  |
| `src/budget_planner/web/templates/settings/index.html` | T-UR13 | delete |  |
| `src/budget_planner/web/templates/settings/password.html` | T-UR14 | delete |  |
| `src/budget_planner/web/templates/settings/security.html` | T-UR14 | delete |  |
| `src/budget_planner/web/templates/settings/users/_add-errors.html` | T-UR14 | delete |  |
| `src/budget_planner/web/templates/settings/users/_password-toast.html` | T-UR14 | delete |  |
| `src/budget_planner/web/templates/settings/users/_row.html` | T-UR14 | delete |  |
| `src/budget_planner/web/templates/settings/users/_table.html` | T-UR14 | delete |  |
| `src/budget_planner/web/templates/settings/users/edit.html` | T-UR14 | delete |  |
| `src/budget_planner/web/templates/settings/users/list.html` | T-UR14 | delete |  |
| `src/budget_planner/web/templates/today/_afford_preview.html` | T-UR07 | delete |  |
| `src/budget_planner/web/templates/today/_upcoming.html` | T-UR07 | delete |  |
| `src/budget_planner/web/templates/today/index.html` | T-UR07 | delete |  |
| `src/budget_planner/web/templates/transactions/index.html` | T-UR09 | delete |  |

## Old visual baselines

| Path | Owner | Status | Note |
|---|---|---|---|
| `tests/visual/__snapshots__/accounts.1024.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/accounts.1440.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/accounts.375.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/budget.1024.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/budget.1440.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/budget.375.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/forecast.1024.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/forecast.1440.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/forecast.375.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/ledger.1024.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/ledger.1440.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/ledger.375.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/login.1024.png` | T-UR15 | deleted | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/login.1440.png` | T-UR15 | deleted | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/login.375.png` | T-UR15 | deleted | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/recurring.1024.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/recurring.1440.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/recurring.375.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/settings.1024.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/settings.1440.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/settings.375.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/today.1024.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/today.1440.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |
| `tests/visual/__snapshots__/today.375.png` | T-UR15 | delete | old snapshot; the surface task deletes its page's `<page>.<width>.png` |

## Toolchain and CI (non-file rows)

All owned by T-UR15 (ADR-0107 §4: Tailwind removed, no Node for CSS, `just css` becomes the bundle script from T-UR01). Checked against the tree at the branch point. These rows are not read by the guard.

| Item | Where | Owner | Status |
|---|---|---|---|
| Tailwind config | `tailwind.config.js` | T-UR15 | delete |
| Tailwind npm dependency (`tailwindcss`) and the `css`, `css:watch` npm scripts | `package.json`, `package-lock.json` | T-UR15 | delete |
| Old stylelint config (the `stylelint` block of `package.json` and the `stylelint` npm script over `static/*.css`) | `package.json` | T-UR15 | delete |
| `just css` (Tailwind build) and `just css-watch` recipes | `justfile` | T-UR15 | delete |
| `npm run stylelint` line in the `just lint` recipe (old config) | `justfile` | T-UR15 | delete |
| `tailwind-check` pre-commit hook and its script | `.pre-commit-config.yaml`, `scripts/pre-commit/tailwind_check.sh` | T-UR15 | delete |
| `stylelint (hand-authored CSS)` pre-commit hook over `static/[^/]+\.css` | `.pre-commit-config.yaml` | T-UR15 | delete |
| `tailwind.css` exclusions in the whitespace and EOF hooks | `.pre-commit-config.yaml` | T-UR15 | delete |
| CI steps "Set up Node (Tailwind + stylelint)", "Install Node dev toolchain", "Build Tailwind CSS" | `.github/workflows/ci.yml` | T-UR15 | delete |
| Dockerfile | `Dockerfile` | T-UR15 | nothing to remove: no Node or Tailwind step at the branch point (the built CSS is committed); re-check at T-UR15 |
