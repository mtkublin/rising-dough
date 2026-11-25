# Frontend audit: T-UR15c (old shell removal)

Change: T-UR15 slice c, branch `wi/ui/sourdough/UR15c`, head 504eb3a7. Old `base.html`, `_partials/**`, `partials/**` and 11 old static JS files deleted; `pages/dev/components.html` ported; `errors.py` renders fragments; `GET /add` always the dialog; `tailwind.css` regenerated.
Tool: `frontend-visual-audit` skill (Playwright, chromium), own server on 127.0.0.1:8765 over a migrated scratch copy of `data/demo.sqlite` (never `data/budget.sqlite`). Screenshots in the scratchpad `au/` directory (not committed); the full-page PNGs were viewed for /today 1440, /ledger 375, /settings 375, /dev/components 1440, the 375 new-entry 422 dialog and /dev/shell with flashes.

## Routes x viewports (1440 / 1024 / 375 each)
/today, /ledger, /ledger?view=planned, /ledger?view=recurring, /ledger/recently-deleted, /plan, /plan?tab=year|forecast|analytics, /accounts, /settings, /settings?tab=categories|fx|prefs, /settings/users, /settings/security, /settings/password and /auth/sessions (both redirect to /settings/security#...), /dev/components, /dev/shell, /nonexistent-page (404), /auth/login, /auth/register and /setup (both redirect to login on a configured DB), /invite/badtoken.

## Diagnostics (all 25 routes x 3 viewports)
| Signal | Result |
|---|---|
| horizontalScroll | 0 on every row |
| overflowingElements | 0 at 1440. At 1024 and 375 non-zero only inside intended scroll containers or clipped decoration (planned/recurring and year tables at 1024, the year/forecast table and SVG at 375, `.rd-tabs__tab` strip, the ASCII loaf `pre`, chip row on /dev/components); document never scrolls horizontally. Triaged, not blocking. |
| duplicateIds | 0 |
| consoleErrors | 0 except the intentional 404 page (browser logs the 404 document) |
| requestFailures | 0 |
| Requests for removed static JS files | 0 (checked each response against the 11 deleted file names) |
| Broken images / missing styles / fonts | 0 broken images; Geist fonts and icon sprite load; screenshots show no unstyled elements |
| hx-target selectors matching != 1 | 0 |

## Interactions (1440 / 1024 / 375 where applicable)
- Command palette (Ctrl+K) and shortcuts overlay (?) on /today /ledger /plan /accounts at 1440 and 1024: open, no overflow, no console errors (keyboard shortcuts not applicable at 375).
- New-entry dialog from /today /ledger /plan /accounts at all three widths: opens; empty submit gives 422, the dialog stays open with a visible summary ("2 fields need attention") and field errors. 0 duplicate ids after the swap.
- Forced POST /transactions 404, 409, 500 (route interception): dialog stays open and a visible flash ("not found", "changed in the meantime", "Something went wrong") appears. Not left looking saved.
- /dev/shell fail buttons 409, 500, 404: visible flash each (409 conflict text, 500 with reference id, 404 "That item was not found").
- Error pages: 404 (browser Accept) renders the shell with "ERROR 404"; /ledger?view=bogus and /plan?tab=bogus render the 422 page; 500 flash via /dev/shell/fail/500.
- Nav rail (top) at 1440/1024 and bottom tab bar with the centre add button at 375 render correctly.

## Step 3b
1. Swap targets: all non-relative `hx-target` selectors match exactly one element on every route, and after the dialog swap.
2. Failing saves visible: yes (see above).
3. No arithmetic in templates: `rg` over the touched templates found none (the guard tests cover it); only the `pages/dev/components.html` fixture values are literals by design.
4. Money by currency: amounts rendered through the filters (EUR account rows show converted PLN). JPY not present in the demo data, not checked.
5. Rendered numbers: /today hero and net worth read from the page (-17.66 PLN/day, 34,439.69 PLN) come from the view model; no template derivation. Not re-derived against the service call.
6. Listeners: no console errors from missing listeners in the interactions above.
7. Scratch data only: yes.

## Findings
1. Minor (not blocking): `GET /accounts/9999/edit` for a missing account answers a bare `account not found` text body instead of the error page fragment (accounts router path, check whether pre-existing).
2. Minor: a forced error flash is announced twice (two `role=alert` elements with the same text) after the dialog 404/409/500 save errors.
3. Not checked: JPY zero-decimal rendering, 500 page full-document render without a handler patch (verified only through the flash on /dev/shell/fail/500), /setup and invite pages with a valid token.
