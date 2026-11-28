# ADR-0055: v2 Rising Dough — Responsive Layer and Mobile Shell

- **Status**: Superseded by ADR-0107 (2026-11-25, T-UR15: the old responsive layer is deleted)
- **Date**: 2026-10-28
- **Related**: ADR-0023 (prior IA; "no mobile adaptive nav" in v1), ADR-0051 (new IA)
- **Supersedes**: ADR-0023 §Design direction "no mobile adaptive nav" — v2 ships a mobile layer.

## Context

v1 explicitly deferred mobile adaptive nav. The handoff restores it: mobile mockups cover Today, Ledger, Plan · Budget, Plan · Forecast, Accounts, and the Add sheet (screens 1o–1t). Mobile users were a non-goal in v1; v2 treats them as first-class because the "can I afford it?" question is most useful on a phone standing at a checkout.

## Decision

### 1. Three breakpoints

| Breakpoint | Range | Shell shape |
|---|---|---|
| **Desktop** | ≥ 1100 px | Left rail + content. Primitive layout: `grid-template-columns: 220px 1fr`. |
| **Tablet** | 641–1099 px | Sidebar collapses to a top bar (`<header>` with brand + inline nav links + top-bar `+ Add`); content takes full width. |
| **Mobile** | ≤ 640 px | Bottom tab bar with the four primary tabs + a centre `+ Add` sheet; Settings reached from the Today header. Content is single-column. |

### 2. Mobile tab bar

- `role="navigation" aria-label="Primary"`, position fixed at bottom, hairline top border.
- Five slots: Today · Ledger · [+ Add] · Plan · Accounts. The `+ Add` button is visually elevated (`--surface` fill, hairline border, 48 px tap target).
- Settings sits in the Today page header on mobile (small gear icon, top-right). The tab bar does not accommodate a sixth slot.
- Tap targets ≥ 44 px (handoff §Interactions / Accessibility).

### 3. Add sheet (mobile)

- `+ Add` opens a bottom sheet (`<dialog>` with `open=""` + CSS translate), not a modal.
- Three choice tiles: Transaction (default) · Planned · Recurring. Picking one swaps the sheet contents to the respective form; amount field is focused first.
- Submit uses the same server endpoints as desktop. Dismiss on 2xx (ADR-0030 modal dismissal scope) and on back-swipe (`popstate`).

### 4. Narrow numeric tables

Wide numeric tables (Plan · Budget rules, Plan · Year grid, Plan · Analytics, Plan · Forecast table) live in a scroll wrapper (`.ledger-scroll` or new `.table-scroll`) with a sticky first column:

```css
.table-scroll {
  overflow-x: auto;
  scroll-snap-type: x proximity;
}
.table-scroll th:first-child,
.table-scroll td:first-child {
  position: sticky;
  left: 0;
  background: var(--surface);
}
```

This fixes the overflow findings on `/budget`, `/analytics`, `/forecast/view` captured in the v1 audit.

### 5. Year grid becomes category cards on mobile

- At ≤ 640 px the Plan · Year heatmap grid replaces its 13-column layout with a per-category card stack. Each card shows the 12 cells as a horizontal strip; cell tap opens the same cell-edit popover.
- The handoff mocks (`mobile-1q-plan-budget.png` lower region) show the shape.

### 6. Breakpoint tokens

Reserved on `tokens.css`:

```css
:root{
  --bp-mobile: 640px;
  --bp-tablet: 1099px;
}
```

Media queries use the values directly (`@media (width < 640px)`) — not Tailwind utilities — so hand-authored partials and the Tailwind theme both reach the same breakpoints.

### 7. Keyboard behaviour unchanged

Keyboard shortcuts (`g o/l/p/a/s`, `n`, `/`, `[`, `]`, `?`, `⎋`) stay desktop-only. Mobile users use the tab bar and swipe gestures; the `?` cheatsheet modal is reachable from Settings on mobile.

## Consequences

### Positive

- "Can I afford it?" works at a checkout — the hero sits above the fold on a 390 px wide iPhone.
- Plan tabs are reachable from mobile without an awkward hamburger.
- Tables stop pushing the page off-viewport on narrow screens.

### Negative / costs

- Visual regression doubles — every screen renders at desktop + tablet + mobile viewports. Baselines regenerate once per v2 Phase 1 task.
- Bottom sheet / popstate interactions need a small amount of vanilla JS (`static/js/sheet.js`, ~40 lines).
- Settings-via-page-header on mobile means `g s` navigates on desktop but tap-reaches on mobile; no shortcut parity.

## Alternatives Considered

- Keep "no mobile adaptive nav" from ADR-0023 — rejected; the design brief ships mobile mocks and the primary question (can I afford it) is phone-first.
- Hamburger menu on mobile — rejected; four primary tabs + Add fit a bottom bar comfortably and hamburger menus hide primary navigation.
- Progressive Web App shell — out of scope; a mobile responsive layer achieves 90% of the win without the install prompt and offline cache work.
