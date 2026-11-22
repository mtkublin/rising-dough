# Rising Dough · frontend handoff

Static HTML, CSS and JS for the "Sourdough" redesign. Every page, overlay and state from the design canvas
is here as a complete HTML document that opens straight from disk: no build, no server, no install.

- Start at **`index.html`**. It links every page, overlay and state, and has a theme switch
  (system · light · dark) that applies to every page you open afterwards (saved in this browser).
- **`components.html`** shows every component, variant and state on one page.
- **`charts/`** has one static SVG example per chart type, with geometry notes.

Sources: the design canvas *Rising Dough · Sourdough redesign* (dark page + light page) and the
*Rising Dough Frontend Handoff Spec*. Light is the dark design with colours only (canvas note L_n12), so each
screen has **one markup**; both themes come from tokens.

---

## What changed in this update (design change T-UT06)
The canvas gained and changed boards; this package follows them:

- **Ledger › actual and planned:** `export ▾` to the right of the tabs, a menu with *export as csv* and
  *export as parquet* (fragment `ledger/export-menu`). The phone ledger board has no export; here it wraps onto
  its own line under the tabs rather than being dropped (deviation 16).
- **Credit-limit line** under account / date in New entry › happened, the phone sheet and Edit transaction
  (fragment `fields/credit-line`, shown only while a credit account is picked via `data-show-when`). New state
  `overlays/new-entry--over-limit.html` (▲ over-limit line, `role="alert"`, saving still allowed).
- **Settings › Users** rebuilt: `+ add user` and `+ invite by email` next to the tabs, one Users table with a
  row menu (member: reset password, delete user · invite: copy link, resend invite, revoke invite). The old
  *Invite someone* card is gone. New overlays: `add-user` (+ `--error`),
  `one-time-password`, `reset-password`, `delete-user`, `invite-user` (+ `--error`), `revoke-invite`. These
  dialogs use the new 460px size (`rd-dialog--md`, token `--size-dialog-md`).
- **Edit user** (follow-up ST17): *edit user* is the first item in a member's row menu and opens
  `overlays/edit-user.html` (email fixed and read-only, name, member/admin, `[ save ]`). The owner's own row has
  no menu, so an admin can't demote or delete themselves.
- **Delete account:** new copy; the blocked state links to what still points at the account. New state
  `overlays/delete-account--blocked-planned.html` (blocked only by recurring rules). In the accounts menu,
  Investments D opens that state and accounts with transactions open the blocked one.
- **Auth:** sign in, invite and the new screens follow the new desktop and phone boards: `register` (+ `--error`),
  `force-password` (+ `--error`), `invite--used`, `invite--invalid`, the invite's name field and new expired copy.
  Phone auth screens use the rounded band; the large headline appears on phone for sign in only.
- **Dev notes wired:** promote shows a "Promoted · undo" toast; Analytics category rows open the ledger filtered
  to that category (`?category=`), which `filters.js` preselects in the static files.

**Not in this package:** the separate *Feedback* handoff (feedback dialog, `f` shortcut, removal of the command
palette). The redesign canvas still has the palette boards, so the palette stays here; apply that handoff on
top of this base.

---

## 1. Structure

