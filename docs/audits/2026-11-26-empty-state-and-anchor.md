# Frontend audit: empty-state "new account" dialog and income-anchor refresh (ACCFIX)

Date: 2026-11-26. Branch `wi/ui/sourdough/ACCFIX`, sha 556be776. Tool: `frontend-visual-audit` skill (Playwright, Chromium), scratch DB (migrated, one login user, no accounts), never `data/budget.sqlite`.

Change: `fragments/states/accounts-empty.html` and `ledger-first-run.html` "new account" now `hx-get` the account dialog into `#modal-root`; the income-anchor form moved inside `#settings-categories` in `pages/settings/categories.html` so it refreshes on category create. The category picker "+ new category" link is unchanged (follow-up).

## Routes x viewports

| Route (state) | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /accounts (no accounts) | 1440 | false | 0 | 0 | 0 | 0 |
| /accounts (no accounts) | 1024 | false | 0 | 0 | 0 | 0 |
| /accounts (no accounts) | 375 | false | 0 | 0 | 0 | 0 |
| /ledger (first run, no accounts) | 1440 | false | 0 | 0 | 0 | 0 |
| /ledger (first run, no accounts) | 1024 | false | 0 | 0 | 0 | 0 |
| /ledger (first run, no accounts) | 375 | false | 0 | 0 | 0 | 0 |
| /settings?tab=categories | 1440 | false | 0 | 0 | 0 | 0 |
| /settings?tab=categories | 1024 | false | 0 | 0 | 0 | 0 |
| /settings?tab=categories | 375 | false | 2 (see below) | 0 | 0 | 0 |

The dialog-open state of /accounts and /ledger was also captured at all three viewports: all five signals 0/false. After-save (/accounts) and after-category-create (/settings) at 1440: all 0/false, no duplicate ids after the swaps.

Overflow at 375 on /settings?tab=categories: two `a.rd-tabs__tab` elements ("preferences", "security") lie past the viewport. Their container `.rd-tabs` is `overflow-x: auto` (scrollWidth 472, clientWidth 311) and the page has no horizontal scroll. This is the designed scrollable tab strip; the change touches no CSS or tab markup (empty static diff), so it is identical on `ui/sourdough`. Triaged as pre-existing and by design, not a finding.

## Step 3b (behaviour contract)

- Empty-state button opens the dialog in place: on /accounts and /ledger at 1440, 1024 and 375 the click leaves the URL unchanged and `#modal-root` fills with the "new account" form. ok
- Save: name "Main PLN", currency PLN, opening 100.50 -> /accounts lists the account (balance 100.50 PLN, "1 accounts"), the empty state is gone, `#modal-root` emptied. ok
- Failing save, validation: `required` removed, empty name submitted -> 422, dialog stays open with "Name is required" and "ISO 4217 code required" inline. ok
- Failing save, duplicate name: dialog stays open with the visible banner "Couldn't save. Your changes are still in the form. (Reference: ...) retry"; the form is not left looking saved. ok (visible). Observation, not blocking: the server log shows an unhandled `IntegrityError` on POST /accounts, so the user gets the generic 500 banner, not a field error on name. Account-create code is not part of this change.
- Category create (income "Salary X") from settings: the `#income-anchor` options went from `[none]` to `[none, Salary X]` without reload (`settings-categories-stale` listener fired; one `#settings-categories`, one `#income-anchor`). ok
- Anchor save: selecting "Salary X" saves on change; after a reload the select shows "Salary X". ok
- Template logic: `rg` for `float`, `/ 100`, `* 100`, `{% set` over the three touched templates returns nothing. ok
- Swap targets: `#modal-root` and `#settings-categories` each match exactly one element before and after the swaps; duplicate-id diagnostic is 0 after each swap. ok
- Console errors and request failures during the whole flow, excluding the forced failures: 0 and 0. ok

## Findings

None blocking. One non-blocking observation (duplicate account name gives the generic 500 banner, see above), for a separate item.

## Screenshots (viewed)

All under `/tmp/fe-audit-accfix/` (not committed): `{1440,1024,375}_{accounts,ledger}_{empty,dialog}.png`, `{1440,1024,375}_settings_categories.png`, `dialog_error.png` (inline 422 messages), `dup_error.png`, `accounts_after_save.png`, `cat_dialog.png`, `settings_after_create.png`. Checked: empty state and dialog layout (mobile renders the dialog as a bottom sheet), inline errors, no clipped content, the anchor select inside the categories region.
