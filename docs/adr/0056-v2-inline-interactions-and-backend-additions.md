# ADR-0056: v2 Rising Dough — Inline Interactions, Live Previews, and Backend Additions

- **Status**: Accepted (2026-11-21; implemented, was Proposed)
- **Date**: 2026-10-28
- **Related**: ADR-0026 (FAB visibility), ADR-0030 (shared form primitives), ADR-0038 (recurring standalone lifecycle), ADR-0041 (budget period anchor window), ADR-0048 (category colour), ADR-0051 (new IA), ADR-0053 (component system)

## Context

The handoff interactions (`docs/application_redesign_handoff/docs/05-interactions.md`) are server-rendered HTMX fragments with one exception: popover state and formula term state (vanilla or Alpine). Several require small new backend endpoints — "can I afford" live preview, formula term preview, batch promote-due, analytics bundle, category archive. This ADR locks each one.

## Decision

### 1. Promote-in-place (replaces the Phase 11 promote modal for Upcoming + Ledger)

- Focus a row (↑ ↓), press `↵` or click **Promote**. The row expands in place to show editable account / date / amount + Confirm / Cancel.
- `GET /recurring/{id}/promote-form` and `GET /planned/{id}/promote-form` return the expanded row fragment.
- Confirm POSTs to the existing promote endpoints; on 2xx the row collapses, hero figures recompute via `HX-Trigger: budget-stale, ledger-stale`.
- Esc cancels — the row collapses without a server call.
- `⇧↵` on a row with any due-today/overdue items triggers `POST /recurring/batch/promote-due` + `POST /planned/batch/promote-due` (new; see §6).

### 2. Cell edit popover (Plan · Year)

- Click (or arrow-to + ↵) a cell. A popover opens anchored to the cell with: amount input, radio `One-off {month YYYY} / Every year · {month}`, Save / Reset to default.
- `GET /plan/year/cell/{category_id}/{year}/{month}/edit` returns the popover fragment.
- Save POSTs to the existing one-off or recurring override endpoints.
- Popover state (open / anchor / focus trap) lives in a small Alpine.js component (`static/js/popover.js`, ~60 lines). CSS Anchor Positioning used where available (Chrome 125+); fallback is `getBoundingClientRect` positioning.

### 3. "Can I afford it?" live preview

- Today page has an amount input. On `keyup changed delay:200ms` HTMX hits `GET /today/afford?amount=<minor_units>`.
- Returns `{"per_day_minor": 15123, "delta_minor": -4567, "pace_tag": "On track"}` as a tiny JSON — rendered by a Jinja fragment response (HTMX swaps the per-day caption + delta text).
- **Server is source of truth**: minor-unit arithmetic + anchor window computed server-side per `services.budget.month_summary` + ADR-0041.
- No DB write.

### 4. Formula term live preview

- Add-entry formula form (`web/templates/transactions/_recurring_formula_form.html`) rebuilds the term list client-side. On any change, HTMX POSTs the current term shape to `POST /recurring/formula/preview` (idempotent, no write).
- Response: `{"amount_minor": 123400, "errors": [...]}` on success, 422 with inline error on cycle / non-positive / invalid source.
- Live preview rendered next to the ƒ chip.

### 5. Reconcile slide-over step shape

Unchanged mechanics (ADR-0011) with a reskinned flow:

- Step 1: "Open your bank" (static copy).
- Step 2: "Enter the balance" (input).
- Step 3: "Review" — shows app vs bank balance, the difference, and a **Record as** category combobox (defaults to the system "Reconciliation" category). Primary button states the signed amount: `Record −28.90`.
- No new endpoint; the existing reconcile POST handles the signed adjustment.

### 6. Backend additions

The design implies six new / amended endpoints. Each follows router → service → repository → SQL and reuses existing primitives.