```
rising-dough-frontend/
├── README.md
├── index.html                       links to everything below
├── components.html                  every component, variant and state
├── charts/                          forecast, income-vs-expense, spend-by-category, sparkline, year-grid
├── pages/
│   ├── today.html  today--empty  --loading  --afford-over  --afford-invalid  --flash
│   ├── accounts.html  accounts--empty
│   ├── auth/        login, reauth, register (first run), invite (+ --expired, --used, --invalid), force-password; each with --error where drawn
│   ├── ledger/      actual (+ --empty, --no-matches, --long), planned (+ --empty), recurring (+ --empty), recently-deleted
│   ├── plan/        budget, year, forecast, analytics
│   ├── settings/    categories, currency-fx, preferences, security (+ --error), users
│   ├── errors/      404, 409, 422, 500, offline
│   └── overlays/    each overlay open on top of its page (62 files, see index.html)
├── static/
│   ├── css/main.css               @layer order + @import list only
│   ├── css/tokens.css             every colour, size, space, radius, z-index, duration; themes; breakpoints
│   ├── css/reset.css base.css layout.css utilities.css
│   ├── css/components/            one file per component
│   ├── css/pages/                 only where a screen needs its own rules
│   ├── js/                        one file per behaviour (+ theme.js)
│   ├── fonts/                     woff2 + OFL licences
│   ├── icons/sprite.svg
│   └── img/favicon.svg
└── .stylelintrc.json              stylelint-config-standard + BEM class pattern (see §8)
```

All asset paths are relative (`../../static/css/main.css`), ready to be rewritten to `/static/`.

## 2. Templates and fragments

Every reusable or swappable piece is wrapped in boundary comments:

```html
<!-- fragment: rows/transaction-row -->
<tr class="rd-row rd-row--tx">…</tr>
<!-- /fragment -->
```

Fragment names in use: `rows/transaction-row`, `rows/transaction-day`, `rows/upcoming-row`, `rows/planned-row`,
`rows/recurring-row` (row + its expandable detail row in one `<tbody>`), `rows/account-row`, `rows/category-row`,
`rows/budget-line`, `rows/year-grid-row`, `rows/year-cell-editor`, `rows/forecast-month`, `rows/analytics-category`,
`rows/user-row`, `rows/session-row`, `rows/reconcile-snapshot`, `rows/deleted-planned`, `rows/deleted-category`,
`today/upcoming-list`, `today/afford-result` ("Can I afford it?" result), `fields/category-picker` (combobox list),
`fields/formula`, `fields/formula-component` (formula preview = the `<output>` inside `fields/formula`),
`ledger/filter-bar`, `ledger/pagination`, `ledger/bulk-bar`, `plan/period-nav`, `plan/unbudgeted-disclosure`,
`popovers/period-picker`, `charts/forecast`, `charts/income-vs-expense`, `forms/error-summary`,
`flash/success`, `flash/error`, `toast/undo`, `states/*` (empty and loading), `overlays/*` (every dialog).
The credit-limit preview is the `.rd-account__credit` line inside `rows/account-row`.

- Fragments never style off siblings (`+`, `~`, `:nth-child`). Every row draws its own top rule.
- Repeated fragments are identical apart from data. Ids inside a row (popover ids, checkbox ids) are data too:
  derive them from the record id.
- `#modal-root`, `#drawer-root`, `#toast-root` and `#flash-region` are on every page. Overlay pages show the
  dialog inside `#modal-root`; `dialog.js` opens any `dialog[data-js~="modal"]` found there with `showModal()`
  on load and on `htmx:load`.
- The command palette (`#palette`) and the shortcuts help (`#shortcuts`) are global dialogs rendered once per
  page after the roots, closed. Put them in the base template.
- **Icon sprite:** `static/icons/sprite.svg` is the source. Each page carries an inline copy at the top of
  `<body>` and uses `<use href="#icon-close">`, because Chrome refuses external `<use>` references on `file://`
  (it would break "no console errors from disk"). In Jinja: `{% include "sprite.svg" %}` in the base layout,
  or switch to `<use href="/static/icons/sprite.svg#icon-close">` once served over HTTP.

### Loading states
HTMX's `.htmx-request` is styled on buttons (dimmed, "…" appended, no pointer), rows (`.rd-row`, upcoming
rows), panels (`.rd-panel`, `.rd-panel-section`: a progress line along the top edge), the afford result and
year cells (text turns muted, never below AA). Buttons that submit should also carry
`hx-disabled-elt="this"` so they are disabled while the request runs; the styling assumes it.
`today--loading.html` shows the upcoming panel loading with the skeleton fragment (`states/loading`).

