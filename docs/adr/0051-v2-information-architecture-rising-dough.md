# ADR-0051: v2 Rising Dough — Information Architecture (Today · Ledger · Plan · Accounts · Settings)

- **Status**: Accepted (2026-11-21; implemented, was Proposed)
- **Date**: 2026-10-28
- **Related**: ADR-0023 (prior IA consolidation), ADR-0028 (Ledger segmented control — full nav), ADR-0031 (Budget page composition v2), ADR-0038 (recurring standalone lifecycle)
- **Supersedes**: ADR-0023 §Information architecture — v1's Overview · Ledger · Accounts · Budget rail is replaced by Today · Ledger · Plan · Accounts; the Settings slide-over drawer is replaced by a Settings page pinned at the bottom.

## Context

v1 shipped four top-level items (Overview, Ledger, Accounts, Budget) plus a Settings drawer and a separate `/forecast` deep page. The design brief at `docs/application_redesign_handoff/docs/02-information-architecture.md` consolidates further: five surfaces, each answering one question.

- Overview tries to be "what's going on" but mixes a left-per-day metric with upcoming items and net worth. The handoff proposes **Today** — "left per day" is the hero; everything else supports that question.
- Budget and Forecast both answer "how will the period go". The handoff merges them under a **Plan** page with four tabs (Budget · Year · Forecast · Analytics) sharing the paycheck header.
- Settings earned a dedicated page: Categories needs room for colour and archive affordances, and the drawer pattern no longer fits.
- The floating `+ Add` FAB covered table content on narrow viewports; **+ Add** moves into the top bar on desktop and the centre tab on mobile.

## Decision

### 1. Rail (desktop ≥ 1100 px)

Four primary tabs + Settings pinned to the bottom:

| Order | Label | Route | Shortcut | Question answered |
|---|---|---|---|---|
| 1 | Today | `/today` | `g o` | "How am I doing *right now*? Can I afford this?" |
| 2 | Ledger | `/ledger?view=actual\|planned\|recurring` | `g l` | "What happened and what is lined up?" |
| 3 | Plan | `/plan?tab=budget\|year\|forecast\|analytics` | `g p` | "How will this period / year go? Where does the money fall?" |
| 4 | Accounts | `/accounts` | `g a` | "What do I own and owe?" |
| ↳ | Settings | `/settings?tab=categories\|fx\|prefs` | `g s` | "How is this app configured?" |

`g b` and `g f` continue to resolve as aliases for `/plan?tab=budget` and `/plan?tab=forecast` for one release.

### 2. Legacy route redirects

v1 URLs are preserved for one release via 302:

| v1 URL | 302 target |
|---|---|
| `/` | `/today` |
| `/overview` (unused) | `/today` |
| `/budget` | `/plan?tab=budget` |
| `/budget/yearly` | `/plan?tab=year` |
| `/forecast` + `/forecast/view` | `/plan?tab=forecast` |
| `/analytics` | `/plan?tab=analytics` |
| `/categories` | `/settings?tab=categories` |
| `/transactions` | `/ledger?view=actual` |
| `/planned` | `/ledger?view=planned` |
| `/recurring` | `/ledger?view=recurring` |

The 302 shim is removed one release after v2 ships (tracked as a Phase 7 cleanup in the v2 plan).

### 3. Today (replaces Overview)

- **Hero**: left-per-day figure (reuses `MonthSummary.left_daily_spend_minor`, ADR-0041 paycheck window), pace tag (On track / Tight / N overdue), segmented bar `spent | committed | left`, period one-liner "Period 15 Oct → 7 Nov · day 14 of 24".
- **Can I afford it?** amount input → `GET /today/afford?amount=` returns the recomputed per-day figure; debounced live preview, server is source of truth for minor units.
- **Net worth card**: total, assets, liabilities, six largest balances, links to Accounts and Plan · Forecast.
- **Upcoming**: segmented 7 / 30 days / All. The sorted union of planned one-offs + active recurring rules per `services.upcoming.list_upcoming(window)` (ADR-0038). Row: date, name + account (+ ƒ for formula rules), category pill, signed amount, `Promote / Skip / Override`. Promote expands the row in place (no modal).

### 4. Ledger

Unchanged shell shape from ADR-0028 (full-nav segmented control). Tabs: **Actual · Planned · Recurring**, each with its row shape per the handoff:

- Actual: rows grouped by day; filter chips for date / category / account / direction / search.
- Planned: columns = due · description + account · category · amount · status · actions.
- Recurring: grouped by Monthly / Yearly; chevron expands to show the overrides list + (for formula rules) the derivation.

Bulk actions and export surface as a toolbar when rows are selected.

### 5. Plan (new, four tabs)

Shared paycheck period header across all four tabs. Tabs:

- **Budget** — current period, Rules table (per-category planned / actual / used bar / remaining / ⋯).
- **Year** — year grid heatmap; cell colour intensity scales with amount (sqrt, capped at 1,600); tier markers for one-off / recurring / default / unset.
- **Forecast** — horizon 6 / 12 / 24 / 60 months, Jinja-rendered SVG chart + monthly table (reuses the F5.5 shape).
- **Analytics** — month / 3 months / YTD / 12 months; spend by category with delta vs 12-month average; income vs expense bars; largest single items.

### 6. Accounts

Columns: name + type · trend sparkline · last-checked status (warning tag if stale) · transaction count · balance · Reconcile. Liability rows show `limit / available / used` bar. Edit / Snapshot / Delete collapse into a ⋯ menu.

### 7. Settings (now a page)

`/settings?tab=categories|fx|prefs` returns the full page shell. Tabs:

- **Categories** — expense / income / system groups; row = pill + direction badge + colour source + Edit / Archive. Archived categories are restorable. System rows locked. Income-anchor selector is the first control on this tab (shifted from Preferences for discoverability).
- **Currency & FX** — base currency + display timezone + cached FX rates (read-only in v2; editing stays deferred).
- **Preferences** — all other per-user prefs; the income-anchor affordance here is a mirror link to the Categories control.

### 8. Settings slide-over drawer retired

The `/settings` fragment response that returned the drawer HTML is replaced by the full page. `#drawer-root` is removed from the base template; the `g s` shortcut navigates instead of injecting.

## Consequences

### Positive

- Four tabs instead of five + a drawer. Each tab answers one question; the brief's five-surfaces-one-question-each principle is enforceable by review.
- Budget / Forecast / Analytics share a paycheck header — context jumps across tabs stay anchored.
- Settings earns room for Category colour, archive, income anchor — all of which fit a page better than a 480 px drawer.
- The retired FAB stops covering table content on narrow viewports.

### Negative / costs

- All existing templates referencing the old IA (base shell, nav, drawer wiring) move. Every integration test that opens Settings as a drawer must switch to a page nav assertion.
- Legacy 302s add a request on every bookmarked URL for one release. Acceptable.
- The move from Overview to Today changes the default landing page and will churn muscle memory on `g o`; aliasing avoids breakage.

## Alternatives Considered

- Keep Overview and add a "Today" tab — rejected; Today *is* the overview with a better name and tighter scope.
- Keep Budget and Forecast as separate top-level pages — rejected; the brief's framing is "they share a question", merging the paycheck header saves rebuilds.
- Make Settings a modal — rejected; Categories list + colour swatches + archive affordances need more vertical room than a modal reasonably provides.
- Collapse Analytics into Ledger — rejected; Analytics is a reading surface, Ledger is a listing surface. Keeping them apart matches user intent.
