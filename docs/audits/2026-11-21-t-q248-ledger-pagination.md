# Frontend audit: T-Q248 ledger pagination race (hx-sync)

Change: T-Q248 (Q-056, Q-057). `templates/ledger/index.html` (filter form and search input) and
`templates/ledger/_table.html` (Older/Newer pager buttons) gain `hx-sync="#ledger-table:replace"`, so a
newer request on the ledger table aborts a still-in-flight one instead of letting a late response swap
over the newer page. No markup, class or target changes otherwise.

Run: `frontend-visual-audit` (Playwright, headless Chromium), app on a migrated scratch DB
`/tmp/t-q248.sqlite` (never `data/budget.sqlite`), logged in through the password form; 55 seeded
transactions (52 Alpha, 3 Beta) so pagination renders.

## Routes and diagnostics

| Route | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /ledger?view=actual | 1440 | false | 0 | 0 | 0 | 0 |
| /ledger?view=planned | 1440 | false | 0 | 0 | 0 | 0 |
| /ledger?view=recurring | 1440 | false | 0 | 0 | 0 | 0 |
| /ledger?view=actual | 1024 | false | 0 | 0 | 0 | 0 |
| /ledger?view=planned | 1024 | false | 0 | 0 | 0 | 0 |
| /ledger?view=recurring | 1024 | false | 0 | 0 | 0 | 0 |
| /ledger?view=actual | 375 | false | 27 (table.ledger descendants) | 0 | 0 | 0 |
| /ledger?view=planned | 375 | false | 8 (table.ledger descendants) | 0 | 0 | 0 |
| /ledger?view=recurring | 375 | false | 8 (table.ledger descendants) | 0 | 0 | 0 |

Triage: the 375 `overflowingElements` are the ledger table wider than the viewport inside its
horizontally scrollable wrapper; `horizontalScroll` stays false and the markup is untouched
(pre-existing, same as the T-Q209 record).

## Behaviour (Step 3b)

1. Swap targets: after clicking "Older" (response awaited) and after changing the category filter,
   `document.querySelectorAll('#ledger-table').length === 1` at every viewport.
2. Pagination result: page 2 of the 55-row ledger shows exactly 5 rows; filtering to Beta shows exactly 3.
3. Failing saves: no state-changing form touched; N/A.
4. No arithmetic or literals added to templates (the diff is four `hx-sync` attributes).
5. Duplicate ids after the swaps: 0.
6. Scratch data only: yes.

## Screenshots (viewed)

`/tmp/fe-audit-tq248/{1440,1024,375}_{actual,planned,recurring}.png` and
`/tmp/fe-audit-tq248/{1440,1024,375}_actual_page2.png`. Checked: the pager shows "Page 2" with only
"Newer" and the 5 remaining rows; nothing clipped.