## 3. Themes and tokens

- `:root` = light (required default). Dark is redefined under `@media (prefers-color-scheme: dark)` for
  `:root:not([data-theme="light"])`, and under `:root[data-theme="dark"]`. `data-theme="light"` forces light.
- Components use tokens only. Grid track widths used by tables are tokens too (`--track-*`, `--table-min-*`).
- Breakpoints are documented at the top of `tokens.css`: **md 48rem (768px)** switches phone chrome (bottom
  tab bar, stacked rows, bottom-sheet dialogs and menus) to desktop chrome; **lg 64rem (1024px)** enables
  two-column panels; content stops at 1280px. Works from 320px to 1920px.
- `theme.js` is a tiny classic script in `<head>` so the saved theme applies before first paint. Priority:
  `?theme=` in the URL (for review) › `localStorage["rd-theme"]` › system. The server could equally set
  `data-theme` from a cookie.

## 4. Values the server sets at runtime

CSP blocks inline `style=""`, so runtime values arrive as **attributes or classes**, never inline styles:

| Value | How | Notes |
|---|---|---|
| Category colour | `data-color="<preset>"` on `.rd-chip`, `.rd-chip-option`, `.rd-swatch`, `.rd-swatch-dot` | Presets live in `components/category-colors.css` and define two properties: `--cat` (the hue) and `--cat-edge` (light-theme outline). Omit `data-color` for the neutral default grey. |
| A hue outside the presets | emit a nonce'd `<style>` rule: `[data-color="c-42"]{--cat:#123456;--cat-edge:#0f2a3d}` | `--cat-edge` = the hue's RGB scaled down until it holds 3:1 on `--color-panel` (`#faf7f3`). |
| Budget / share bars | the server renders the block characters (█ ▒ ░) in spans: `.rd-bar__left` (░ left), `.rd-bar__rest` (share remainder) | 20 cells wide, 10 in table rows and on phone. `.rd-bar--over`, `.rd-bar--none` colour the whole bar. |
| Year-grid cell state | `data-state="default|recurring|one-off|unset|editing"` on `.rd-year-cell` | the glyph (↻ • –) is part of the text. |
| Current month | `aria-current="date"` on the month header | |
| Chart geometry | the server writes the SVG paths/points (see `charts/`) | colours come from classes only. |
| Selection state | `aria-current`, `aria-pressed`, `aria-selected`, `checked`, `data-state` | never a styling class. |
| Hero figure fit | `data-digits`, `data-marks`, `data-signs` on `.rd-hero__figure` | glyph counts of the figure: digits, `,`/`.`, and `−`/`+`. Below the 390px boards the figure shrinks to fit its bake field on one line (container query); at 390px and up the mockup sizes apply unchanged. One small Jinja filter computes them. |

Chip rule: dark = hue at 20% fill + 60% outline; light = hue at 30% fill + `--cat-edge` outline; label is
always ink. Every light edge shown on the light boards (21 hues) is copied exactly; hues that never appear on a
board are computed with the same rule. The neutral (`data-color="grey"`, or no `data-color`: Reconciliation,
uncategorised) follows `--color-ink-muted` in both themes, as the boards do.

## 5. JavaScript

One file per behaviour in `static/js/`, all event-delegated on `document` and re-initialised on `htmx:load`
where they keep per-element state. No dependencies, no `innerHTML`, no `eval`, no data fetching, no number or
date formatting.

