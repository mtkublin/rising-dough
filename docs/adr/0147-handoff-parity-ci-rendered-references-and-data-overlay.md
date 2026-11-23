# ADR-0147: Handoff Parity Method: CI-Rendered References, Cluster Cap and a Data Overlay

- **Status**: Accepted (implementation pending, T-UR00b)
- **Date**: 2026-11-22
- **Amends**: [ADR-0106](0106-ui-behaviour-test-harness.md) amendment 2026-11-22 (§1 data parity, §2 same renderer, §3 strict tolerance); [ADR-0107](0107-sourdough-redesign-from-designer-handoff.md) §1 (source of truth)
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

- **Allowed:** text nodes; and attributes that carry the same displayed value: `aria-label`, `title`, `value`, `datetime`, `aria-keyshortcuts`, `data-digits`, `data-marks`, `data-signs`.
- **Charts:** SVG geometry attributes (`d`, `points`, `x`, `y`, `width`, `height`, `cx`, `cy`, `r`) may change only in rows generated from the new values by the same geometry function the app uses (T-UR12), marked `source = "geometry"`. Hand-edited geometry is refused.
- **Never:** element names, element order or nesting, classes, ids, any other attribute, inline `<style>` or `<script>`, and any CSS, JS, font, icon or image file. The overlay applies to HTML pages only.
- **Guard** (`tests/visual/test_handoff_overlay.py`): every row's `old` value matches the pristine page exactly once per targeted element (no stale or ambiguous rows); the overlaid DOM equals the pristine DOM after stripping text nodes and the allowed attributes; geometry rows carry `source = "geometry"`; no row targets a non-HTML file.

### 5. Keyboard map: `g t` for Today

- Operator decision (2026-11-22, `derived.md` question 3): Today is `g t`, not the handoff's `g o`. The key lives in markup (`aria-keyshortcuts`) and visible key labels; the handoff's `shortcuts.js` reads the map from markup and is not changed. The handoff side is corrected by overlay rows (`aria-keyshortcuts` and the label text); the app's templates use `g t`. Requirement text: `docs/requirements.md` keyboard shortcuts line.
- Bulk select ships as delivered (hidden checkbox column, Tab / `x`; `derived.md` question 1).

## Consequences

- CI checks every handoff page, overlay and viewport in both themes; repo size drops by the committed reference set.
- Visual runs take longer (both sides rendered per run). `visual.yml` runs on template and CSS PRs only, as today.
- A localised defect fails even on long pages. The cluster cap needs one calibration pass and may raise tolerance-exception rows for anti-aliased chart edges; those rows carry operator sign-off.
- The handoff's data becomes consistent with what the app computes, at the cost of a maintained overlay. Every correction is a visible, reasoned row; the designer's files are never edited.
- Data the handoff shows but the app cannot compute surfaces early (value inventory), before any template is written.

## Alternatives considered

- **0.05 % ratio only** (operator's first proposal). Rejected: still about 2,150 pixels on a long page, so a whole wrong word passes; the cluster cap targets that case directly.
- **Commit all references** (about 68 MB) with the provenance manifest. Rejected: repo weight, and the manifest only approximates what rendering in the comparing job guarantees.
- **Edit the vendored handoff files.** Rejected: breaks the byte-identical vendoring and makes designer re-deliveries hard to diff.
- **Per-state hand-made seeds** to reproduce each board as typed. Rejected: inconsistent boards would need contradictory data, and totals that do not add up cannot be produced by correct services at all.
- **Tolerance exceptions for data mismatches.** Rejected: a loosened region hides layout defects inside it, the same reason masking was rejected.
- **Designer corrects every inconsistency.** Not chosen as the default: number and label fixes are mechanical and do not change design. Anything beyond the §4 allowed set still goes to the designer as a change request.
