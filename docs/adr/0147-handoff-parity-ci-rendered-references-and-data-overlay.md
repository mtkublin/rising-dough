# ADR-0147: Handoff Parity Method: CI-Rendered References, Cluster Cap and a Data Overlay

- **Status**: Accepted (implementation pending, T-UR00b)
- **Date**: 2026-11-22
- **Amends**: [ADR-0106](0106-ui-behaviour-test-harness.md) amendment 2026-11-22 (§1 data parity, §2 same renderer, §3 strict tolerance); [ADR-0107](0107-sourdough-redesign-from-designer-handoff.md) §1 (source of truth)
- **Superseded in part by**: [ADR-0154](0154-accepted-ui-screenshots-replace-the-handoff-references.md) (proposed): on operator acceptance of the UI the handoff stops being the regression reference (§1 per-PR render, overlay, xfails); the render tool stays for manual designer comparisons.
- **Relates to**: [ADR-0027](0027-frontend-toolchain-hardening.md) (visual suite), [ADR-0134](0134-redesign-scope-decisions-from-the-designer-change-request.md), [ADR-0148](0148-redesign-backend-preconditions-released-first.md)

## Context

The ADR-0106 amendment of 2026-11-22 made the handoff screenshots the visual baselines for the redesign: the app is seeded with the handoff's data, references are rendered in the pinned Playwright container, and the diff tolerance is 0.1 % of pixels. Three gaps remained (operator review, 2026-11-22):

1. **Coverage.** Only the 1440 and 375 non-overlay references are committed (size budget, about 13 MB); overlays and 1024 are gitignored and the tests skip missing images, so CI never checks them.
2. **Ratio blind spot.** A page-wide ratio lets a localised defect through. On a 1440 x 3000 full-page shot 0.1 % is about 4,300 pixels and 0.05 % about 2,150; a mis-styled word (about 800 pixels) passes either way.
3. **Data the app cannot reproduce.** The handoff's numbers and labels are hand-typed. Some do not agree with each other (handoff README §6 item 17: *Delete account · confirm* names "Investments E", which is not in the handoff's account list), and some totals may not equal what the app's services compute from the same entries. One seed cannot reproduce such boards, so pixel parity would be impossible there.

## Decision

### 1. References are rendered in CI, not committed

- `visual.yml` renders the handoff references in the same job and the same pinned container as the app screenshots, then compares them. All pages, overlays and states are rendered at 1440 / 1024 / 375 in light and dark (546 images at delivery); nothing is skipped for a missing reference.
- `tests/visual/reference/` is removed from git and gitignored. A guard fails if a PNG is committed under it.
- This replaces the provenance manifest of the ADR-0106 amendment §2: references never leave the job that compares them, so their renderer is the pinned image by construction. Local runs (`just visual-reference`, `just test-visual --reference=handoff`) keep using the same container, never the host.

### 2. Tolerance: 0.1 % ratio plus a cluster cap

- The page-wide limit stays `MAX_DIFF_PIXEL_RATIO = 0.001` (0.1 %).
- Added: a **cluster cap**. The largest connected region of differing pixels (8-connected, after the per-pixel colour threshold) must not exceed `MAX_DIFF_CLUSTER_PX`. A comparison fails if either limit is exceeded.
- `MAX_DIFF_CLUSTER_PX` is calibrated at T-UR00b from the handoff-vs-itself noise floor (largest cluster across repeated runs under load, times two) and recorded in `tests/visual/README.md`. Changing it later needs an amendment to this ADR.
- On failure the test writes the diff image with the largest cluster outlined, so the defect is visible in the CI artifact.
- Tolerance exceptions for a surface still need a `derived.md` "Tolerance exceptions" row with the reason and operator sign-off; an exception may loosen the ratio, the cluster cap or both, and says which.

### 3. One coherent seed, and a data overlay on the handoff

