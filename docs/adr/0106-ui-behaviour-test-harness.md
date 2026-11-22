# ADR-0106: UI Behaviour Test Harness Ahead of the Sourdough Redesign

- **Status**: Accepted (2026-11-21; exit-gate result in [T-UT12](../plans/ui-test-harness/tasks.md))
- **Date**: 2026-11-16
- **Amends**: [ADR-0027](0027-frontend-toolchain-hardening.md) §4 (visual regression baselines)
- **Relates to**: [ADR-0107](0107-sourdough-redesign-from-designer-handoff.md) (the redesign this harness protects), [ADR-0066](0066-orchestrator-mode-skill.md), [ADR-0097](0097-per-batch-ci-policy-and-fast-precommit-pytest.md)

## Context

ADR-0107 replaces the whole presentation layer (about 110 templates, all CSS and the presentational JS) with the designer's static handoff. The redesign must be done test-first: every screen's behaviour is pinned by tests that go red until the new template is wired, then green.

The current test suite cannot play that role as it stands:

- **Integration web tests are coupled to markup.** `tests/integration/web/` holds about 200 `in r.text` substring assertions and about 100 BeautifulSoup parses with CSS `.select(...)`. Many of them check behaviour (an amount is shown, a row is gone) through today's class names and copy. A redesign turns them red for the wrong reason, and fixing them one by one hides real regressions in the noise.
- **E2E journeys are few and use CSS selectors.** `tests/e2e/` has 8 journeys; selectors are `locator(...)` CSS (46) against `get_by_*` (4).
- **Visual baselines are of the old design.** `tests/visual/baselines/` (ADR-0027 §4) pins 5 routes × 3 viewports of the screens being replaced.
- **No inventory of what the UI does.** There is no list of every route, fragment endpoint, HTMX trigger and user-visible state, so "feature parity" with the new design cannot be checked.

Writing a click-by-click suite against today's UI was considered and rejected: it would encode the information architecture and markup that the redesign discards (the handoff moves actions into row menus, a command palette and dialogs in `#modal-root`), and almost every test would need rewriting during the migration.

## Decision

Build a harness that pins **behaviour** independently of markup, before the redesign starts. Five parts:

### 1. HTTP and HTMX contract tests (UI-independent)

- Every route in `app.routes` (pages, fragment endpoints, form POSTs, `hx-*` targets) has at least one contract test asserting status code, redirect target, `HX-*` response headers, CSRF enforcement, auth/authz, and the effect on the database and `audit_log`.
- Contract tests do **not** assert on markup beyond the presence of documented hook ids (part 2). Response bodies are checked through the UI map, never through raw class names or copy.
- A meta-test (`tests/contract/test_route_coverage.py`) enumerates `app.routes` and fails if a route has no contract test. Exclusions live in an explicit allowlist with a reason per entry.

### 2. UI map (one locator layer per surface)

- `tests/ui_map/` holds one module per surface (`shell`, `today`, `ledger`, `plan`, `accounts`, `settings`, `auth`, `errors`). Each exposes semantic names (`today.hero_figure`, `ledger.row(tx_id)`, `ledger.row_menu(tx_id)`) mapped to locators.
- Locators prefer, in order: ARIA role + accessible name, `<label>`, documented `id`s (`#modal-root`, `#flash-region`, record-derived row ids), then `data-testid` only where the first three are ambiguous. CSS class selectors are not allowed in the UI map.
- Both layers use it: Playwright (`page.get_by_role(...)`) and server-side HTML checks (a small adapter over BeautifulSoup that resolves the same role/label/id queries).
- Existing markup-coupled assertions in `tests/integration/web/` are rewritten to go through the UI map or are split: the behaviour part becomes a contract test (part 1), the markup part becomes a UI-map assertion.
- **This is the seam for the redesign.** Migrating a surface means changing that surface's UI-map module to the handoff's markup first (red), then the templates (green). No test body changes.

### 3. Generated crawler smoke test

- `tests/e2e/test_crawl.py` logs in on a seeded scratch DB, visits every page route, and for each page finds every link, button, `[hx-get]`, `[hx-post]`, menu item and dialog trigger. It activates each one (destructive actions only on a per-test fresh DB copy) and asserts: no 4xx/5xx, no console errors, no failed requests, no duplicate ids, no horizontal scroll at 375 and 1440, and that the control did something (navigated, opened, closed or swapped).
- The control inventory it discovers is written to `tests/e2e/crawl_inventory.json` and committed. A diff in that file is reviewed as a UI change.
- This replaces hand-writing one test per clickable element.

### 4. Journey tests

- The 8 existing journeys move onto the UI map. Missing critical journeys are added: new entry (happened / planned / repeats), edit and delete with undo, promote, reconcile, budget override, period navigation, category CRUD, FX, preferences, password and passkey, user admin, login / logout / re-auth.
- Journeys use only UI-map names. They run on Chromium in CI; Firefox and WebKit run in the opt-in `just test-e2e-browsers` recipe (the handoff relies on `:has()`, `color-mix()`, `popover` and `<dialog>`).

