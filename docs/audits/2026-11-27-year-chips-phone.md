# Frontend audit: CHIPMOB year cell chips on a phone (2026-11-27)

Change: CHIPMOB (T-UR92, R26; branch wi/ui/sourdough/CHIPMOB, sha c1c0ad9f, JS only: `app-year-cell.js`). Operator report from a real phone: "plan/year, the edit toggle chips are floating all around the page in mobile mode, should be fixed to the cell". Fix: place() flips and clamps against visualViewport (offsetTop/height) and re-places (rAF-throttled) on visualViewport resize/scroll, window resize, capture-phase scroll, and at 120/350/700 ms after open.
Route: /plan?tab=year&year=2026 (the only route using app-year-cell.js).
Run: frontend-visual-audit skill (Playwright) against two servers on scratch DBs (never data/budget.sqlite): BASE = merge base 9503cea2 (temporary git worktree, removed afterwards), FIX = c1c0ad9f. Seed: 2026 PLN, Groceries 500 + one-off Mar + recurring Jun, Rent 1,200, Travel, plus 24 filler categories (page height 1770 px at 393 wide, so the page really scrolls). Screenshots in `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/CHIPMOB/shots` (viewed: open-375-Travel-6; others captured per viewport as open-<w>-<category>-<month>.png and year-<w>.png, base-* for BASE).

## Attachment criterion

Chip-group rect against the edited cell (editor) rect, both from getBoundingClientRect: attached = horizontally overlapping the cell and the group top within 0..8 px of the cell bottom (or group bottom within 0..8 px of the cell top when flipped above); exactly one chip group and one editor in the DOM. Sampled 1000 ms after each step.

## Engines

- Chromium, "Pixel 5" descriptor (is_mobile, has_touch, DPR 2.75, 393x727): full matrix, BASE and FIX. Touch via CDP Input.dispatchTouchEvent and Input.synthesizeScrollGesture, pinch via Emulation.setPageScaleFactor, taps via locator.tap().
- Chromium with the "iPhone 13" descriptor (iOS user agent, DPR 3, 390x664): full matrix, BASE and FIX. This is Blink, not WebKit.
- WebKit, "iPhone 13": NOT RUN. Playwright's WebKit (webkit_mac14_arm64_special-2251) launches but browser.new_page() hangs forever in this sandbox, also with a plain context (no device descriptor), so no WebKit result exists. iOS Safari compositing (fixed-position layers lag behind JS during momentum scroll) cannot be reproduced by any of these emulations either.

## Result per scenario (BASE vs FIX; attached = yes in both unless noted)

Same outcome on Pixel 5 and iPhone 13 descriptors unless noted.

| Scenario | BASE | FIX |
|---|---|---|
| 1. Tap-open 8 cells (Groceries 1/6/12, Rent 3/9, Travel 1/7/12) | attached, gap 4 px, 1 group | same |
| 2a-2c. Page scroll: mouse.wheel, scrollBy | attached | attached |
| 2d-2g. Touch swipe up/down (CDP), touch scroll gesture, sample right after the gesture | attached in every sample (group travels with the cell, also when the cell is scrolled off screen) | attached |
| 3. Grid horizontal touch swipe left/right 240 px | attached (group clamped to x 8..258 with the cell off the left edge) | same |
| 4. focus() / scrollIntoView (center, start) | attached | attached |
| 5b. Pinch zoom x2 (visual viewport 197x364) | attached (gap 4 px) but group below the visible area (visibleInVV=false) | group flips above the cell, attached (gap 0 above) |
| 5c. Pan the visual viewport while zoomed | attached, group not in the visual viewport | attached, group in the visual viewport (Pixel 5; iPhone descriptor too) |
| 5d. Pan back | attached, not in visual viewport | attached (above), not in visual viewport (cell itself is off screen) |
| 5e. Zoom reset | attached, below | attached, below |
| 6. Layout viewport height 100% -> 50% -> 35% -> scroll -> 100% (keyboard-like) | flips above the cell, attached | identical |
| 7a-7c, 7f. Tap another cell while one is open (also after a page scroll) | always exactly 1 group + 1 editor, attached to the new cell | same |
| 7d/7e. Tap a heading / the corner while open | editor stays open (no outside-tap close, by design), exactly 1 group, still attached to its cell (page scrolled to top: cell and chips both below the fold) | same |
| 7g. Escape | 0 groups, 0 editors | same |

Orphaned chips: none in any run. The chip group count was 1 whenever an editor was open and 0 after Escape, on BASE and FIX; opening another cell replaced the previous group.

## Does the bug reproduce?

No. On the merge base no scenario produced chips that were detached from the edited cell in layout coordinates (all 35 Pixel 5 and 35 iPhone-descriptor samples attached, 0 BAD). The only BASE/FIX difference found is under pinch zoom: BASE keeps the group below the cell even when that is outside the visible (zoomed) viewport, FIX flips it above to stay in view (5b/5c). The operator's symptom is therefore not reproduced by headless Chromium emulation; the visualViewport-only movement (iOS keyboard, URL-bar collapse, compositor lag during momentum scroll) cannot be simulated faithfully, and WebKit was unavailable. The fix is consistent with the hypothesis and regresses nothing measured; whether it resolves the phone report needs a check on the real device.

## Diagnostics (FIX server, Chromium, light theme)

Columns: horizontalScroll / overflowingElements / duplicateIds / consoleErrors / requestFailures.

| Route (state) | 1440 | 1024 | 375 |
|---|---|---|---|
| /plan?tab=year&year=2026 loaded | false/0/0/0/0 | false/20/0/0/0 | false/20/0/0/0 |
| after 3 open + scroll + Escape cycles | false/0/0/0/0 | false/0/0/0/0 | false/20/0/0/0 |

overflowingElements=20 at 1024 and 375 is the 12-month table.rd-year inside its own scroller (no page horizontal scroll). It is identical on BASE (1024 loaded 20, 375 loaded 20 and 20 after cycles), pre-existing (T-UR71), not caused by CHIPMOB. Console errors and request failures are 0 in every diagnostic run and in all four scenario runs.

Desktop sanity (1440, unchanged): Groceries Jan, Groceries Dec, Travel Jun open with gap 4 px, group inside the viewport (Dec x 1161..1432), 2 chips; Escape leaves 0 groups and 0 editors. 1024 and 375 identical (375 Dec x 96..367, inside the viewport); same coordinates as the earlier YEARCHIP record.

## Step 3b

JS-only change, no template or HTMX change: no template arithmetic or float introduced (nothing in templates touched); swap targets and saves unchanged. IDs: duplicateIds=0 before and after the open/close cycles. No save path was modified; the editor open/close and Escape behaviour is unchanged (checked above).

## Findings

None blocking. Notes: (1) the real-phone symptom is not reproducible here (WebKit unusable in this sandbox, cause remains a hypothesis); (2) the editor stays open after tapping elsewhere (pre-existing, same on BASE), so chips remain until Escape or another save; (3) tapping a cell covered by the open editor's chip group hits the chip instead (by design, chips overlay the row below).