- **Value inventory.** Every value the handoff displays (text, and the attributes in §4) is listed per page with the service or view-model field that produces it in the app ([ADR-0148](0148-redesign-backend-preconditions-released-first.md), T-UR34). Fields the app lacks are added before the migration.
- **Seed.** One base seed holds the handoff's entities (accounts, categories, transactions, planned and recurring items, budgets, users) at the frozen date 2026-10-31. State variants (`--empty`, `--no-matches`, `--long`, `--over-limit`, error states) are named modifiers of the base seed, not separate hand-made datasets. The frozen server in the visual suite renders the app from it.
- **Overlay.** Where a handoff value cannot be produced by the seed (internally inconsistent boards, totals that do not add up, entities missing from lists), the handoff side is corrected, never the app's logic. Corrections live in a reviewed replacements file, `tests/visual/handoff_overlay.toml`: one row per change with page (or glob), CSS selector, field (`text` or an attribute name), old value, new value and reason. The overlay is applied when the handoff is served for reference rendering and for `--target=mockup` journeys (T-UT09), so both read the same corrected content.
- **The vendored handoff stays byte-identical** to the designer's package (`docs/design/rising-dough-frontend/`, checksum manifest, ADR-0107 amendments). Later designer drops stay diffable; overlay rows whose `old` value no longer matches fail the guard and are reviewed.

### 4. What the overlay may change

- **Allowed:** text nodes; and attributes that carry the same displayed value: `aria-label`, `title`, `value`, `placeholder`, `datetime`, `aria-keyshortcuts`, `data-digits`, `data-marks`, `data-signs`.
- **Charts:** SVG geometry attributes (`d`, `points`, `x`, `y`, `width`, `height`, `cx`, `cy`, `r`) may change only in rows generated from the new values by the same geometry function the app uses (T-UR12), marked `source = "geometry"`. Hand-edited geometry is refused.
- **Never:** element names, element order or nesting, classes (except the reviewed token pair of the 2026-11-25 O1 amendment below), ids, any other attribute, inline `<style>` or `<script>`, and any CSS, JS, font, icon or image file. The overlay applies to HTML pages only.
- **Guard** (`tests/visual/test_handoff_overlay.py`): every row's `old` value matches the pristine page exactly once per targeted element (no stale or ambiguous rows); the overlaid DOM equals the pristine DOM after stripping text nodes and the allowed attributes; geometry rows carry `source = "geometry"`; no row targets a non-HTML file.

Amendment 2026-11-25 (T-UR00b, O1): class tokens and absent attributes. Two row kinds join the allowed set of section 4; the never-list otherwise stands (no element added or removed, no `style`, no tolerance, no mask).