| Endpoint | Service | Purpose |
|---|---|---|
| `GET /today/afford?amount=` | `services.today.afford(amount_minor)` | Returns recomputed left-per-day + delta + pace tag. Pure function over `month_summary`. |
| `POST /recurring/formula/preview` | `services.recurring.formula.preview(terms)` | Computes value for a draft term list without persisting. Cycle / non-positive validation. |
| `GET /accounts/last-checked` | `services.accounts.last_checked()` | Latest snapshot or reconcile date per account. Powers Accounts table "last checked" column. |
| `GET /plan/analytics` | `services.analytics.bundle(period)` | Returns spend-by-category + 12-month averages + income-vs-expense + largest items. Replaces Plotly-backed `/analytics`. |
| `POST /categories/{id}/archive` + `POST /categories/{id}/restore` | `services.categories.archive(id)` / `restore(id)` | Soft-delete + restore for categories via the existing repository helper. |
| `POST /recurring/batch/promote-due` + `POST /planned/batch/promote-due` | `services.{recurring,planned}.batch_promote_due()` | Promote every rule / planned row due today or overdue, within one transaction. Returns summary for the Undo toast. |

All new endpoints emit the right `HX-Trigger` events (`budget-stale`, `ledger-stale`, `forecast-stale`, `accounts-stale`) so existing Phase 11 listeners refresh.

### 7. View Transitions

Where supported (`document.startViewTransition`), promote-in-place and tab changes within Plan use `hx-swap="... transition:true"` so the collapsing row and the spent-amount flight read as one motion. `prefers-reduced-motion` disables.

### 8. Quick-add relocation

- The floating `+ Add` FAB (ADR-0026) is retired.
- Desktop: `+ Add` lives in the top bar as the right-most control. Keyboard: `n` opens the Add modal regardless of focus (standard input-guard preserved).
- Mobile: `+ Add` is the centre tab (ADR-0055 §2) and opens the bottom sheet.
- ADR-0026 is amended: "none planned in v1" sentence is historical; the FAB is removed in v2.

### 9. Overlay stack

Multiple overlays can co-exist (promote-in-place row + popover + modal). The Esc handler stays single-stack (`static/js/overlay-stack.js`) and only the top-most overlay reacts.

## Consequences

### Positive

- Promote-in-place is one keystroke (`↵`) instead of a modal open + submit + close.
- "Can I afford it?" is a server-of-truth preview — no client duplication of the paycheck-window math.
- Six new endpoints are small, pure, and testable; none introduce new persistence tables.
- The FAB-removal unlocks table content on narrow viewports without redesigning the mobile shell.

### Negative / costs

- Live previews add request pressure (one request per 200 ms during typing). Mitigated by server-side pure functions and HTMX's built-in debounce.
- Alpine.js adds ~15 kB over the HTMX baseline for popover state. Imported only on pages that use popovers (Plan · Year, Add formula form).
- View Transitions degrade gracefully on Firefox / Safari; feature detection in the base template.

### Follow-ups

- A later ADR may replace Alpine with native CSS Anchor Positioning + Popover API when Safari support crosses the 95% threshold.
- A later ADR may add the command palette (`⌘K`); kept as a design reference only for v2 (handoff screen 1m).

## Amendment 2026-11-21 (T-Q244, Q-050)

The section 4 live formula preview endpoint `POST /recurring/formula/preview` (and its partial) had no caller since the unified entry form (ADR-0060) and was deleted, with `GET /accounts/last-checked`, `GET /plan/analytics`, `POST /budget/recurring/{category_id}/{month}`, `POST /recurring/batch/promote-due` and `POST /recurring/batch/undo`. `services/recurring_formula.preview` remains for a future re-wire in the ADR-0107 redesign.

### Amendment 2026-11-22 (SYNC-MAIN): formula preview route restored

The ui-test-harness work (T-UT12-3) wired the recurring form to `POST /recurring/formula/preview` again (`rd-formula-change` trigger in `partials/recurring/_form.html`), so the route deleted by T-Q244 has a caller. It is restored with its partial `partials/recurring/_formula_preview.html` and integration test; the other five T-Q244 deletions stand.