### 5. Feature-parity inventory and the mockup reference

- `docs/plans/ui-test-harness/parity.md` lists every user-visible feature, route and state of the current UI and maps each to a handoff page or overlay (`docs/design/rising-dough-frontend/pages/...`). Rows with no mapping are open decisions for the operator (keep in the old shape, design it, or drop it with an ADR). Rows that exist only in the handoff are listed too (they are new features and need their own requirement before they are wired).
- The designer's handoff is committed to the repo under `docs/design/rising-dough-frontend/` (it is currently an untracked folder under `data/`) so tests and agents can reference it at a fixed revision.
- The harness can run a journey against a handoff page served over HTTP with `stand-in.js` active (`--target=mockup`). That validates UI-map locators against the reference markup before any Jinja is written.

### Visual regression (amends ADR-0027 §4)

- During the redesign the reference images come from the handoff, not from the old app: each handoff page screenshotted at 1440 / 1024 / 375, light and dark, with the same fixed data the frozen server renders. Old baselines are deleted per surface as that surface migrates.
- ~~Tolerance and opt-in status (`CI_VISUAL=1`) are unchanged from ADR-0027.~~ Superseded by the amendment 2026-11-22 below: the suite runs in CI via `visual.yml` (ADR-0027 amendment 2026-11-22, T-Q251), not behind `CI_VISUAL=1`, and the redesign tolerance is strict.

### What the harness is not

- Not a redesign: no template, CSS or JS changes except adding `data-testid` or `id` hooks where the UI map needs them in the old UI, and only when role/label lookups are ambiguous.
- Not a coverage drive for services or domain logic. That is the quality audit's remediation (`docs/plans/quality-audit/`).

## Consequences

- The redesign gets a red/green signal per surface, and the only test edits it makes are in `tests/ui_map/` and the visual references.
- Integration web tests become slower to write (a UI-map entry instead of an `in r.text`), but stop breaking on copy and class changes.
- Accessibility improves as a side effect: role/label locators fail on unlabelled controls.
- The crawler needs fixtures that never touch `data/budget.sqlite`; it runs on a temp copy of a seeded scratch DB, like the rest of the suite.
- The mockup folder (about 3 MB, 99 HTML files, woff2 fonts) is added to git.

## Alternatives considered

- **Exhaustive click-by-click suite against today's UI.** Rejected: encodes the IA being replaced; most tests rewritten during migration.
- **Only visual regression against the mockups.** Rejected: catches layout, not wiring (a button that renders correctly and posts nowhere passes).
- **Write all tests only from the mockups, skip the current UI.** Rejected: loses the parity inventory, so features the designer did not draw would silently disappear.

## Amendment 2026-11-22: pixel parity against the handoff

Operator decision (2026-11-22; task T-UR00b). Redesign surfaces must match the designer handoff with no deviation, test-first: the handoff screenshots are the visual baselines, they fail red at first, and each surface task's goal is pixel parity.

1. **Data parity (option a).** The visual fixture (the frozen server data the app renders in the visual suite) is seeded with exactly the data the handoff pages hardcode: names, amounts, dates, counts and the frozen clock date. App renders and handoff references then show identical content, so the diff checks layout and styling, not data. Masking dynamic regions is rejected (it leaves the layout inside them unchecked). The handoff data lives in the hardcoded markup of `docs/design/rising-dough-frontend/pages/**` (and `components.html`, `charts/`); extracting it into a seed is part of T-UR00b. This replaces the earlier assumption that `data/demo.sqlite` at 2026-10-31 is "the matching fixture".
2. **Same renderer.** Handoff reference images are generated in the same pinned Playwright container as the app snapshots (`visual.yml`, `just visual-update` path), never on macOS. A provenance guard fails if references were produced elsewhere: a manifest recording the image tag and digest is written next to the references and checked against the image pinned by `tests/architecture/test_visual_image_pin.py`. Existing references in `tests/visual/reference/` are regenerated in the container.
3. **Strict tolerance.** The default per-surface tolerance is the strict suite default, `MAX_DIFF_PIXEL_RATIO = 0.001` (0.1 percent of pixels, `tests/visual/test_snapshots.py`). A looser tolerance for a surface needs a row in `docs/plans/ui-redesign/derived.md` ("Tolerance exceptions") with the reason, plus operator sign-off. The current per-surface values in `handoff.SURFACE_TOLERANCE` (1 to 4 percent) are removed by T-UR00b. The `CI_VISUAL=1` opt-in wording no longer applies: the suite runs in CI via `visual.yml` on template and CSS PRs.

Visual parity complements the behaviour harness (sections 1 to 4) and does not replace it: a surface is done only when both the contract, journey and crawler tests and the visual diff are green. The rejected alternative "Only visual regression against the mockups" stays rejected.
