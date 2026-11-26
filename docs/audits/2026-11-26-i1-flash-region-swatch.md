# Frontend audit: I1 (single #flash-region, category swatch snap, picker placeholder)

Date: 2026-11-26. Item: I1, branch wi/ui/sourdough/I1. Audited code: sha 50176cb (exported with
`git archive`; the worktree HEAD later moved to a merge of ui/sourdough and gained uncommitted
category-colour edits, which are NOT part of this audit). Tool: frontend-visual-audit skill
(Playwright, Chromium), scratch DB seeded by `tests/visual/handoff_seed.py` (never `data/budget.sqlite`),
frozen clock 2026-10-31 as in `tests/visual/conftest.py`, `BUDGET_ENV=dev`.
Screenshots: `/tmp/claude-0/-home-user-rising-dough/bb5462da-5905-5890-a7d9-fc9c31189361/scratchpad/i1/shots/<viewport>__<name>.png` (viewed: shell flash stack, dialog flash at 375,
category edit dialog, new-category 422 at 375).

## Routes x viewports (1440, 1024, 375)

/today, /accounts, /settings?tab=categories, /add?when=happened, /dev/shell, plus states: dev shell
409/500/404 flashes, toast, dialog-saved flash, saved + error stacked, accounts new-account blank
name (422) and forced 500, account create (HX-Refresh), edit-category dialog (Takeaway, id 19) and
save unchanged, new-category dialog and blank 422, category picker open.

## Diagnostics (all 19 states at each of 3 viewports)

| Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|
| 1440 | 0 | 0 | 0 | 0 (*) | 0 |
| 1024 | 0 | 0 | 0 | 0 (*) | 0 |
| 375 | 0 | /today 1 (pre.rd-hero__loaf), /settings categories 3 (a.rd-tabs__tab), /add 1 (label.rd-chip-option); document does not scroll | 0 | 0 (*) | 0 |

(*) The only console entries are the browser's "Failed to load resource" line for the deliberately
forced 404/409/422/500 responses. No script errors. `#flash-region` count is 1 in every state.

375 overflowingElements are identical on MAIN (ui/sourdough db4357a, same seed): inner scroll
containers (hero loaf, tab strip, chip row), `horizontalScroll` false. Pre-existing, not from I1.

## Step 3b

- Swap targets: every `hx-target` on /add, /settings, /accounts matches exactly 1 element: ok.
- Flash region: one `#flash-region` (role=status, aria-live=polite). An error flash inside it keeps
  its own role=alert (409, 500, 404, retry variant), saved flash is role=status. Stack: saved then
  error, gap 8px (138-130) at 1440; a new flash replaces only the previous of its own kind.
  In an open dialog the flash is rendered in a dialog region with the same roles (500 on new-account
  save: visible error, dialog stays open, form values kept) at 1440/1024/375. Retry re-issued the
  request (2 requests), close removed the flash.
- Failing saves: new-account blank name: native `required` blocks first; with novalidate the 422
  shows "Name is required" and "ISO 4217 code required" inline; forced 500 shows the flash; new
  category blank name 422 shows the flash summary "Some fields need fixing: Name". No silent failure.
- Templates/JS diff: no float, /100, *100 or set blocks added.
- IDs/listeners: no duplicate ids after any swap.
- Picker: placeholder and trigger text "search all 24 categories" (24 options), matches the option count.

## Findings

1. DATA-ALTERING (category dialog): Takeaway is stored `#ff9f43`; the dialog preselects swatch
   tangerine (`#f97316`, preview chip tangerine, as designed). Saving the dialog unchanged writes
   `#f97316`: DB before `#ff9f43`, after `#f97316` (all three viewports). A plain save recolours
   the category (board colour changes). Needs the unchanged-save guard (keep the stored hue when the
   posted swatch is the preselected neighbour). The uncommitted edits seen in the worktree
   (category_forms._keeps_stored_colour) look like that fix; they were not audited.
2. Flash visibility: `#flash-region` is in normal flow (position static). After a button lower on
   the page is used, the flash can sit above the viewport (top -152 at 1024, -116 at 375 on /dev/shell):
   announced to AT but not visible without scrolling. Triage: layout decision (sticky/fixed region?).
3. HX-Refresh flows (create account/category) reload the page, so the "saved" flash is not shown
   after the reload (region empty). By design since T-D150 (swap none + refresh); the confirmation
   is lost.
4. Dialog 422 for the new-category form shows only the summary flash, no inline field error under
   name (account form has inline errors). Minor.

No blocking diagnostic from the layout signals. Finding 1 is a behaviour/data finding.
