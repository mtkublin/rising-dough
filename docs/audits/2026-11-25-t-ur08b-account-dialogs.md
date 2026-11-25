# Audit: UR08b account dialogs on the shared dialog shell (2026-11-25)

## Scope

Change: T-UR08b (ADR-0107). The accounts new, edit, delete (confirm, blocked, blocked-planned) and reconcile (asset, liability, preview) dialogs and the row menu moved onto `fragments/dialogs/dialog.html` and `fragments/menus/row-menu.html`. Branch `wi/ui/sourdough/UR08b`, head `2901c9e5`.

Route: `/accounts` (all dialogs open in `#modal-root`; delete confirm is `GET /accounts/<id>/edit?intent=delete`, reconcile preview is `POST /accounts/<id>/reconcile?preview=1`).

Run: Playwright (Chromium) against a scratch copy of `data/demo.sqlite` with FX cache rows for EUR and JPY, added accounts `Euro Cash` (EUR 1,234.56), `Yen Wallet` (JPY 12,345), `Visa Gold` (liability, limit 3,000.00, balance -500.00), `Spare` (deletable), `PlannedOnly` (blocked by a planned item). Light and dark (`html[data-theme]`). Every capture waits for `dialog[open]` and then for `getAnimations({subtree:true}).length === 0` (+300 ms). The page is served with its own CSP (no `bypass_csp`).

## Diagnostics

13 states per viewport and theme (list, row menu, new empty, new filled, new 422, edit asset, edit liability, delete confirm, delete blocked, delete blocked-planned, reconcile asset, reconcile liability, reconcile preview): 78 captures.

| Route | Viewport | Theme | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|---|
| /accounts (all 13 states) | 1440 | light, dark | false | 0 | 0 | 0 | 0 |
| /accounts (all 13 states) | 1024 | light, dark | false | 0 | 0 | 0 | 0 |
| /accounts (all 13 states) | 375 | light, dark | false | 0 | 0 | 0 | 0 |

consoleErrors: the only entries are Chromium's own `Failed to load resource ... 422` line for the deliberately forced 422 (new 422 state) and the `500` lines of the forced-500 checks in Step 3b. No script error, CSP violation or other console error appeared in any state.

## Side by side with docs/design/rising-dough-frontend/pages/overlays/

Compared: new-account, new-account--filled, new-account--error, edit-account, edit-account--liability, delete-account, delete-account--blocked, delete-account--blocked-planned, reconcile, reconcile--liability, row-menu--account (handoff rendered at 1440 and 375 from the files).

- Delete confirm, blocked, blocked-planned, reconcile asset and liability (static difference hero, `balance in your bank` / `remaining balance in your bank` field, snapshots, actions) and the row menu (desktop popover with edit/delete, phone sheet with reconcile/edit/delete, delete in the danger colour): match the handoff in band, hero, spacing, actions and dark tokens.
- Hidden cancel at 375: confirmed. In the sheet `cancel` computes `display:none` (width 0) and the visible close paths are the round close button, the scrim and Escape (all three closed the dialog at 375). This matches the handoff (hidden by `.rd-dialog__body .rd-dialog__actions .rd-btn--quiet[data-js="dialog-close"]`).
- derived.md deviations seen and accepted: credit-limit field (shown for liability), `record as` select, `also save a balance snapshot` checkbox, preview button, delete served by the edit route. No other undeclared difference except F1 and F2 below.

## Step 3b

