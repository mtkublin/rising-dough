# ADR-0107: Sourdough Redesign Built Solely From the Designer Handoff

- **Status**: Accepted (implementation pending) (2026-11-21; OQ-23 confirmed 2026-11-24)
- **Date**: 2026-11-16
- **Supersedes**: [ADR-0052](0052-v2-tailwind-v4-tokens-and-font-hosting.md) (Tailwind v4 `@theme` tokens; font self-hosting continues under §4), [ADR-0053](0053-v2-component-system-and-jinja-macros.md) (component and macro inventory), [ADR-0055](0055-v2-responsive-layer-mobile-first.md) (breakpoints and mobile shell)
- **Supersedes (visual direction only)**: [ADR-0050](0050-v2-rising-dough-rename-and-visual-direction.md) palette, typography and elevation. The product name stays.
- **Amends**: [ADR-0027](0027-frontend-toolchain-hardening.md) §1 (Tailwind build removed), §2 (stylelint config), §3 (partials directory); [ADR-0054](0054-v2-charts-plotly-to-server-svg.md) (chart geometry follows the handoff's `charts/`); [ADR-0056](0056-v2-inline-interactions-and-backend-additions.md) (dialogs in `#modal-root`, row menus as popovers)
- **Keeps**: [ADR-0051](0051-v2-information-architecture-rising-dough.md) (Today · Ledger · Plan · Accounts · Settings), [ADR-0048](0048-category-color-coding.md) (per-category hue)
- **Relates to**: [ADR-0106](0106-ui-behaviour-test-harness.md) (precondition), [ADR-0099](0099-release-and-environment-policy.md) (release), [ADR-0079](0079-v4-threat-model-and-data-protection-goals.md) (v4 adds screens)

## Context

A designer delivered a complete static frontend, "Rising Dough · Sourdough redesign" (`data/rising-dough-frontend/`, untracked at the time of writing): 99 HTML files covering every page, overlay and state, one markup per screen with light and dark themes from tokens, plain CSS in `@layer`s, 16 single-behaviour JS files, self-hosted fonts and an SVG icon sprite. Its README documents fragment boundaries, runtime values the server must set, wiring, deviations from the spec and the checks run at delivery (W3C validator, stylelint, axe-core, Playwright at 320–1920 px, gzip budgets).

The current frontend is the v2 chrome (ADR-0050..0056) layered over Tailwind and a legacy `app.css`, plus a `rising-dough.css` override sheet. Adapting it to the new design screen by screen would carry its structure into the result.

The operator decided the redesign is built from the handoff, without reusing existing frontend files. This ADR draws the line of what "frontend files" means and fixes the toolchain, layout and rollout.

## Decision

### 1. Source of truth

- The handoff is committed under `docs/design/rising-dough-frontend/` (ADR-0106 §5; T-UT01) and is the only source for markup structure, CSS, fonts, icons and presentational JS.
- Where the app needs a screen or state the handoff does not draw, it is derived from the handoff's design system the same way the handoff derived its own extras (its README §6), and listed in `docs/plans/ui-redesign/derived.md`. A new board from the designer replaces a derived screen when it arrives.
- Deviations from the handoff are recorded per surface in the same file, with a reason.

### 2. What is replaced and what is kept

**Replaced (not reused, deleted at the end):** every template under `src/budget_planner/web/templates/` (the dev-only `dev/components.html` becomes a port of the handoff's `components.html`); `favicon.svg`; `app.css`, `rising-dough.css`, `tailwind*.css`, `tokens.css`, `fonts.css`, `auth.css`, `settings-*.css`; presentational JS (`rising-dough.js`, `kebab.js`, `bulk-select.js`, `combobox.js`, `palette.js`, `shortcuts.js`, `numeric-input.js`, `budget-override.js`).

**Kept and adapted to the new markup (behaviour, not design):**
- `htmx-csrf.js` (CSRF header on HTMX requests) and `passkeys.js` (WebAuthn ceremonies; v4 adds PRF on top).
- `users-admin.js` behaviour only if the handoff's `settings/users` page has no equivalent; otherwise replaced.
- Routers, services, view models and Jinja filters (`money`, dates). Router changes are limited to the template name, the context the new fragments need, and the response shape for dialogs and out-of-band swaps (§6).
- HTMX endpoint URLs and trigger names, unless the parity inventory (ADR-0106 §5) records a change.
- CSP and security headers. The handoff already avoids inline `style=""` (`style-src 'self' 'nonce-…'`).

The handoff's `stand-in.js` and every `data-demo*` / `data-js="demo-action"` attribute are never shipped.

### 3. Layout in the repo

- Static assets: `src/budget_planner/web/static/rd/` with the handoff's tree (`css/`, `js/`, `fonts/`, `icons/`, `img/`). The `rd/` prefix avoids collisions with old JS file names during the migration and stays afterwards.
- Templates: `layouts/base.html` (the handoff page shell: sprite, `#modal-root`, `#drawer-root`, `#toast-root`, `#flash-region`, palette and shortcuts dialogs), `pages/<surface>/<page>.html`, and `fragments/<name>.html` named exactly as the handoff's fragment boundary comments (`fragments/rows/transaction-row.html`, `fragments/overlays/edit-transaction.html`). The handoff's fragment name is the contract between the static files and the templates.
- Fragments are macros or includes with their inputs documented in a leading `{# #}` comment (ADR-0027 §3 convention, moved to the new directory).
- Old trees (`_partials/`, `partials/`, the per-feature directories, `base.html`) are deleted in the final task.

### 4. Toolchain

- **Tailwind is removed**: no `tailwind.src.css`, no build, no `tailwind-check` hook (amends ADR-0027 §1).
- **CSS bundle**: `just css` concatenates `rd/css/main.css`'s `@import` list in order into `rd/css/app.bundle.css` (a small Python script, no Node). The bundle is checked in and hash-busted; a pre-commit hook fails when it is stale. This avoids the `@import` request waterfall in production while keeping the handoff's source files untouched.
- **stylelint** uses the handoff's `.stylelintrc.json` (standard + BEM class pattern) for `static/rd/css/**` (amends ADR-0027 §2).
- **JS** loads as `type="module"` once served over HTTP (handoff README §6.1). No bundler.
- **Icons**: external sprite, `<use href="/static/rd/icons/sprite.svg#icon-…">` (handoff README §2 permits it over HTTP), instead of the inline copy per page.
- **Fonts**: the handoff's woff2 files (Unbounded 700, Geist Mono variable) replace the current fonts; OFL licences ship next to them.
- `djlint`, `ruff`, `mypy --strict`, axe in tests (with the handoff's two documented `aria-hidden` exclusions) are unchanged.

### 5. Server-side values

The handoff README §4 lists values the server sets as attributes or classes. These are implemented as small pure helpers with unit tests:
- category colour: `data-color="<preset>"`, or a nonce'd `<style>` rule for hues outside the presets (with the `--cat-edge` 3:1 contrast rule);
- block-character bars (20 cells, 10 in rows and on phone) with `--over` / `--none` modifiers;
- year-grid `data-state`, `aria-current="date"`, selection via ARIA attributes;
- hero figure fit (`data-digits`, `data-marks`, `data-signs`) as a Jinja filter;
- chart SVG geometry per `charts/`.

### 6. Interaction model

- Dialogs: `hx-get` into `#modal-root`; POST responses swap the changed row and add `flash/success` out of band. Delete/skip/restore respond with row removal plus `toast/undo`.
- Period navigation: `hx-get` + `hx-push-url` with `?period=YYYY-MM` / `?year=YYYY`.
- Row menus are native popovers (bottom sheet below 768 px).
- Submit buttons carry `hx-disabled-elt="this"`.
- Theme: `theme.js` in `<head>` (URL `?theme=` › `localStorage["rd-theme"]` › system), as delivered. Server-side theme cookie is out of scope.

### 7. Scope

- **Parity, not new features.** Screens the handoff draws but the app does not have (candidates found during planning: the offline page, first-run registration and invites, if not already supported) are not wired without a requirement in `docs/requirements.md`. Until then they are left out, and the parity inventory says so.
- Open design questions listed in the handoff README §6 (visible bulk-select entry point, inline promote variant) ship as delivered unless the operator decides otherwise in T-UR00.
- **v4 screens** (unlock, claim and recovery code, Data protection section, `/privacy`, export) are built after this redesign, from the new design system. They are not part of this effort.

### 8. Rollout

- One long-lived work branch `ui/sourdough`, surfaces migrated one at a time in orchestrator mode (ADR-0066). A migrated page extends `layouts/base.html`; an unmigrated page keeps the old `base.html`. Old and new CSS are never loaded on the same page.
- Each surface is done when its UI-map module (ADR-0106 §2) points at the new markup and the contract, journey, crawler and visual tests are green, and `frontend-visual-audit` is clean at 1440 / 1024 / 375 in both themes.
- **Old files are removed, not left behind.** A removal ledger generated at the branch point lists every old-frontend file, recipe, hook and CI step. Each surface deletes the old files only it used (and the Python only they used) when it migrates; a final sweep deletes the rest. An architecture test fails if a ledger row marked deleted reappears or a new file lands in an old-frontend path.
- Prod receives the redesign **once**, after every surface is migrated and the old frontend is deleted, through the ADR-0099 pipeline (`drill-gate` on the PR to `main`). No mixed chrome in prod.

### 9. Sequencing

- After v3 ships and after the quality-audit remediation tasks tagged `[pre-v4-P3]` land (they thin the routers this work touches).
- After the UI test harness (ADR-0106, `docs/plans/ui-test-harness/`) is complete.
- Before v4 Phase 2, which is the first v4 phase that adds UI. v4 Phase 1 (crypto core, no UI) may run in parallel.

## Consequences

- One coherent frontend with a documented contract (fragment names) between design and code. Future designer deliveries can be diffed against `docs/design/`.
- The toolchain gets simpler (no Tailwind build or `tailwind-check`; Node stays dev-only for stylelint, pixelmatch and Playwright), at the cost of a hand-maintained CSS architecture. The handoff's tokens and BEM conventions carry that.
- Large, mostly mechanical change across about 110 templates: parallelisable by surface, but the branch lives for a while and needs regular merges of `v3`/`main` into it.
- Routers change only at the edges (template names, context, OOB responses). Behaviour is pinned by the harness.
- Old visual baselines and old CSS disappear; ADR-0050..0055 become historical for design questions.

## Amendments

- 2026-11-21: `docs/design/rising-dough-frontend/` re-vendored byte-identical from the designer's updated package answering change request T-UT06 (171 files, 113 HTML; checksum manifest regenerated). No decision change.
- 2026-11-21 (T-UT06-EDITUSER): delta package for ST17 (Edit user) copied over the folder byte-identical: 2 files added (`pages/overlays/edit-user.html`, `CHANGES-edit-user.md`, kept as delivered), 13 changed (Users page, 8 Users overlays, `index.html`, `README.md`, `field.css`, `auth.css`); now 173 files, 114 HTML; checksum manifest regenerated. No decision change.

- 2026-11-22: [ADR-0147](0147-handoff-parity-ci-rendered-references-and-data-overlay.md) adds a data overlay (text and value attributes only) applied to the handoff for references; the vendored files stay byte-identical (§1). [ADR-0148](0148-redesign-backend-preconditions-released-first.md) moves the backend parts of the designer-answer scope into a release before the migration (§8, §9); the redesign release stays frontend only.
- 2026-11-25 (operator QA Q1, [operator decisions](../plans/ui-redesign/operator-decisions-2026-11-25.md)): §2 keeps two files by name. `src/budget_planner/web/static/csrf.js` (the shared token reader loaded before `htmx-csrf.js` and `passkeys.js`) and the vendored `src/budget_planner/web/static/vendor/htmx-2.0.11.min.js` (the HTMX runtime, a library and not design) are KEEP. Both have `keep` rows in `docs/plans/ui-redesign/removal.md`; T-UR15 does not delete them.
- 2026-11-25 (UR15d, operator QA Q1 relocation): the kept files are now `src/budget_planner/web/static/rd/js/csrf.js`, `static/rd/js/htmx-csrf.js`, `static/rd/js/passkeys.js` and `static/vendor/htmx-2.0.11.min.js`. The root copies `static/csrf.js`, `static/htmx-csrf.js` and `static/js/passkeys.js` were removed as superseded: they are identical to the `rd/js/` copies except for comments and the 422 `beforeSwap` handler, and no layout loads them. This supersedes the earlier sentence "T-UR15 does not delete them"; the operator's intent (the token reader and the vendored HTMX stay in the product) is met by the `rd/js/` copies and the unchanged vendored file.
- 2026-11-26 (T-UR00b, operator options D9-A and D11-S, [options](../plans/ui-redesign/operator-options-2026-11-26.md)): (D9-A) one `#flash-region`, see the ADR-0143 amendment 2026-11-26. (D11-S) the edit-category dialog selects and previews the dialog swatch nearest (RGB distance) to the stored hue (`settings_view.category_form_view`): Takeaway is stored as the board `orange` (`#ff9f43`), none of the ten dialog swatches, and the handoff dialog shows `tangerine`. Boards and lists keep the stored colour. An unchanged save never recolours: posting the preselected swatch back keeps the stored hue (`services.category_forms.parse_category_patch(stored_color=...)`, `derived.md`); only another swatch or the default radio changes it, and picking the preselected swatch deliberately counts as unchanged. Q19 palette names and hex are unchanged; the vendored CSS stays byte-identical.
- 2026-11-26 (T-UR00b, operator decisions D1-b, [decisions](../plans/ui-redesign/operator-decisions-2026-11-26.md)): app-owned CSS goes to `src/budget_planner/web/static/rd/app/overrides.css`, linked from `layouts/base.html` after `app.bundle.css`. The vendored `rd/css/**` returns to byte-identical with the handoff: the PAR-B additions to `dialog.css` move to `overrides.css`, and the D1-b rule (the hero amount keeps its focused underline while the category picker is open) lives there.- 2026-11-26 (T-UR56, F4.8a, operator review R5 "Inline + scope chips"): the year-grid inline cell editor no longer saves a one-off only. A scope chip row (an in-flow row under the edited row, so no cell value is covered; radios named `tier`: "this month only", "every <month>", "every month (default)", the dialog's labels via `plan_year_view.tier_labels`) starts on the cell's own tier (`plan_year_view.cell_scope`: one-off, recurring, else default). Enter posts amount and chosen scope to the same override route the dialog uses (`POST /budget/rules/{id}/overrides`, one save path, ADR-0031 §2); an unknown scope answers 422 as before. Escape cancels; focus returns to the cell after the grid reloads. A default-tier cell's no-script link opens the dialog on the same scope the editor preselects (`cell_scope`). The chip row is app CSS in `rd/app/overrides.css`; the vendored CSS is untouched.

## Alternatives considered

- **Restyle the existing templates toward the mockups.** Rejected by the operator: carries old structure and Tailwind utility markup into the new design.
- **Keep Tailwind and port the handoff's CSS into utilities.** Rejected: the handoff is token- and BEM-based plain CSS that already passes its checks; translating it creates drift from the source of truth.
- **Ship surface by surface to prod.** Rejected: mixed chrome for weeks, two CSS stacks in production, more release risk for a single-user app with no benefit.