- **Absent text attribute** (`absent = true`, `old = ""`). A row may SET `value` or `placeholder` on an element that has none (`ABSENT_SETTABLE` in `tests/visual/overlay.py`). Reason it exists: a handoff board whose summary names a search (`ledger/actual--no-matches`, "pizza") draws the search box without a `value` attribute, while the app correctly shows the active `q`. A row on any other attribute, or on one that already exists, is an error.
- **Class token pair** (`field = "class"`; `old` and `value` are the whole class string). A row may remove or add exactly one token, and only as a pair listed in `ALLOWED_CLASS_CHANGES` with its reason beside it. The one pair: `rd-fc__net--negative` -> none, for forecast net cells where the handoff prints a positive figure in the loss colour (Dec 2026 and Sep 2027 once the value rows apply) and the app paints a positive net plain. Any other pair, or more than one token, is refused at apply time and by the guard.
- **App-value rows** (`source = "app-values"`, text only). The Plan · analytics "vs 12-mo avg" cells cannot be reproduced by the fixed seed (the board's averages contradict its own flow chart). `overlay.delta_rows` builds one row per differing cell from the app's own spend rows run over the seed; the rows are committed under a marker at the end of `handoff_overlay.toml` and `test_handoff_overlay.py` fails when they differ from the regenerated ones (`uv run python -m tests.visual.test_handoff_overlay`). The arrow and the `--down` class stay the handoff's: an up/down mismatch or a row-count difference is an error, not an overlay row.
- **Guard.** `test_handoff_overlay.py` keeps the stale rule (a row matching nothing, or whose `old` differs from the page, fails), and its skeleton comparison now ignores only the tokens of `ALLOWED_CLASS_CHANGES`; a class edit outside them still fails. New cases cover a refused token pair, a stale class row, an absent row on a forbidden attribute and an absent row on an existing attribute.

Amendment 2026-11-25 (T-UR00b, N1): hidden promote-all. One more absent attribute joins the allowed set, with the never-list otherwise standing (no element added or removed, no `style`, no tolerance, no mask).

- **What.** A row (`absent = true`, `field = "hidden"`, `old = ""`, `value = "hidden"`) may set `hidden` on an element selected by `.rd-upcoming__promote-all` and by nothing else (`HIDDEN_SETTABLE_CLASSES` in `tests/visual/overlay.py`; any other selector is refused by `kind_violation`). The vendored CSS makes `[hidden]` win (`display: none !important`), so the element is not drawn, as the app does.
- **Reason it exists.** `pages/today--empty.html` draws the `promote all due` button (form `data-demo-flash="Promoted 2 due entries"`) beside "Nothing due in the next 30 days", contradicting `value-inventory.md` section 2 ("promote all due" visible when due rows exist). The app is right; the handoff is internally inconsistent.
- **Guard.** `test_handoff_overlay.py` skeleton comparison ignores `hidden` only on elements of those classes; new cases cover the allowed row, a refused selector, a stale `old` and a `hidden` attribute on any other element.

Amendment 2026-11-25 (T-UR12, UR12b): how geometry rows are produced.

- **Generator.** Rows come from `tests/visual/overlay.py` `geometry_rows`, which walks the app's chart fragment (`web/chart_geometry.py` `forecast_chart`, `flow_chart`, the same functions and templates the app serves, fed by the seed through the services) in step with the handoff's chart and emits one `source = "geometry"` row per coordinate, label or tooltip text that differs. "The same geometry function the app uses" therefore means the app's functions produce the new values; the generator only diffs.
- **Committed, not generated at load.** The rows are committed in `handoff_overlay.toml` (one reviewed block per chart, reason "generated by geometry_rows from the base seed") so a reviewer sees every changed coordinate and `test_handoff_overlay.py` guards them like any other row. A drift test (`tests/visual/test_overlay_geometry.py`) regenerates them from the built seed and the current app code and fails when the committed rows differ, so a seed or geometry change cannot leave stale coordinates. Regenerate with the helper named in that test's failure message.
- **Structural errors are fixed in the seed.** A child-count, tag or class mismatch between the handoff chart and the app chart (for example four flow months on the board against one month drawn) is an error in `geometry_rows`, never absorbed by the overlay: an overlay cannot add or remove elements (never-list above). The seed carries the data instead.
- **Seed history.** The base seed therefore holds Jul to Sep 2026 income and expense (one income and one expense entry per month on Checking, equal to the board's monthly figures) in addition to the October entries, so the analytics flow chart draws the board's four months. Ledger counts and per-account counts that the overlay pins follow from the seed and are recomputed by the value cases, never typed.
- **Planned seed item (UR12b review, 2026-11-25).** The base seed also carries a planned "Annual bonus" (25,000.00, 2026-11-20, Checking; `tests/visual/handoff_seed.py`). It lifts the forecast peak to 83,761.15 as on the board. It is seed data, not an overlay row, so it adds no entry to the overlay allow-list.
- **Overlay base surface (T-UR00b, H1, 2026-11-25).** A handoff overlay page is the full board of its own surface behind the dialog, not always Today. The reference run renders the dialog over that surface: the base page is derived from the overlay file (the `aria-current="page"` tab link that is not another overlay, else the main-nav link), and the app route and seed modifiers are those of that base page (`route_for`, `modifiers_for`, so a recurring-rule overlay gets the `recurring-board` modifier like `pages/ledger/recurring.html`). The three new-entry overlays load `/today` and fetch their dialog into `#modal-root` like every other opener; the blank `/add?dialog=1` shell is no longer used. No tolerance changes.
- **Cap height with one decimal (T-UR00b, Q1, 2026-11-26).** The handoff prints a loaf's arc start (`A17.0,17.0 ... x,y`) with one decimal where the app printed three (99.986 against 100.0); the 0.014 px difference rasterised the cap arcs differently (a 60 px cluster at 1024, over the 52 px cap). `web/chart_geometry.py` `_loaf_path` therefore rounds the apex to one decimal, as the handoff does; no overlay row and no tolerance change. The generated geometry rows were regenerated.
- **Page routing (T-UR00b, H2, 2026-11-25).** Non-overlay handoff pages get their own app route and state in `tests/visual/test_reference.py`: signed-out auth pages (login, invite and its expired/used/invalid states) render without the session cookie (a signed-in user is redirected from `/auth/login`); error states reached by a failing POST (login, reauth) are produced by filling and submitting the form in the browser (CSRF token included) over a fresh seeded DB; empty/long/no-match boards use the seed modifiers of `handoff_seed.py`; ledger actual uses the handoff period board `/ledger?date_from=2026-10-07&date_to=2026-10-31&page_size=11`; settings tabs and security/users use their real routes. Pages the harness cannot reach yet (first-run register, forced password rotation, 409, 500, offline, Today afford/flash/loading states) sit in an explicit `UNMAPPED_PAGES` dict with a reason each; it only shrinks, and they stay red like `UNMAPPED_OVERLAYS`.

Amendment 2026-11-26 (T-UR00b, operator option D1-a): `placeholder` is an allowed overlay attribute for text rows. Until now only an absent `placeholder` could be set (O1 amendment); a row may now rewrite an existing one (`ALLOWED_ATTRIBUTES` in `tests/visual/overlay.py`). One row uses it: the picker search input `search all 21 categories` becomes `search all 24 categories`, the same count the button above it already carries (value-inventory 5 row 12, ADR-0151: Reconciliation is system-only). The handoff is internally inconsistent here (panel says 21, button 24 on other boards); the number is what the app computes and the app is not changed. The never-list and the guard stand (`test_handoff_overlay.py` covers the row and a stale `old`).

### 5. Keyboard map: `g t` for Today

- Operator decision (2026-11-22, `derived.md` question 3): Today is `g t`, not the handoff's `g o`. The key lives in markup (`aria-keyshortcuts`) and visible key labels; the handoff's `shortcuts.js` reads the map from markup and is not changed. The handoff side is corrected by overlay rows (`aria-keyshortcuts` and the label text); the app's templates use `g t`. Requirement text: `docs/requirements.md` keyboard shortcuts line.
- Bulk select ships as delivered (hidden checkbox column, Tab / `x`; `derived.md` question 1).

## Consequences

- CI checks every handoff page, overlay and viewport in both themes; repo size drops by the committed reference set.
- Visual runs take longer (both sides rendered per run). `visual.yml` runs on template and CSS PRs only, as today.
- A localised defect fails even on long pages. The cluster cap needs one calibration pass and may raise tolerance-exception rows for anti-aliased chart edges; those rows carry operator sign-off.
- The handoff's data becomes consistent with what the app computes, at the cost of a maintained overlay. Every correction is a visible, reasoned row; the designer's files are never edited.
- Data the handoff shows but the app cannot compute surfaces early (value inventory), before any template is written.

## Amendment 2026-11-26 (operator decisions 2026-11-26)

Source: [operator-decisions-2026-11-26.md](../plans/ui-redesign/operator-decisions-2026-11-26.md).

- **Overlay op `insert_row` (D8-E).** Copies an existing element's markup within the same parent and changes text and allowed attributes only. Tags, classes, ids, CSS and JS of the copy are those of the source element. `test_handoff_overlay.py` accepts only that and rejects any other structural op. First use: the 11th account row of the `delete-account` backdrop.
- **Seed modifier "archive after seeding" (D1-c(i)).** Modifier `picker-handoff-list` archives the four extra categories after seeding, for the two category-picker pages (`category-picker`, `category-picker--no-match`), so the count rows read 20 as in the handoff.
- **Intended differences.** Pages that differ from the handoff by operator decision are listed in `derived.md` "Intended differences" (page, shards, decision id, sign-off) and marked `xfail(strict=True)` in `tests/visual/test_reference.py`. They are not tolerance exceptions: a new or vanished difference still fails the run.
- **Reference job stays advisory** (`continue-on-error`, not in `visual-gate`). Follow-up: once the operator accepts the UI, the accepted app screenshots become the reference (own ADR, supersedes the handoff-as-reference parts for regression), and only then is the job required.

## Alternatives considered

- **0.05 % ratio only** (operator's first proposal). Rejected: still about 2,150 pixels on a long page, so a whole wrong word passes; the cluster cap targets that case directly.
- **Commit all references** (about 68 MB) with the provenance manifest. Rejected: repo weight, and the manifest only approximates what rendering in the comparing job guarantees.
- **Edit the vendored handoff files.** Rejected: breaks the byte-identical vendoring and makes designer re-deliveries hard to diff.
- **Per-state hand-made seeds** to reproduce each board as typed. Rejected: inconsistent boards would need contradictory data, and totals that do not add up cannot be produced by correct services at all.
- **Tolerance exceptions for data mismatches.** Rejected: a loosened region hides layout defects inside it, the same reason masking was rejected.
- **Designer corrects every inconsistency.** Not chosen as the default: number and label fixes are mechanical and do not change design. Anything beyond the §4 allowed set still goes to the designer as a change request.
