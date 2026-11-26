# Frontend audit: D8R reconcile dialog (2026-11-26)

Change: the reconcile dialog per handoff (`pages/overlays/reconcile.html`, `reconcile--liability.html`): one balance field, live hero difference (`hx-get ?hero=1`, `input changed delay:300ms`, `hx-select .rd-dialog__hero`), always booked to Reconciliation, snapshot always saved, no record-as / snapshot checkbox / preview. Item D8R, branch `wi/ui/sourdough/D8R` at 68e2299b. Skill: `frontend-visual-audit` (Playwright, Chromium), scratch DB seeded by `tests/visual/handoff_seed.py` (never `data/budget.sqlite`). Screenshots and JSON in `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/out/` (viewed).

## Routes x viewports

Route: `/accounts` then reconcile on Checking (asset) and Credit Card (liability). Opened by the inline "reconcile" link at 1440/1024 (the row-menu item is phone-only, `rd-menu__item--phone`) and by row menu -> reconcile at 375. Diagnostics taken with the dialog open, after live typing and after failing saves (3 snapshots per row; all identical).

| Route / account | Viewport | Theme | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|---|
| /accounts reconcile Checking | 1440 | light | false | 0 | 0 | 0 | 0 |
| /accounts reconcile Credit Card | 1440 | light | false | 0 | 0 | 0 | 0 |
| /accounts reconcile Checking | 1024 | light | false | 0 | 0 | 0 | 0 |
| /accounts reconcile Credit Card | 1024 | light | false | 0 | 0 | 0 | 0 |
| /accounts reconcile Checking | 375 | light | false | 0 | 0 | 0 | 0 |
| /accounts reconcile Credit Card | 375 | light | false | 0 | 0 | 0 | 0 |
| /accounts reconcile Checking | 1440 | dark | false | 0 | 0 | 0 | 0 |
| /accounts reconcile Credit Card | 1440 | dark | false | 0 | 0 | 0 | 0 |
| /accounts reconcile Checking | 375 | dark | false | 0 | 0 | 0 | 0 |
| /accounts reconcile Credit Card | 375 | dark | false | 0 | 0 | 0 | 0 |

Screenshots (`/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/out/`): `<vp>-<theme>-<Checking|CreditCard>-open.png`, `-typed.png`, `1440-light-*-fail-*.png`, `375-dark-*-fail-*.png`. Checked: dialog layout against the handoff pages (title, hero, "in rising dough" fact, one field with PLN suffix, liability hint line, SNAPSHOTS list, cancel + [ reconcile ]; no extra controls: the control list per dialog is Close, actual_balance, cancel, [ reconcile ]), bottom sheet at 375, dark theme contrast.

The only non-zero consoleErrors in the whole run are the browser's "Failed to load resource 404/409/500/422" lines of the deliberately forced and invalid POSTs in the failing-save tests (below), not of normal use.

## Behaviour (Step 3b)

1. Swap targets: every `hx-target` on the page matches exactly one element with the dialog open (`#modal-root`, `#account-<id>`, `#modal-root .rd-dialog__hero`: count 1 each), and no duplicate ids after the hero swap or after the save swap.
2. Live hero: typing 3690.10 on Checking (in rising dough 3,685.81) gives `+4.29 PLN difference` after the 300 ms debounce (one `?hero=1` request per typed value, hero updated within 1 s); the input element is the same node after the swap (identity kept), keeps its value (3690.10) and keeps focus. Credit Card (available 12,521.63): `−8,831.53` for 3690.10 (= 3690.10 − 12,521.63). Same at 1440, 1024, 375, light and dark. A GET with `actual_balance=abc` answers 200.
3. Rendered number equals the service value: save on Checking with 3690.10: hero +4.29, DB transaction amount 429 (Reconciliation, "auto-reconciliation 2026-10-31"), row balance 3,690.10; Credit Card with 12400.00: hero −121.63, DB amount −12163, row available 12,400.00. Net worth +4.29 on the page.
4. Save outcome: dialog closes, flash "Checking reconciled" / "Credit Card reconciled" visible, balance row updated, exactly one adjustment transaction per save with category Reconciliation (ledger shows both), a snapshot row added (reopen lists 26 NOV 3,690.10 for Checking, 26 NOV 12,400.00 available credit for the liability; stored balance −257,737 minor), reopened hero 0.00.
5. Failing saves: empty and "abc" typed by keyboard: the amount filter turns "abc" into an empty value and the field's `required` shows the browser's native "Please fill out this field."; dialog stays open, no request. With native validation bypassed (value forced to "", "abc", "1,2,3"): 422, dialog stays open, visible "▲ invalid number" under the field, typed value kept ("abc", "1,2,3"; empty stays empty), field highlighted. Forced POST 404 / 409 / 500 (`page.route`): visible field-level messages ("That item was not found...", "That item changed in the meantime...", "Something went wrong on our side. Try again."), dialog stays open, nothing looks saved.
6. No arithmetic in templates: `rg` of `dialog-reconcile.html` and `reconcile-snapshot.html` for float, `/ 100`, `* 100`, `set`, round and currency literals: no matches. Events: the save emits `balance-stale` and `forecast-stale`; both have listeners (accounts panels `hx-trigger="balance-stale from:body"`, forecast hero).
7. Money by currency (two extra accounts inserted in the scratch DB; GET `?hero=1`): JPY 150,000 -> 150500 gives `+500 JPY` (zero decimals); EUR 100.00 -> 100.55 gives `+0.55 EUR`. Observation: JPY 100.55 (fraction) shows `0`, a silent rounding; not blocking.

## Findings

None blocking. Non-blocking notes:
- Empty/non-numeric input is caught by the browser (`required` plus the amount filter) before the server; the server-side "invalid number" message is only reachable when native validation is bypassed. Behaviour is visible either way.
- The saved flash text appears twice in the accessibility/flash selectors I queried (toast region and live region); the screenshot shows one banner.

Result: CLEAN.
