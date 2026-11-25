# Frontend audit: F8 new-entry dialog and category picker parity (2026-11-25)

Item F8 (branch `wi/ui/sourdough/F8`, audited sha 3ae9e34). Skill `frontend-visual-audit`
(Playwright, Chromium headless shell 158), scratch DB built by `tests/visual/handoff_seed.py`
(`build_seed`), server via `tests.visual.frozen_server` with the frozen clock 2026-10-31
(as `tests/visual/conftest.py`). `data/budget.sqlite` was not touched. Screenshots (all
viewed or spot-checked): `/tmp/fe-audit-f8/*.png`.

## Routes and viewports

Routes: `/today`; `/add?when=happened|planned|repeats` (direct route and dialog opened over
Today with `htmx.ajax('/add?when=..&dialog=1')`); phone sheet via the tab bar `+`
(`.rd-tabbar__new`); category picker open, `zoo` no match, `+ new category` link; blank amount;
blank category / zero amount (422); amount variants; over-limit credit card; account select;
repeats formula; typing during an in-flight refresh; forced 404/409/500 saves.

| Route / state | 1440 | 1024 | 375 |
|---|---|---|---|
| /today | h=false o=0 d=0 c=0 r=0 | h=false o=0 d=0 c=0 r=0 | h=false o=1 d=0 c=0 r=0 |
| /add?when=happened (route and dialog) | 0/0/0/0/0 | 0/0/0/0/0 | h=false o=2-3 d=0 c=0 r=0 |
| /add?when=planned (route and dialog) | 0/0/0/0/0 | 0/0/0/0/0 | h=false o=2-3 d=0 c=0 r=0 |
| /add?when=repeats (route and dialog) | 0/0/0/0/0 | 0/0/0/0/0 | h=false o=2-3 d=0 c=0 r=0 |
| phone sheet via tab bar `+` | n/a | n/a | h=false o=2 d=0 c=0 r=0 |
| picker open / `zoo` no match | 0/0/0/0/0 | 0/0/0/0/0 | h=false o=2 d=0 c=0 r=0 |
| blank amount submit | 0/0/0/0/0 | 0/0/0/0/0 | h=false o=2 d=0 c=0 r=0 |
| 422 (zero amount, no category) | h=false o=0 d=0 **c=1** r=0 | same, c=1 | h=false o=2 d=0 **c=1** r=0 |
| amount 13000 typed | 0/0/0/0/0 | 0/0/0/0/0 | h=false o=3 d=0 c=0 r=0 |
| over-limit preview | 0/0/0/0/0 | 0/0/0/0/0 | h=false o=3 d=0 c=0 r=0 |
| repeats + formula | h=false o=0 d=0 **c=1** r=0 | same, c=1 | h=false o=3 d=0 **c=1** r=0 |
| forced 500 save | c=1 (the 500 itself) | c=1 | c=1, o=3 |

Columns are horizontalScroll / overflowingElements / duplicateIds / consoleErrors /
requestFailures (h/o/d/c/r). Totals: horizontalScroll=0, duplicateIds=0, requestFailures=0.
overflowingElements: 0 at 1440 and 1024; at 375 it lists the chip row's last `label.rd-chip-option`
(right 455) with its hidden radio `input` (396) and, on Today, `pre.rd-hero__loaf` (399). The chips
sit in `.rd-catfield__recent` (`overflow-x: auto`, a deliberate scroller, screenshot shows
ENTERTAINMENT cut at the edge) and the loaf is decorative; the page has no horizontal scroll, so
these are triaged as intended (loaf not part of F8). consoleErrors: every one is the browser's
"Failed to load resource ... 422/500" line for a response the app answers on purpose (422 dialog,
formula preview while incomplete, the forced 500); no JS error, no `pageerror`.

## Behaviour (Step 3b)

- Swap targets: `#modal-root`, `#modal-root .rd-dialog__hero`, `#credit-line`, `#hero-refresh`
  each match exactly 1 element before and after a hero swap and after a 422; no duplicate ids.
- Templates/JS: `rg` over `new-entry.html`, `category-picker.html`, `credit-line.html`, `dialog.html`,
  `amount-input.js`, `combobox.js`, `formula.js` finds no `float`, `/ 100`, `* 100`, `set` block,
  `parseFloat`, `toFixed`, `Math.round`. Money text comes from `money_num` / the view model.
- Amounts (Checking, scratch DB): typed `13000` -> input regrouped `13,000.00` -> stored 1300000;
  `13,000.00` -> 1300000; `1234,50` -> echo `1,234.50` -> stored 123450 (checked in the DB row).
- Rendered = service: credit line `Credit Card · 12,521.63 of 14,977.37 left`, over by 478.37 for
  13,000.00 (12,521.63 left), equals `limit_preview` output over the preview route; repeats formula
  hero `1,896.00` equals the formula line `next amount 1,896.00 PLN`; the hero carries no
  `→ next amount` note.
- Account select: order Credit Card, Checking, Checking EUR, then never-used by name (reconciliation
  rows do not count as use, as `list_by_last_use` documents); keyboard ArrowDown changes the account
  and the hero/preview requests carry the new id. After my own saves on Checking the default became
  Checking (same-day tie, then by name). The seed has no non-PLN account currency, so JPY/EUR formatting
  was not exercisable here.
- Failing saves visible: forced 404 ("That item was not found..."), 409 ("...changed in the
  meantime"), 500 ("Something went wrong on our side. Try again."), 422 (hero error plus
  "Pick a category"); the dialog stays open in each case.
- Phone sheet: bottom sheet, rect 0,154 -> 375,812 (anchored to the bottom), no page scroll.
- In-flight refresh: with the hero response delayed 900 ms, typing `123456` (60 ms/key) kept all six
  digits. A first digit typed less than ~100 ms after a click can be swallowed by the select-on-focus
  frame in `amount-input.js` (observed `23456` when typing 40 ms after the click); not reproducible
  with a human delay, noted only.

## Findings

1. Behavior, medium: over-limit preview missing when the amount is typed before the category and
   account (0 of 3 runs at each of 1440/1024/375, still empty after 2 s). Sequence: type 13000.00,
   pick Takeaway, pick Credit Card. The first preview request (fired by the amount blur, no category yet)
   is still in flight when the category and account `change` events arrive; `#credit-line`
   (`fragments/fields/credit-line.html`) has no `hx-sync`, so htmx drops those triggers and the stale
   empty answer stays. The hero has `hx-sync="this:queue last"`. Fix: add the same `hx-sync` to the
   credit line. Amount typed after category and account works (3/3), as does keyup refresh.
2. A11y surface, medium: after a 422 focus always returns to the amount input (and selects it), also
   when the amount is valid and only the category is wrong (`Pick a category`). That error
   (`p.rd-field__error#catpick-new-entry-error`) has no `role` or `aria-live`; only the fieldset
   `aria-describedby` points at it, so a screen reader announces the amount alert
   (`role=alert`, "Enter an amount above 0.00") but not the category error, and focus is not on the
   invalid field.
3. Behavior, low (triage): the formula preview POST answers 422 while a component is incomplete; the
   console logs it (consoleErrors=1 on repeats + formula). Intended response, but a non-zero
   diagnostic: orchestrator to accept or have the preview answer 200 with the hint.
4. Triage, 422 console line on the dialog 422 and the forced 500 is the browser's network log of a
   deliberate status.

Not verified: real screen-reader output; the 5-min load stayed below 2x cores.