| File | Behaviour |
|---|---|
| `dialog.js` | opens modals in `#modal-root` with `showModal()`, `[data-js="dialog-close"]`, backdrop click closes, focus returns to the opener |
| `row-menu.js` | row action menus on the native `popover` attribute: positions under the trigger ≥768px (bottom action sheet below), ↑/↓/Home/End, closes on pick, opens `[popover][data-open]` (state pages) |
| `palette.js` | Ctrl K / ⌘ K command palette: filter, ↑/↓, Enter runs `data-href` |
| `shortcuts.js` | `g o/l/p/a/s`, `n`, `/`, `[` `]`, `?` — targets are declared in markup with `aria-keyshortcuts` |
| `combobox.js` | category picker: open, type to filter the list in the DOM, ↑/↓, Enter picks, Esc closes |
| `formula.js` | formula components: add / remove (✕ hidden while one), multi-select categories, re-index field names |
| `amount-input.js` | decimal keypad (`inputmode`), right-aligned, filters non-numeric keystrokes, selects on focus |
| `bulk-select.js` | ledger row selection: checkbox column appears when something is selected, Shift-click range, `x` toggles the focused row, bulk bar with count |
| `segmented.js` | `aria-pressed` button groups |
| `expand.js` | recurring rows' formula/overrides disclosure |
| `filters.js` | phone "filters" toggle on the ledger filter bar |
| `toast.js` | undo toast auto-dismiss after 8 s (pauses on hover/focus), flash dismiss |
| `theme-switch.js` | Settings › Preferences theme (system · light · dark), per browser |
| `theme.js` | classic `<head>` script, applies the saved theme before paint |
| `reveal.js` | dependent form sections: `data-show-when="amount_mode=formula"` shows a part only while the named control has that value (space = and, `\|` = or); hidden parts are disabled so they don't submit. Used for fixed vs formula amounts, the Transit destination account and the liability warning. |
| `stand-in.js` | **static stand-in for the server: delete it when you wire the templates to FastAPI + HTMX.** See §5a. |

Keyboard map (from the cheatsheet board): `g o` Today, `g l` Ledger, `g p` Plan, `g a` Accounts, `g s` Settings,
`n` new entry, `/` search/filter, `[` `]` cycle tabs, `?` cheatsheet, `⌘K`/`Ctrl K` palette, `Esc` closes.
Note: the board uses **`g o`** (not `g t`) for Today.

### 5a. How the controls are wired in the static files
Every control leads somewhere, so you can click through the whole app from `index.html`:

| Control | In these files | In the app |
|---|---|---|
| Opens a dialog (row menu items, promote, override, edit, reconcile, + new …, year cells, archive) | a link to the dialog's state page in `pages/overlays/` | `hx-get` into `#modal-root` |
| Closing, cancelling or saving a dialog | `stand-in.js` returns to the page you came from; saving shows the "● Saved" flash there | the POST response swaps the changed row and adds `flash/success` out of band |
| Delete, skip, skip next, restore, bulk actions | `stand-in.js` hides the row and shows the undo toast (`data-js="demo-action"`) | `hx-post` / `hx-delete`, response = row removal + `toast/undo` |
| Period ← → and the period picker | links to the same view with `?period=YYYY-MM` / `?year=YYYY` | `hx-get` + `hx-push-url` |
| Pagination, error-page buttons, clear filters, show all | links | links |
| Sign in / out, re-authenticate | `data-demo-next` on the form takes you to the next page | form POST + redirect |
| Settings forms, promote all due | `data-demo-flash` shows the success flash | form POST |
| Add user, reset password | `data-demo-next` on the dialog form goes on to the one-time password dialog | POST, response = the one-time password dialog |
| Invite, delete user, revoke invite, promote, delete account | `data-demo-toast` (+ `data-demo-undo`) on the dialog form shows the toast on the page you return to | POST, response = row swap + `toast` out of band |
| Export csv / parquet, copy link, resend invite, copy password | `data-js="demo-action"` toasts | a download link / `hx-post` + `toast` |
| Analytics category rows, "view 84 transactions", "view recurring rules" | links with `?category=` / `?account=`; `filters.js` preselects the filter | the server renders the filtered ledger |
| Upcoming range (7 days · 30 days · all), forecast horizon, analytics range | toggle their pressed state only: the new numbers have to come from the server | `hx-get` of the list / chart fragment |

