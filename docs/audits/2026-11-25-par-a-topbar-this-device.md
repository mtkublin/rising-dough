# Frontend visual audit: PAR-A topbar email removal and THIS DEVICE badge (2026-11-25)

Change: PAR-A (Q17, Q23), branch wi/ui/sourdough/PARA at b84d8997. `layouts/base.html` no longer renders the signed-in email span in the topbar; `fragments/rows/session-row.html` badge text reads `THIS DEVICE`.
Run via the `frontend-visual-audit` skill (Playwright chromium) on a migrated scratch copy of `data/demo.sqlite` (never `data/budget.sqlite`). Screenshots in `/tmp/fe-audit-para/` (full page and topbar crop per route x viewport, plus `badge_cell.png`); I viewed the topbar crops at 1440, 1024 and 375 on /settings/security and the badge cell.

## Routes x viewports

Routes: /today, /ledger, /plan, /accounts, /settings, /settings/security, each at 1440, 1024 and 375 (18 rows).

| Diagnostic | Result (all 18 rows) |
|---|---|
| horizontalScroll | 0 (false everywhere) |
| duplicateIds | 0 |
| consoleErrors | 0 |
| requestFailures | 0 |
| overflowingElements | 0 at 1440 and 1024. At 375: `pre.rd-hero__loaf` on /today, `a.rd-tabs__tab` on /ledger, /settings, /settings/security (tab strip scrolls inside its container, page has no horizontal scroll). Identical on `ui/sourdough` (MAIN) for /today, /ledger, /settings: pre-existing, not caused by this change. |

## Topbar checks

- Signed-in email appears nowhere in the topbar on any route/viewport. On MAIN the email is still in the DOM (hidden below md); on PARA it is gone. The only place the email renders is the /settings/security hero note, which the handoff has too (`rd-hero__note--band`).
- 1440: items in order brand, today, ledger, plan, accounts | [ new entry ], ?, settings, sign out; sign out right edge 1360 = container edge, no gap where the span was. 1024: same order, right edge 1000 = container edge. 375: brand, settings, sign out (nav, new entry and ? hidden at that width as before), right edge 359, no gap. Matches handoff topbar (pages/today.html:47-52) order and alignment.
- Keyboard order: skip link, brand, today, ledger, plan, accounts, [ new entry ], ?, settings, sign out; at 375: skip link, brand, settings, sign out. Sane, no new stop.

## THIS DEVICE badge (/settings/security)

One badge per sessions list (1 row at 1440, 2 at 1024, 3 at 375 data-dependent session count), text `THIS DEVICE`. Computed: inline-block, 1px ink border, pill radius 999px, padding 2px 10px, 11px font, 0.44px letter-spacing, margin-top 6px, placed below device name and IP inside `td.rd-session__device`. Matches handoff (`.rd-this-device` in settings.css:232 and security.html markup: same position after the `rd-row__sub` span).

## Step 3b

- Swap targets: all `hx-target` selectors match one element; the only non-1 results are the relative selectors `this` and `closest tr` on security rows (valid HTMX, not document selectors).
- No arithmetic/`float`/`/ 100`/`* 100`/`set` in `layouts/base.html` or `session-row.html` (rg). The change removes markup only and adds no number.
- Rendered numbers: change renders no figures; no service value touched.
- Failing saves: no state-changing form added or modified (only the logout form, unchanged).
- HX-Trigger events: none added or removed.

## Findings

None. Result: CLEAN.
