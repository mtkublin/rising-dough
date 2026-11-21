# ADR-0054: v2 Rising Dough — Charts Move From Plotly to Server-Rendered SVG

- **Status**: Accepted (2026-11-21; implemented, was Proposed)
- **Date**: 2026-10-28
- **Related**: ADR-0002 (web stack — Plotly), ADR-0015 (forecast deterministic + live HTMX), ADR-0042 (forecast budget overlay), ADR-0043 (forecast monthly horizon + table), ADR-0050 (visual direction), ADR-0053 (component system)

## Context

ADR-0002 picked Plotly for charts. The handoff (`docs/application_redesign_handoff/docs/06-implementation-notes.md`) recommends replacing Plotly with Jinja-generated SVG for three reasons:

1. **Bundle size.** `plotly-basic.min.js` is ~2 MB over the wire; a bespoke SVG renderer is ~2 kB of Jinja + inline styles.
2. **On-brand.** Plotly's default stroke / fill / grid colours do not match the Rising Dough palette without extensive config, and config lives client-side where tokens are harder to reach.
3. **Accessibility.** A data-table fallback is required for every chart (`web/testing.md`). Jinja-rendered SVG makes rendering the table from the same data trivial; Plotly requires a separate code path.

The Forecast surface (ADR-0043) already renders a monthly breakdown *table* under the chart; the chart is the only remaining Plotly consumer along with Analytics.

## Decision

### 1. Replace Plotly on Forecast and Analytics

- Remove `plotly.js` from `static/vendor/`. Remove the `ForecastSeries.to_plotly_figure()` helper (if present) and the router-side Plotly JSON conversion.
- New helper module `src/budget_planner/web/charts.py` exposes pure functions that take domain series + layout hints and return pre-computed SVG geometry (points, path `d` strings, axis labels, grid lines). The functions are testable in isolation.
- Templates `templates/plan/_forecast_chart.html` and `templates/plan/_analytics_charts.html` consume the geometry and emit inline SVG.

### 2. Chart shapes

Three chart types cover v2:

| Chart | Shape | Where |
|---|---|---|
| **Monthly line + area** | SVG `<path>` with `d` for line + a second `d` with `L …` returning to baseline for area; one annotation `<text>` per outlier month (profit share, planned holiday). | Plan · Forecast. |
| **Grouped bars (income vs expense per month)** | SVG `<rect>` pairs per month; two colours (income + expense). | Plan · Analytics. |
| **Horizontal bar list (spend by category)** | SVG `<rect>` per category + inline label; delta vs 12-month average rendered as a small triangle. | Plan · Analytics. |

Each chart renders at **two breakpoints**: desktop and mobile (narrower aspect, fewer gridlines). Tablet reuses the desktop shape.

### 3. Data-table fallback

- Every chart template `<figure>` includes a `<details>` block containing the data table equivalent (ADR-0043 §F5.5 is already a table; its data is the same source).
- Charts gain `role="img"` + `aria-labelledby` pointing at a figcaption. The caption summarises the shape ("Monthly projected balance, Dec 2026 — Nov 2027").
- `prefers-reduced-motion` disables the hover tooltip transition only; the chart itself is static SVG and does not animate.

### 4. Interactive affordances (minimal)

- Hover tooltip: a small `<g>` positioned by CSS anchor positioning (or Alpine.js fallback for Safari < 17.4). The tooltip reads from `data-*` attributes on the hovered element.
- Click on a bar / point: navigates to a filtered Ledger view (Analytics only).
- No pan, zoom, legend-toggle. The data table replaces those affordances for keyboard users.

### 5. Routes

Chart rendering stays within the existing router endpoints:

- `GET /plan?tab=forecast` renders the full page.
- `GET /plan/forecast/chart?horizon=12` returns the SVG + table fragment (HTMX swap on horizon change).
- `GET /plan/analytics?period=…` renders the full tab.
- `GET /plan/analytics/charts?period=…` returns the three analytics charts as a fragment.

HTMX event names stay (`forecast-stale`, `analytics-stale`) so Phase 11 listeners keep working during the migration.

## Consequences

### Positive

- Removes 2 MB of JS from the critical path for every user who visits a chart page.
- Chart colour tokens come from `tokens.css` directly; no colour drift between chart and page.
- Playwright visual regression captures the exact pixels; no Plotly rendering flakiness.
- Accessibility story improves — screen readers get the data table, hover users get the SVG, keyboard users get the table rows that link to filtered Ledger views.

### Negative / costs

- `charts.py` has to compute axis labels, nice-rounded gridlines, and tooltip anchor positions by hand. Non-trivial but bounded; three chart shapes total.
- No built-in zoom / pan. Mitigated by the horizon selector (Forecast) and period selector (Analytics) — the UI exposes slicing instead of panning.
- Loss of Plotly's built-in CSV export of the plotted data. Already covered by the Forecast monthly table + Analytics table + v1 export surface.

### Follow-ups

- A later ADR may add CSV export of the chart's rendered data to the `<details>` fallback block.
- A later ADR may add a small `<canvas>` sparkline for the Accounts trend column; SVG works equally well and keeps the shape consistent.

## Alternatives Considered

- Keep Plotly and theme it — rejected; 2 MB bundle on a server-rendered app is the wrong tradeoff.
- Chart.js — ~70 kB, better than Plotly, still client-side JS. Rejected; the server already has the numbers, there is no reason to recompute them in JS.
- Pure CSS charts (bars-only via width %) — works for the bar lists but not for a monthly line + area. Mixed approaches hurt coherence.
- D3 — overkill; D3's power is interactivity we don't need.