- Swap targets: `#modal-root` is the single target of every dialog trigger and of the preview button; `#account-form` (contract-pinned) exists once; `#account-<id>` rows are unique before and after each swap. Result: ok.
- Failing saves are visible: new 422 (summary "2 fields need attention", `▲ name required`, `▲ ISO 4217 code required`), edit 422 (`▲ name required`), reconcile with `abc` (`▲ invalid number` plus summary), forced 500 on create, edit, reconcile and delete (toast "Something went wrong on our side. Try again.", dialog stays open, nothing looks saved). Result: ok.
- No arithmetic: `rg` for `float`, `/ 100`, `* 100`, `{% set` over `dialog-account.html`, `dialog-delete.html`, `dialog-reconcile.html`, `account-row.html`: no match.
- Money by currency: `1,234.56 EUR`, `12,345 JPY` (no decimals), reconcile of the JPY account `-345` (no decimals).
- Rendered equals service (same scratch DB): reconcile Euro Cash typed 1300.00 prints `+65.44`, `preview_difference` = 6544 minor; Visa Gold (available-credit entry) typed 2000.00 prints `−500.00`, service -50000; Yen Wallet typed 12000 prints `−345`; used % / available: Credit Card `16% / 12,521.63 of 14,977.37` and Visa Gold `16% / 2,500.00 of 3,000.00`, equal to `accounts_data.hydrate` (16, 1252163, 1497737) and (16, 250000, 300000).
- Signs use U+2212 (`−50.50`, `−500.00`, `−345`, `−6,601.15`).
- After create, edit, reconcile and delete: the row list updates (new row, renamed row, `120.00 EUR` and txn count 1, Spare row removed), `#modal-root` is empty (length 0), no `dialog[open]`, no duplicate ids. Delete shows the toast `Account deleted`. The old flow had no delete undo toast (old reconcile dialog only said the adjustment can be undone), so none is expected.
- ✕, scrim and Esc leave the closed `<dialog>` markup in `#modal-root` (no open dialog, no duplicate ids; the next open replaces it). Observation only.
- Events: `balance-stale`, `forecast-stale` are emitted by delete and reconcile and the page refetches on them (row removal and row update observed).

## Findings

Status: FINDINGS (diagnostics are all zero; F1 is a visible overlap and should be fixed before merge).

- F1 Layout, new and edit dialogs, every width and theme: the wrapper `<div id="account-form">` in `src/budget_planner/web/templates/pages/accounts/dialog-account.html:12` is a plain block inside `.rd-dialog__body` (a flex column with `gap: var(--space-5)`, `static/rd/css/components/dialog.css:138`). The fields lose that gap, so labels sit directly under the previous input (handoff has about 28 px between fields) and, in the 422 state, `▲ ISO 4217 code required` is drawn over the hint `currency is fixed after creation` (1440 and 375). Suggested fix: give `#account-form` `display:flex; flex-direction:column; gap:var(--space-5)` (or `display:contents`; the contract only pins its `hx-target`). Screenshots: `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/shots/1440-light-new-error.png`, `.../shots/375-light-new-error.png`, `.../shots/1440-light-edit-liability.png`; handoff reference `.../scratchpad/hand/1440-new-account--error.png`.
- F2 Content, new dialog: the handoff `new-account*` overlays carry an `as of` date field (`name="asof"`); the app dialog has none and `derived.md` does not list it. Declare it as a deviation or add the field.
- F3 Behavior (minor), new dialog: the hero unit stays `PLN` while `EUR` is typed in the currency field (only a 422 re-render updates it). `.../shots/1024-dark-new-filled.png`.
- F4 Behavior (minor, pre-existing contract): POSTing an empty `name` (only possible past the browser `required`) reaches FastAPI's required-field check and the raw JSON `{"detail":[{"type":"missing",...}]}` is swapped into the dialog instead of the field summary. `name: str = Form(...)` in `src/budget_planner/web/routers/accounts.py` (create). Whitespace-only names get the proper summary.

## Captures viewed

All in `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/shots/` (`<vp>-<theme>-<state>.png`, 78 files, plus `flow-*.png` for the Step 3b flows). Viewed: 1440 light new-empty, new-error, edit-liability, delete-blocked, reconcile-preview, row-menu; 375 light new-error, reconcile-liability; 375 dark row-menu, delete-confirm; 1024 dark new-filled. The rest were checked through the DOM diagnostics (identical values across states).
