# ADR-0043: Forecast Surface — Monthly Horizon + Breakdown Table

- **Status**: Accepted
- **Date**: 2026-10-27
- **Amends**: [ADR-0015](0015-forecast-deterministic-live-htmx.md) (Forecasting — Deterministic Projection)

## Context

ADR-0015 defined a daily deterministic projection with a user-selectable horizon. In practice:

1. Users think about forecast runway in **months / years**, not days.
2. The 365-day cap excluded multi-year planning scenarios (loan payoff windows, savings goals).
3. The chart alone omits the detail users actually need to act on — the per-month income / planned-expense / net breakdown that drives the EOM balance curve.

## Decision

### 1. Horizon unit becomes **months**

- Primary input renamed `horizon_months` (default **12**, min **1**, max **60**).
- Service still projects daily under the hood (ADR-0015 invariant preserved); the router expands months → days (`horizon_days = end_of_month_offset_from_today`).
- Legacy `horizon_days` query param is removed; this is a v1 UI change, no persisted state depends on it.

### 2. New monthly aggregation API

`services.forecast.forecast_monthly(conn, http, today, horizon_months, base_currency) -> MonthlySeries`

Per month in `[today.month, today.month + horizon_months - 1]` returns:

- `month` (first-of-month `date`)
- `income_base_minor` — sum of signed income events landing in the month (base currency)
- `expense_base_minor` — for the **current calendar-month row**, `totals.committed_minor` from `services.budget.month_summary` (anchor-window `[today, next_income_date)`, ADR-0041). For **future rows**, sum of (absolute) expense events landing in that calendar month.
- `planned_budget_base_minor` — for the **current calendar-month row**, `max(totals.remaining_minor, 0)` from the same `month_summary` call so the Forecast table lines up with the Budget page's "remaining" and the Overview panel's "committed (recurring + planned)" math. For **future rows**, `Σ max(resolve_budget(cat, m) − spent_so_far(cat, m) − committed_future(cat, m), 0)` across live expense categories (ADR-0042 math).
- `net_base_minor` — `income - expense - planned_budget`
- `end_balance_base_minor` — projected total fortune at end of month, computed by `forecast()` with the ADR-0042 **budget overlay enabled**, so the current-month row absorbs both the remaining planned events and the synthetic residual-budget spend distributed across the rest of the horizon.

Transits net to zero across accounts and are excluded from income / expense totals. Adjustments are not emitted by the forecast engine (planned adjustments unsupported, ADR-0011).

Budget-period consumption boundaries (ADR-0041) are approximated with calendar months here — matching ADR-0042 overlay semantics. Fiscal-period redefinition (anchor-income cycle) is tracked separately.

The daily `forecast()` function remains the primary driver; `forecast_monthly()` composes over its daily output + raw event stream — one DB pass per request.

### 3. Forecast tab is promoted into the rail nav

Previously the `/forecast` route was reachable only by URL. It becomes a first-class nav entry (`g f` shortcut), placed after Budget.

### 4. Page composition

```
Forecast
  ├─ Horizon control (number input, unit = months)
  ├─ Chart (monthly granularity — one EOM point per month, overlay-on)
  └─ Monthly table
       Month · Income · Expenses · Planned budget · Net · Projected balance (EOM)
```

Chart X-axis renders one point per month (`forecast_monthly.months`) with `mode: "lines+markers"` and `tickformat: "%b %Y"` — matches ADR-0042's monthly materialisation and the table's row granularity. Users wanting a per-day drilldown use the daily `forecast()` endpoint directly (not surfaced in the UI).

Table reuses `partials/forecast/_table.html`; both chart + table share the `#forecast-view` wrap so one HTMX swap updates both.

## Consequences

- Horizon math moves to the router boundary; service stays pure in days.
- Multi-year planning now fits — 60 months × ~31 days = ~1860 points per chart; still cheap (one pass through planned rows + rule expansion).
- Monthly table exposes the "why" behind the curve — users can see which month a dip comes from without hovering the chart.
- The `HX-Trigger: forecast-stale` contract (ADR-0015) still fires both chart + table since they share one swap target.

## Alternatives Considered

- **Keep days as the input, add a separate "months" preset dropdown**: double-input UX, no gain.
- **Push monthly aggregation into the template via Jinja grouping**: scattering domain math across layers, violates "fat services" (CLAUDE.md).
- **Compute monthly series client-side from the Plotly payload**: duplicates signed-leg logic in JS, DRY violation (same reasoning that killed client-side recompute in ADR-0015).

## Amendment 2026-11-25 (T-UR15a)

Per ADR-0051 and operator decision Q13, the horizon on `/plan?tab=forecast` is one of 6, 12, 24 or 60 months; any other value (including the former clamp values arriving through the `/forecast?horizon_months=` redirect) is a 422 instead of being clamped to 1..60.
