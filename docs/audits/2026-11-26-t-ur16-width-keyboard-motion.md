# T-UR16 (UR16S): width sweep, keyboard map, reduced motion

Date 2026-11-26. Base `bea9ce19` (ui/sourdough), branch `wi/ui/sourdough/UR16S`. Run with the `frontend-visual-audit` diagnostics (Chromium, headless) against a scratch copy of `data/demo.sqlite` (migrated, one login user), never `data/budget.sqlite`. Not repeated here: crawler, journeys, Chromium/Firefox/WebKit e2e, axe, budgets, handoff visual diff (CI). The 375/1024/1440 sweep is in the UR41 audit.

Screenshots and JSON (scratch, not committed): `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/ur16s/` (`<width>__<route>.png`, `sweep.json`, `sweep320d.json`, `kb.json`, `rm.json`). Viewed: 320 today with the new-entry dialog open, 768 `/plan?tab=year`.

## 1. Width sweep 320 / 768 / 1920

Columns: horizontalScroll / overflowingElements (raw count; all classified below) / duplicateIds / consoleErrors / requestFailures.

| Route | 320 | 768 | 1920 |
|---|---|---|---|
| /today | false / 1 / 0 / 0 / 0 | false / 0 / 0 / 0 / 0 | false / 0 / 0 / 0 / 0 |
| /ledger | false / 1 / 0 / 0 / 0 | false / 30 / 0 / 0 / 0 | false / 0 / 0 / 0 / 0 |
| /plan | false / 1 / 0 / 0 / 0 | false / 30 / 0 / 0 / 0 | false / 0 / 0 / 0 / 0 |
| /plan?tab=year | false / 30 / 0 / 0 / 0 | false / 30 / 0 / 0 / 0 | false / 0 / 0 / 0 / 0 |
| /accounts | false / 0 / 0 / 0 / 0 | false / 30 / 0 / 0 / 0 | false / 0 / 0 / 0 / 0 |
| /settings?tab=categories | false / 2 / 0 / 0 / 0 | false / 0 / 0 / 0 / 0 | false / 0 / 0 / 0 / 0 |
| dialog open on /today (from topbar "new entry", 320: tabbar "+") | false / 2 / 0 / 0 / 0 | false / 0 / 0 / 0 / 0 | false / 0 / 0 / 0 / 0 |
| dialog open on /ledger | false / 2 / 0 / 0 / 0 | false / 30 / 0 / 0 / 0 | false / 0 / 0 / 0 / 0 |

Totals: horizontalScroll=0, duplicateIds=0, consoleErrors=0, requestFailures=0. `[style]` attributes also counted per page (see sweep.json `styleAttr`), not part of this task's acceptance.

overflowingElements classification (every entry has an ancestor with `overflow-x` not visible; none is a defect):
- Clipped by design, horizontally scrollable containers: `div.rd-table-scroll[auto]` (ledger, budget, year, accounts tables at 768 and year at 320; table is wider than the viewport by design, page itself does not scroll), `nav.rd-tabs[auto]` / `div.rd-tabs[auto]` (tab strip at 320), `div.rd-catfield__recent[auto]` (recent-category chip row in the dialog).
- Hidden: `pre.rd-hero__loaf` inside `section.rd-hero[hidden]` (320 /today), not rendered.
- Defects: 0.

## 2. Keyboard map, 1440, /today and /ledger (ADR-0147 section 5)

| Key | /today | /ledger |
|---|---|---|
| g t, g l, g p, g a, g s navigate | pass (all five) | pass (all five) |
| n opens new entry in place | pass (stays on page, dialog open) | pass |
| Esc closes dialog | pass | pass |
| / focuses search | n/a (no search on page) | **FAIL** |
| [ ] move period/tab | n/a (no tabs); no error | pass (/ledger -> /ledger?view=planned -> /ledger) |
| ? opens help (`#shortcuts`), Esc closes | pass | pass |
| Meta+K opens palette, Esc closes | pass | pass |

Finding K1 (minor): on /ledger `/` does nothing. `shortcuts.js` (line ~55) does `document.querySelector('main input[type="search"], main [role="search"] input')`; the first match in document order is the `<input type="hidden" name="view">` inside the `role="search"` filter bar (`fragments/ledger/filter-bar.html`), so `.focus()` goes to a hidden input and focus stays on `body`. The real search input is `input[name=q][type=search]`. Likely fix: select `input[type="search"]` first, or exclude `[type=hidden]` (`:not([type=hidden])`). Evidence: `kb_ledger_slash.png`, `kb.json`.

## 3. prefers-reduced-motion: reduce, 1440, /today with new-entry dialog

- Computed styles of every element (and `::before/::after`) on /today, with the dialog opening (100 ms and settled) and after an empty submit: elements with transition or animation duration plus delay above 0.011 s = 0 in all four snapshots; no `scroll-behavior: smooth`.
- Dialog: `transition-duration 0.001s`, `animation rd-pop-in 0.001s` (backdrop none). Flash region `rd-flash-region`: 0.001 s.
- Control run without the preference: dialog animation `rd-pop-in 0.32s`, buttons `0.12s` transitions (55 elements above threshold), so the reduce rule is what removes them.
- Limit: no visible toast item was produced (the flash region stayed empty on the empty-submit); only the region's computed duration was checked. A shown toast was not measured.

## Findings

| ID | Route / viewport | Severity | Evidence | Likely file |
|---|---|---|---|---|
| K1 | /ledger @ 1440 | minor | `/` does not focus search; hidden `view` input matched first | `src/budget_planner/web/static/rd/js/shortcuts.js` (~line 55) |
| V1 | new-entry dialog @ 320 | minor (cosmetic) | account select shows "Credit C" and date shows "26/11/202" truncated side by side (`320__DIALOG__today.png`) | dialog field row CSS (new-entry fragment) |

Step 3b was not in this item's scope (no template change); no template or CSS touched.