`stand-in.js` only touches `action="#"` forms and `data-demo*` / `data-js="demo-action"` controls, so you can
delete it (and those attributes) view by view as you wire each one.

## 6. Deviations from the spec (please read)

1. **Scripts load with `defer`, not `type="module"`.** Chrome blocks module scripts on `file://` (CORS, origin
   `null`), which would fail acceptance check 1. The files contain no `import`/`export`, so you can switch every
   tag to `<script type="module" src="…">` as-is once they're served from `/static/`.
2. **Inline sprite copy per page**, for the same `file://` reason (see §2).
3. **stylelint:** `stylelint-config-standard`'s default `selector-class-pattern` is kebab-case only, which
   rejects the BEM classes the spec asks for (`rd-card__title`, `rd-btn--primary`). `.stylelintrc.json` extends
   the standard config and only overrides that one rule with a BEM pattern. Everything else passes as standard.
   Media queries use range syntax (`(width >= 48rem)`): that is the standard config's required form of
   `min-width`, still mobile-first.
4. **Menus are popovers, not `<details>`**, so they can become a bottom action sheet on phone with the native
   backdrop and light-dismiss.
5. **Date inputs are `type="date"`** (value `2026-10-31`, the spec's input format). The browser shows them in
   its locale; the mockups' `dd/mm/yyyy` appears only where the browser locale uses it.
6. **Glyphs not in Geist Mono** (⋮ ✕ ⌕ ✓ ⇄ ↻ ◇ ⌘) fell back to a system font in the mockups. UI icons
   (⋮, ✕, ⌕) are sprite icons here; data glyphs that the server emits as text (⇄ ↻ ✓) still use the system
   fallback, as in the mockups.
7. **Bulk selection has no visible control in the mockups.** The checkbox column stays hidden until a box is
   checked (reach it with Tab, or press `x` on a row), then the column and the bulk bar appear. If you'd rather
   have a visible "select" entry point, it needs a design decision.
8. **Copy that differs between phone and desktop boards** (e.g. "7 days until next income (Salary, 7 nov)" vs
   "7 days until salary (7 nov)") is rendered twice with `u-hide-below-md` / `u-hide-from-md`. It's short label
   text only; all structural markup is shared.
9. **Phone dialogs** are the same `<dialog>`s: below 768px they dock to the bottom as sheets, `cancel` is hidden
   (the ✕ and the scrim cancel), the primary button fills the row, as on the "New entry · phone sheet" board.
10. **The Plan period control** keeps the Plan page's look (separate ←, label, → buttons) and opens the period
    picker popover from the "Period picker" board.
11. **320px boards.** The 320 boards are the 390 layouts squeezed, and in them the hero figures run out of the
    bake field and get clipped. Here the figure shrinks to fit instead (see "Hero figure fit" in §4), and the
    phone header keeps `settings` and `sign out` on one line while the brand wraps, as on the boards.
12. **Contrast fixes.** The key hints in the command palette and the direction hints in the category picker are
    muted grey on the highlighted row in the boards (4.1:1 in dark, below AA). On the highlighted row only they
    turn ink. Everywhere else the colours are exactly the boards'.
13. **Phone list rows** (Today › Upcoming, Ledger › planned, recurring, recently deleted) don't follow the phone
    boards' left-stacked layout. Following your review, the right edge now carries the amount, the row menu and
    the row's main action (promote, expand, restore) on every line, so rows read as two aligned columns.
    Ledger › actual and Accounts keep the board layout.
14. **Chart tooltips** appear on hover and keyboard focus only. The boards show one tooltip open to illustrate it.
15. **Phone category picker.** Below 768px the open picker is its own bottom sheet with a scrim, as on the
    "Phone action sheets · category picker sheet" board. On desktop it stays the anchored dropdown.
16. **Export on phone.** The phone ledger board has no `export ▾`; it is kept on phone, wrapping onto its own
    line under the tabs. Hide it below 768px (`.rd-ledger-head__export`) if export should be desktop only.
17. **Delete account · confirm** shows *Investments E* as on its board, but the demo account list has no
    Investments E, so that state opens from `index.html` only.

### Items in the spec's inventory with no board (derived from the design system)
- **Errors 409 and 422**: same card as 404/500; 422 includes the form error summary fragment.
- **Edit planned entry**, **repeats · fixed amount** in New entry,
  **inline year-grid cell editor**, **flash success**, **form error summary**, **validation states** for
  Settings › Security and New category (duplicate name, using the message from the dev note).
- **Promote inline row variant**: not drawn; the row's `promote` button opens the promote dialog
  (`overlays/promote--planned.html`). Worth a quick design decision if an inline variant is still wanted.
- **Re-authenticate · no error** and **Sign in · no error** derived from their error boards.

## 7. Accessibility notes
- Real `<table>`s for tabular data. Rows lay out with CSS grid so phone and desktop share one markup.
- Every input has a `<label for>`; errors use `aria-invalid="true"` + `aria-describedby`.
- Dialogs are native `<dialog>` (focus trap and Esc for free); confirms use `role="alertdialog"`.
- Bars are `role="img"` with an `aria-label` ("78 percent spent, 15 percent left").
- Chart points are focusable `<g tabindex="0">` with labels; tooltips appear on hover and focus.
- Touch targets are 44px or more. Focus ring: 2px ink, ink-deep on the bake field.
- Motion animates only `transform` and `opacity`; `prefers-reduced-motion` turns it off.

## 8. Checks we ran (results at delivery)
- **Visual comparison with every board**, light and dark: each page and overlay was screenshotted at the
  board's width (1440, 560-wide dialogs, 390 and 320 for the phone boards) in both themes and compared with
  the board. Phone layouts of screens that only have a desktop board were checked at 390 and 320 too.
- W3C Nu validator (`vnu.jar --errors-only`) on all 114 HTML files: **0 errors**, no duplicate ids.
- `stylelint` with `.stylelintrc.json` (standard + BEM pattern): **0 problems**.
- **Wiring:** a script clicked every distinct link, button, menu item and option on every page and in every
  dialog and checked that each one navigates, opens or closes something, or changes state. The only controls
  that change nothing are links to the page you're already on and submit buttons blocked by required fields.
- Playwright, Chromium, opened from `file://`: every file at 320 / 375 / 768 / 1024 / 1440 / 1920px:
  **no horizontal page scroll, no console errors, no requests outside the folder.**
- axe-core 4 on every file, light and dark, at 375 and 1440px: **0 serious or critical issues.** The two
  ASCII loaf drawings (`.rd-empty__loaf`, `.rd-auth__loaf`) are excluded from the colour-contrast check: they
  are `aria-hidden` decoration drawn in the design's faint rule colour, which WCAG 1.4.3 exempts as pure
  decoration (axe can't tell, so it flags them). Use
  `axe.run({ exclude: [[".rd-empty__loaf"], [".rd-auth__loaf"]] })` in your CI to match.
- Table scroll wrappers are `tabindex="0" role="region"` with a label, so they can be scrolled by keyboard.
- Gzipped budgets (all files of each kind together): **CSS 23 kB** (budget 50), **JS 11 kB** (budget 30),
  **fonts 60 kB** (budget 250).
- Not run here: Firefox and Safari (only Chromium is available in our environment). The CSS relies on
  `:has()`, `color-mix()`, popover and `<dialog>`, which are in the latest two versions of all three.

## 9. Fonts
`static/fonts/`: **Unbounded 700** (latin + latin-ext A split by `unicode-range`) and **Geist Mono variable
400–500** (latin, latin-ext A, arrows, box drawing and block elements for the bars). Both SIL OFL 1.1, which
permits self-hosting; licences are next to the files. Total ≈ 60 kB.
