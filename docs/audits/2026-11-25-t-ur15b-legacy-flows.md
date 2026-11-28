# Frontend visual audit: T-UR15 slice b (UR15b), legacy old-shell flows removed

- Item: UR15b, branch `wi/ui/sourdough/UR15b`, head `5c5314d5`; MAIN `ui/sourdough` (`3c5aec99`) used for the pre-existing comparison.
- Method: `frontend-visual-audit` skill (Playwright, Chromium), own server on a scratch copy of `data/demo.sqlite` (migrated), plus an emptied scratch copy for the empty states. `data/budget.sqlite` untouched.
- Screenshots (scratchpad, viewed): `/tmp/claude-0/-home-user-rising-dough/86228838-e551-5ec3-979b-dd5580a5d147/scratchpad/a/shots/{1440,1024,375}_*.png`. Checked: dialog layout, 422 summary + hero error, flash banner, tab counts, no clipped save button.

## Routes x viewports (1440 / 1024 / 375 each)

`/today`, `/ledger`, `/ledger?view=planned`, `/ledger?view=recurring`, empty-state `/ledger` (actual, planned, recurring on an emptied DB), `/add?when=happened|planned|repeats&dialog=1` (direct GET in a fresh tab), removed URLs `/transactions/new`, `/planned/new`, `/recurring/new`.

| Signal | 1440 | 1024 | 375 |
|---|---|---|---|
| horizontalScroll | 0 | 0 | 0 |
| overflowingElements | 0 | 20 on `/ledger?view=planned` and `?view=recurring` (actions column `th/td/button`, right=1058, inside the table scroller) | 1 per page (`pre.rd-hero__loaf` on Today, `a.rd-tabs__tab` on Ledger, `label.rd-chip-option` in the dialog) |
| duplicateIds | 0 | 0 | 0 |
| consoleErrors | 0 (only the deliberately forced 422/500 resource lines) | same | same |
| requestFailures | 0 | 0 | 0 |

Overflowing elements: identical counts, selectors and right edges on MAIN (`3c5aec99`) at the same routes and viewports (pages, and the dialog opened with `n`). No horizontal scroll results. Pre-existing, not introduced by UR15b; they are still a non-zero signal for the orchestrator to triage.

## 1. Ways to open a new entry

| Opener | 1440 | 1024 | 375 |
|---|---|---|---|
| Top bar `[ new entry ]` on Today | dialog | dialog | hidden (tab bar instead) |
| Top bar `[ new entry ]` on Ledger | dialog in place, URL stays `/ledger` | same | hidden |
| Tab bar `+` | hidden | hidden | dialog |
| Palette (Ctrl+K, "New entry") | dialog | dialog | dialog |
| Key `n` | dialog | dialog | dialog |
| Empty-state `[ new entry ]` (actual, planned, recurring), href `/add?when=happened&dialog=1` | dialog | dialog | dialog |
| Direct GET `/add?when={happened,planned,repeats}&dialog=1`, fresh tab | dialog on the right tab, URL replaced with `/today` | same | same |

No FAB present. Finding F1: from `/ledger`, the tab bar `+`, the palette and `n` do a full navigation through the shell page and land on `/today` (hx-replace-url `/today`); only the Ledger top bar button opens in place. A save from there is "off the ledger" and reloads Today.

## 2. Create each kind (on `/ledger`)

| Kind | Flash | Dialog | Ledger update without reload (marker kept) |
|---|---|---|---|
| happened | "Transaction saved" | closed | yes: tab count +1, hero 19,436.52 -> 19,448.86 (12.34), row visible |
| planned | "Planned entry saved" | closed | yes: planned +1, planned net -2,259.14 -> -2,271.48 (12.34) |
| recurring | "Recurring rule saved" | closed | yes: recurring +1, per month -13,754.94 -> -13,767.28 (12.34) |

Rendered numbers equal the expected value (old value plus the posted 12.34). At 375 the ledger opener goes through `/today` (F1), so the in-place update is verified at 1440 and 1024 only.
Off the ledger (from Today): the page reloads (`HX-Refresh`, marker lost), the new row exists; no flash is visible after the reload at any viewport (F2).

## 3. Failing saves

- Empty amount (browser `required` removed to reach the server): 422 for `/transactions`, `/planned`, `/recurring`. The dialog stays open with the hero error, the error summary ("1 field needs attention", link to Amount / Default Amount) and `aria-invalid` on the field. All three kinds, all viewports.
- Forced 500 (`page.route`): dialog stays open and "Something went wrong on our side. Try again." shows as an alert; nothing looks saved. All three kinds, all viewports.

## 4. Today upcoming row actions

Row menu (kebab) holds skip and override; `promote` is the row button. promote opens `promote-dialog`, override opens `override-occurrence-dialog`, skip posts and flashes "Next occurrence skipped". All at 3 viewports. There is no `edit` action on recurring upcoming rows (demo has no planned item upcoming); noted, not a regression claim.

## 5. Removed URLs

`GET /transactions/new`, `/planned/new`, `/recurring/new` (plain and HX) answer **405** `{"detail":"Method Not Allowed"}`, not 404: the POST-only `/{id}` routes match the path (F3). No rendered HTML of Today, Ledger (3 views), Accounts, Plan, Budget, Settings or the dialog contains `/transactions/new`, `/planned/new`, `/recurring/new` or `slideover`; `rg` over `src/` finds none either.

## Step 3b

1. Swap targets: every non-relative `hx-target` on Today and the three ledger views matches exactly one element, before and with the dialog open. ok.
2. Failing saves visible: 422 and 500 per kind (section 3). 404/409 not separately forced (shared handler contract, ADR-0143). ok for the forced cases.
3. No arithmetic in templates: `rg` of the changed templates for `float`, `/ 100`, `* 100`, `{% set` returns nothing.
4. Currency formatting: not exercised for JPY in this slice (no template change to money output).
5. Rendered numbers equal the expected service value (section 2). ok.
6. IDs and listeners: no duplicate ids with the dialog open; `ledger-stale`, `balance-stale`, `forecast-stale` events refreshed the hero and tab counts. ok.
7. Scratch data only. ok.

## Findings

- F1 (Behavior): `/ledger` tab bar `+`, palette "New entry" and `n` leave the ledger for `/today`; only the top bar button opens in place. Likely the shell-page `hx-replace-url="/today"` in `pages/entries/open.html`.
- F2 (Behavior): after a save off the ledger the page reloads via `HX-Refresh` and the out-of-band success flash is lost; no confirmation is visible (`web/htmx.py` `refresh_unless_on`).
- F3 (Contract): removed URLs answer 405, not 404.
- Triage: overflowingElements counts above are identical on MAIN; no horizontal scroll.
