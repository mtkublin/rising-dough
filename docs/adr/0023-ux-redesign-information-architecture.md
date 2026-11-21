# ADR-0023: UX Redesign — Information Architecture Consolidation + Interaction Model

- **Status**: Accepted
- **Date**: 2026-10-25
- **Related**: ADR-0002 (web stack), ADR-0021 (functional style), ADR-0022 (repository discipline)
- **Supersedes**: nothing

## Context

Phase 5 landed the token layer and the editorial/Swiss direction (T-053) but kept Phase 3's nine top-level routes as nine top-level nav items. Nine tabs for a single-user, local-first budget app is admin-shaped, not app-shaped. Users must pick a tab before they pick a job; three of the tabs (Transactions / Planned / Recurring) are the same entity shown three ways; three more (Home / Forecast / Analytics) all answer "how am I doing?" from different angles.

We need an information architecture that

- maps nav items to user jobs rather than entity names,
- collapses the three "money event" surfaces onto one surface so the user can compare and act without context-switching, and
- keeps every v1 feature. No regressions, no deferral.

Everything stays inside the ADR-0002 web stack (FastAPI + Jinja + HTMX + Tailwind CDN + Plotly) and the ADR-0021 functional style.

## Decision

### 1. Reduce nav from 9 top-level items to 4 + a Settings drawer

| Nav item | URL | Collapses | Job |
|---|---|---|---|
| Overview | `/` | Home + headline forecast link | How am I doing right now? |
| Ledger | `/ledger` | Transactions + Planned + Recurring | Record and reconcile money events |
| Accounts | `/accounts` | unchanged | What's where, does it match reality? |
| Budget | `/budget` | Budget + Analytics breakdown | Am I inside my plan, where is money going? |
| Settings (drawer, not a tab) | `/settings?tab=…` | Categories + FX cache + Preferences | Admin-shaped surfaces live here |

`/forecast` is retained as a non-tab deep page, linked from the Overview budget panel and from Budget. `/analytics` is retained as a deprecated-but-live URL for one release, then pruned (Phase 7 cleanup task).

### 2. Overview composition is three panels, not five

Per the explicit v1 spec (2026-10-25): the dashboard shows (a) current account state for all accounts plus the summed fortune in base currency, (b) budget stats with `amount left` as the primary headline number, (c) upcoming planned payments with items where `planned_date >= today` rendered at full emphasis and items where `planned_date < today` (overdue, un-promoted) muted + italic. No forecast chart, no spend-by-category tiles on Overview — those live on `/forecast` and `/budget` respectively.

### 3. Ledger unifies three queries behind one segmented control

`/ledger` renders Actual | Planned | Recurring from one shell. Filter shape is shared across the three views. The three current fragment routes (`/transactions/table`, `/planned/table`, `/recurring` list) are aliased to one dispatch fragment `/ledger/table?view=…` for one release, then removed.

### 4. Add two interaction affordances on top of the IA

- **Command palette** (`⌘K` / `Ctrl K`) — small Alfred-style popover, implemented as a Jinja partial fetched by HTMX plus ~60 lines of vanilla JS, no framework.
- **Quick-add FAB** — fixed bottom-right, keyboard `n`, opens the transaction form in a slide-over. Context-aware against the active Ledger segmented tab.

### 5. Legacy URLs 302-redirect for one release

`/transactions`, `/planned`, `/recurring`, `/categories`, `/analytics` all return `302` to their new home. HTMX fragment routes are kept under their original paths as aliases. Flip to `301` once stable; remove in a Phase 7 cleanup task.

## Consequences

### Pros

- Nav halves (9 → 4), with every item a job the user actually does.
- Planned-vs-actual comparison becomes a one-click segmented toggle on the same filtered view rather than two separate pages.
- Overview answers the three questions a user opens the app for: *what do I have, what's left this month, what's coming up?*
- Settings being a drawer puts configuration out of the primary nav where it belongs for a single-user local app.
- Command palette + keyboard shortcuts turn a browser app into something closer to a native power tool, which matches the audience (one developer-shaped user).

### Cons / costs

- One release of 302 redirects for five old URLs (plus their fragment aliases). Low cost; integration-tested in T-070.
- Ledger must preserve the three current create / edit / delete flows under one shell — the templates are consolidated but the services and routers remain the Phase 3 ones. T-064 lays out the dispatch pattern.
- Command palette is net-new JS surface (~100 lines total across palette + shortcuts). Capped by scope in T-068; if it grows past ~150 lines, scope reduces to navigation-only.

### Explicit non-goals

- No dark mode. No mobile adaptive nav. No icon system. All three are new ADRs if desired, and all three are out of scope for v1.
- No change to data model, service signatures, repository functions, or ADRs 0003–0022. Pure web-layer refactor.
- No new third-party JS dependencies. HTMX + Plotly + Tailwind CDN remain the only client-side libraries.

## Alternatives Considered

- **3 tabs (Overview, Ledger, Accounts) with Budget absorbed into Overview** — rejected. Budget is a workflow (set rules, inspect breakdown), not a glance. Collapsing it loses the deep-dive surface where spend-vs-plan actually belongs.
- **5 tabs (keep Analytics as its own tab)** — rejected. The analytics figures are a *view* of budget data; they belong under Budget. A dedicated Analytics tab was Phase 3's "we don't know where to put the charts yet" placement.
- **Top horizontal nav instead of left rail** — rejected. The app is dense (money tables + numeric data). Left rail keeps the horizontal strip for page title + actions and gives the content column one axis of visual rhythm.
- **Command palette deferred to v2** — rejected. ~60 lines vanilla JS; big UX win for a keyboard-first audience. Low cost, high leverage.

## Addendum 2026-11-21: navigation and FAB drift

Section 1 (four nav items plus a Settings drawer) and the context-aware quick-add FAB (affordance #4) describe the Phase 6 design. The shipped navigation (Rising Dough, ADR-0050, ADR-0051) is Today, Ledger, Plan, Accounts plus Settings in the rail footer and a mobile tab bar; the FAB and `fab_target_for` no longer exist in `src/`. Quality-audit finding Q-052.
