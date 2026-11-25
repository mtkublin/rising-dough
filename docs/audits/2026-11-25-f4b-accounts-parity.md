# Frontend visual audit: F4b Accounts handoff parity

- Item: F4b (branch `wi/ui/sourdough/F4b`, audited sha c716ae0a), Accounts handoff parity.
- Skill: `frontend-visual-audit` (Playwright, headless Chromium). Scratch DB built by `tests/visual/handoff_seed.py` with modifiers `unreferenced-account` + `account-with-rules`, server on the frozen clock of `tests/visual/frozen_server.py` (2026-10-31). `data/budget.sqlite` untouched.
- Screenshots (viewed): `/tmp/claude-0/-home-user-rising-dough/bb5462da-5905-5890-a7d9-fc9c31189361/scratchpad/shots/<viewport>_<route>.png`.

## Routes x viewports (1440, 1024, 375: all three each)

Each row: horizontalScroll / overflowingElements / duplicateIds / consoleErrors / requestFailures.

| Route (how reached) | Result at 1440, 1024 and 375 |
|---|---|
| /accounts | false / 0 / 0 / 0 / 0 |
| /accounts/new (button) | false / 0 / 0 / 0 / 0 |
| /accounts/new, 422 (blank name, currency XYZ) | false / 0 / 0 / 0 / 0 (see note 1) |
| /accounts/new, typed EUR | false / 0 / 0 / 0 / 0; hero chip reads EUR at all widths |
| /accounts/new, liability without credit limit | false / 0 / 0 / 0 / 0 (note 1) |
| /accounts/4/edit (asset) via row menu | false / 0 / 0 / 0 / 0 |
| /accounts/9/edit (liability) via row menu | false / 0 / 0 / 0 / 0 |
| edit liability, credit limit cleared, save | false / 0 / 0 / 0 / 0 (note 1) |
| /accounts/11/edit?intent=delete (unblocked) | false / 0 / 0 / 0 / 0 |
| /accounts/6/edit?intent=delete (blocked, 2 recurring rules) | false / 0 / 0 / 0 / 0 |
| /accounts/4/reconcile | false / 0 / 0 / 0 / 0 |
| reconcile, bad amount "abc" | false / 0 / 0 / 0 / 0 (note 1) |
| row menu opened by keyboard | false / 0 / 0 / 0 / 0 |
| direct GET of each dialog route (no layout, see finding 3) | false / 0 / 0 / 0 / 0 |

Totals over all 3 x 28 captures: horizontalScroll=0, overflowingElements=0, duplicateIds=0, requestFailures=0.

Note 1: the only console entries are "Failed to load resource: ... 422" produced by the deliberately invalid submits (one per forced 422); no console error on any load, open or valid swap. Counted as 0 consoleErrors for page states; each is the browser's log of the expected 422.

## Step 3b

- Template arithmetic: `rg` for `float`, `/ 100`, `* 100`, `{% set` over `pages/accounts/`, `rows/account-row.html`, `rows/reconcile-snapshot.html`, `charts/sparkline.html`, `fields/credit-line.html`, `states/accounts-empty.html`: no matches.
- Rendered numbers equal service values on the scratch DB (frozen 2026-10-31): net worth 34,439.69 = `compute_fortune.net_base` 3443969; assets 36,895.43 = 3689543; liabilities 2,455.74 = 245574; all 11 per-account balances equal `derive_balances`. "After planned" notes (3,250.52 / -5,480.70 / -2,744.99) differ from balances by -435.29 / +1,120.45 / -289.25, which sum to the hero's planned +395.91. Sparkline polylines come from the view model (points not independently recomputed).
- Failing saves are visible: new account blank name -> "Name is required" and XYZ -> "Unknown currency code", inline; liability with no credit limit (new and edit) -> "positive credit limit required" under the field, dialog stays open; reconcile "abc" -> "invalid number" inline; delete blocked -> "Can't delete Investments D / It has no transactions, but 2 recurring rules still use it. Move or delete them first." with "view recurring rules" and ok. Forced 404/409/500 not run for these forms.
- Keyboard row menu: Enter opens, focus lands on the first visible item (edit at 1440/1024, reconcile at 375 where the inline link is hidden), ArrowDown moves focus; items reconcile, edit, delete, cancel.
- Swap targets: `#account-form`, `#modal-root`, `#account-<id>` each resolved to exactly one element (no failed swaps); no duplicate ids after any swap.

## Findings

1. Edit dialog of a credit-card account (/accounts/9/edit): the type select lists "credit card" twice (value "credit card" unselected, value "credit_card" selected). Template/view-model option list lacks the stored value mapping. Saving may switch the stored type. Layout: no.
2. Delete-blocked wording is "2 recurring rules still use it", not the brief's expected "N planned or recurring items". A planned-items variant is not in the seed so it was not checked.
3. Direct GET of dialog routes (e.g. /accounts/9/edit, the href fallback of each menu item) renders an unstyled bare fragment (no layout, no CSS). In-app HTMX flow is styled.
4. At 375 the hero omits "planned +395.91" shown at 1440; check this is the intended phone design.
5. Screenshots of the delete dialog were taken mid fade-in (translucent); timing, not a defect.

Blocking diagnostics: none.
