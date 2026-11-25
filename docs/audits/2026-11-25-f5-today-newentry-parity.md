# Frontend visual audit: F5 Today / new-entry / shell parity (2026-11-25)

Item: F5 (branch wi/ui/sourdough/F5, sha 3e7cb1b, MAIN ui/sourdough). Skill: frontend-visual-audit
(Playwright, chromium headless shell). Scratch DB seeded by tests/visual/handoff_seed.py (not
data/budget.sqlite), server via tests/visual/frozen_server.py, frozen date 2026-10-31.

## Routes
/today, /today?amount=abc, /today?amount=1800, Today range buttons (7 / 30 / all, plus forced
failures), /add?when=happened (open and 422 states), /dev/shell (forced 404/409/500 + retry),
palette (Ctrl+K) and shortcuts (?) on /today. Each at 1440, 1024 and 375.

## Diagnostics
| route | viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| today | 1440 | false | 0 | 0 | 0 | 0 |
| today_amount_abc | 1440 | false | 0 | 0 | 0 | 0 |
| today_amount_1800 | 1440 | false | 0 | 0 | 0 | 0 |
| today_ranges | 1440 | false | 0 | 0 | 4 | 1 |
| add_happened | 1440 | false | 0 | 0 | 0 | 0 |
| add_422 | 1440 | false | 0 | 0 | 1 | 0 |
| dev_shell_fail | 1440 | false | 0 | 0 | 4 | 0 |
| palette_shortcuts | 1440 | false | 0 | 0 | 0 | 0 |
| today | 1024 | false | 0 | 0 | 0 | 0 |
| today_amount_abc | 1024 | false | 0 | 0 | 0 | 0 |
| today_amount_1800 | 1024 | false | 0 | 0 | 0 | 0 |
| today_ranges | 1024 | false | 0 | 0 | 4 | 1 |
| add_happened | 1024 | false | 0 | 0 | 0 | 0 |
| add_422 | 1024 | false | 0 | 0 | 1 | 0 |
| dev_shell_fail | 1024 | false | 0 | 0 | 4 | 0 |
| palette_shortcuts | 1024 | false | 0 | 0 | 0 | 0 |
| today | 375 | false | 1 | 0 | 0 | 0 |
| today_amount_abc | 375 | false | 1 | 0 | 0 | 0 |
| today_amount_1800 | 375 | false | 1 | 0 | 0 | 0 |
| today_ranges | 375 | false | 1 | 0 | 4 | 1 |
| add_happened | 375 | false | 2 | 0 | 0 | 0 |
| add_422 | 375 | false | 2 | 0 | 1 | 0 |
| dev_shell_fail | 375 | false | 0 | 0 | 4 | 0 |
| palette_shortcuts | 375 | false | 1 | 0 | 0 | 0 |

Reading the counts:
- consoleErrors on today_ranges (4), add_422 (1), dev_shell_fail (4) are the browser's own
  "Failed to load resource ... 4xx/5xx" lines and htmx sendError lines caused by the forced
  failures (422 blank save, forced 404/409/500, aborted range request). Clean pages
  (today, amount variants, add_happened, palette_shortcuts) have 0.
- requestFailures=1 on today_ranges is the deliberately aborted range request.
- overflowingElements at 375 (identical on MAIN, checked on a second server on the same DB):
  today/palette: pre.rd-hero__loaf (decorative ASCII loaf, right=399, clipped by the hero's
  overflow hidden; horizontalScroll stays false); add: label.rd-chip-option (right=455, the
  horizontally scrolling recent-category chip strip) and an absolutely positioned input
  (right=396). No horizontal scroll at any width. Pre-existing, not introduced by F5.
- duplicateIds 0 everywhere, including after range swaps.

## Step 3b
1. Swap targets: #upcoming-list, #afford-result, #today-bar each match exactly 1 element on load
   and after range swaps.
2. Failing saves: 404 -> flash "That item was not found...", 409 -> flash "Dev conflict: that row
   is protected", 500 -> flash "Couldn't save. Your changes are still in the form." with a retry
   button; clicking retry re-issued exactly 1 request and the flash stayed. /add blank save: field
   error "Pick a category" visible (blank amount shows the browser's native "Please fill out this
   field" bubble, no request sent). OK.
3. Templates: no arithmetic/float in the Today templates; bar glyph runs come from the view model.
4. Rendered numbers equal service values on the scratch DB (month_summary / budget_view /
   compute_fortune): spent 5,014.55 (501455), committed 446.60, left 987.93, budget 6,449.08,
   per day 141.13 (14113), net worth 34,439.69, assets 36,895.43, liabilities 2,455.74. Hero bar:
   501455/644908 = 77.76 % of 20 cells -> 16 filled + 1 committed + 3 empty = 20; aria-label
   "77 percent spent, 15 percent left". OK.
5. FINDING (blocking): the range-button skeleton is left stuck on a failed request (below).
6. HX-Trigger listeners not re-audited beyond today-stale/ledger-stale used on the page.

## Findings
1. Behavior, blocking. Today range buttons, HTTP error response (forced 500; and a real handler
   response, /today/upcoming?window=zzz -> 422 flash "window must be one of 7, 30, all"): the
   skeleton placeholder stays in #upcoming-list (5 .rd-skeleton nodes, innerText empty) and
   #upcoming keeps aria-busy="true"; the previous list is not restored. The error flash does show,
   but the list is gone until reload. Cause: skeleton.js restores only on htmx:sendError /
   responseError / timeout / sendAbort, but app-toast.js:186-219 sets detail.isError = false in
   htmx:beforeSwap, so htmx:responseError never fires for HTTP errors (only the network-abort
   case restores the list). Fix: also restore on htmx:beforeSwap when !detail.shouldSwap, or on
   htmx:afterRequest when !detail.successful.
   Screenshot: /tmp/claude-0/-home-user-rising-dough/bb5462da-5905-5890-a7d9-fc9c31189361/scratchpad/shots/dbg500.png (viewed: flash visible, skeleton lines in place of the list).
2. Behavior, a11y, minor. After a successful range swap #upcoming keeps aria-busy="true"
   (skeleton.js sets it in beforeRequest; success replaces only #upcoming-list via outerHTML, and
   nothing removes it). Fix: remove aria-busy on htmx:afterSettle / afterRequest.
3. Layout, pre-existing on MAIN, 375: overflowingElements listed above (no horizontalScroll).

## Screenshots
/tmp/claude-0/-home-user-rising-dough/bb5462da-5905-5890-a7d9-fc9c31189361/scratchpad/shots/<viewport>__<route>.png (today, today_amount_abc, today_amount_1800, today_ranges,
add_happened, add_422, dev_shell_fail, palette_shortcuts, palette_open, shortcuts_open).
Viewed: 375 today, 1440 add_422, dbg500. Checked: hero, bar and stats layout, afford panel,
dialog with the 422 error, flash banner, skeleton state. Palette and shortcuts open with Ctrl+K and ?.
