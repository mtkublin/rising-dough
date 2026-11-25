# Frontend visual audit: T-UR27 theme switch

Task: T-UR27, branch wi/ui/sourdough/UR27. ADR-0134 section 8, ADR-0107, ADR-0113 (CSP), ADR-0123 (no CDN).
Method: Playwright (chromium) through the e2e `journey` fixture (prod CSP applied, logged-in scratch app DB); data/budget.sqlite not touched.

## Decision

Client-only. ADR-0134 section 8 says server-side persistence is a non-goal (per browser). `rd/js/theme.js` (classic external `<head>` script,
CSP-safe) and `rd/js/theme-switch.js` (module) came with the shell (T-UR01, T-UR02) and the Appearance card with T-UR13; T-UR27 verifies them on the
real Preferences route, adds ui_map entries (`theme_group`, `theme_option`, app and mockup) and the e2e `tests/e2e/test_theme_switch.py`
(default system, dark survives reload and applies on /today, system follows `prefers-color-scheme` via emulate_media). No CSS change.

## Probe

/settings?tab=prefs and /today, light and dark, at 1440, 1024 and 375 (12 states).

| State | horizontalScroll | duplicateIds | console errors | request failures | CSP violations |
|---|---|---|---|---|---|
| 1440, 1024, both themes | 0 | 0 | 0 | 0 | 0 |
| 375, both themes | 0 | 0 | 0 | 0 | 0 |

Overflowing elements at 375: 2 on preferences (settings tab strip, scrolls inside `.rd-tabs`, same as the T-UR13 record and the handoff), 1 on
/today (an inner scroller); the document has no horizontal scroll.

No flash: a MutationObserver installed before load read `<html data-theme>` when `<body>` first appeared; it was already `dark` or `light` as stored in
all 12 loads, so the attribute is set before first paint.

## Findings

None.
