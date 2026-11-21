# ADR-0026: Quick-add FAB visibility scope

- **Status**: Accepted
- **Date**: 2026-10-27
- **Related**: ADR-0023 (UX redesign — IA + interaction model)
- **Supersedes**: nothing (narrows ADR-0023 affordance #4 only)

## Context

ADR-0023 introduced a context-aware quick-add FAB (affordance #4). The implementation (`T-069`) wires it into `base.html` unconditionally and routes via `fab_target_for(request)`, so the FAB appears on every page. Field use (Phase 8 observation report, 2026-10-27) surfaced two problems:

1. On Accounts, Budget, Settings, Forecast, and Analytics the FAB offers `+ Transaction`, which is almost never the correct next action from those surfaces. It competes visually with the real primary action on the page (e.g. `+ New account`, inline rule edit, settings tab change).
2. On Budget specifically, users read the floating `+` as "add a budget rule", but the rules table enumerates every category inline — there is nothing to create.

The underlying IA decision is unchanged: four nav items + Settings drawer, Ledger-unified entity, Overview three-panel composition. Only the FAB visibility rule needs narrowing.

## Decision

The quick-add FAB is rendered **only** on surfaces where "add a money event" is the primary user intent:

| Surface | FAB target | Rationale |
|---|---|---|
| `/` (Overview) | `/transactions/new` | Primary intent on the dashboard is "I just spent money, log it." |
| `/ledger` (any view) | view-aware: `/transactions/new`, `/planned/new`, `/recurring/new` | Ledger is the money-event surface; FAB mirrors the active segment. |
| `/accounts` | hidden | Primary action is `+ New account`, already present in the page header. |
| `/budget` | hidden | Rules are per-category and already enumerated; there is no missing endpoint. |
| `/settings` and sub-pages | hidden | Administrative surface; no money-event affordance belongs here. |
| `/forecast`, `/analytics` | hidden | Read-only or chart-first surfaces. |

Implementation: `fab_target_for(request)` returns `str | None`. `base.html` wraps the FAB include in `{% if fab_target_for(request) %}`.

The `n` keyboard shortcut (`shortcuts.js`) is unchanged — it clicks the FAB when present and falls back to the command palette otherwise. On surfaces without a FAB the fallback is the correct behaviour (the palette has every create action).

Budget rules discoverability is improved by copy, not by a new FAB target: the Rules section header gains a one-line hint explaining the inline-edit model and the three-tier resolution. No new endpoint, no new slide-over.

## Consequences

### Pros

- One primary action per surface. The FAB is quiet where it has no purpose.
- No new routes, no new endpoints, no change to the services layer.
- ADR-0023 intent preserved: quick-add remains the fast path for the surfaces where money events live.
- Keyboard parity is maintained via the palette fallback.

### Cons

- Users who memorised "`n` opens a transaction form from anywhere" now get a palette on non-money-event surfaces. Mitigation: the palette's first entry is still `New transaction`, so the Enter-key path is one extra keystroke, not a lost affordance.
- One more branch in `fab_target_for` to maintain. Low cost — a single allow-list in one module.

### Rejected alternatives

- **FAB target per surface** (e.g. `+ New account` on `/accounts`). Rejected: duplicates the surface's existing primary button and bloats `fab_target_for` with surface-specific knowledge the context helper should not own.
- **`+ Rule` endpoint on Budget**. Rejected: rules are per-category; the enumeration is already exhaustive. Adding a slide-over to pick a category + tier re-invents the existing inline inputs.
- **FAB only on `/ledger`**. Rejected: Overview is the landing page and "I just spent money" is a dominant intent on arrival — demoting the FAB there slows the most common action.

## Follow-ups

- Prune `data-add-kind` placeholder attributes (e.g. `+ Planned` on Overview Upcoming panel) once T-093 wires them directly to the correct slide-over endpoint.
- Revisit if a future phase introduces a surface where "add" is ambiguous (none planned in v1, v2, or v3). Note: v2 (Rising Dough) retires the FAB in favour of a top-bar `+ Add` button; this ADR's rationale is historical.

## Addendum 2026-11-21: FAB removed

`fab_target_for(request)` and the quick-add FAB no longer exist in `src/` (replaced by the Rising Dough navigation, ADR-0051). This ADR is historical for the FAB; ADR-0028 names the same helper and is likewise historical on that point. Quality-audit finding Q-052.
