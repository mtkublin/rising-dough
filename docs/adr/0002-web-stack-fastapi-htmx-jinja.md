# ADR-0002: Web Stack — FastAPI + HTMX + Jinja2 + Tailwind (CDN) + Plotly

- **Status**: Accepted
- **Date**: 2026-10-23

## Context

The initial requirements call for a web application run locally, Python-preferred, with graphs and interactive views. Future deployment is possible.

## Decision

- **Backend**: FastAPI (Python 3.12).
- **Templating**: Jinja2 server-rendered templates.
- **Interactivity**: HTMX fragment swaps.
- **Styling**: Tailwind CSS via CDN (no node toolchain).
- **Charts**: Plotly (JSON embedded, rendered client-side via CDN script).

## Consequences

- Pure Python toolchain; no `node`/`npm`.
- Interactivity (filters, inline edit, live forecast) via HTMX attributes; no JS written.
- FastAPI gives async handlers, Pydantic validation, OpenAPI docs for free.
- Testable with `TestClient` + fragment assertions.
- A JS build step can be added later if Tailwind-CDN output becomes too large; low-risk migration.

## Alternatives Considered

- **Streamlit**: fastest MVP but ceiling too low for custom CRUD UX (edit modals, filters, planned-txn promotion).
- **Flask + Jinja**: viable; FastAPI preferred for Pydantic + async + OpenAPI.
- **Next.js / React SPA**: overbuilt for a single-user local app; doubles languages and build systems.
- **Reflex / NiceGUI / Dash**: niche; smaller communities; opaque under the hood.

## Addendum 2026-11-21: stack drift

The Decision above is partly obsolete; the prior text is kept as the record. Today: Tailwind is built locally (`just css`, no CDN; ADR-0027), charts are server-rendered SVG (ADR-0054, ADR-0123) and Plotly is gone, and the frontend stays server-rendered Jinja + HTMX with no SPA framework (ADR-0123). The repo does use a `package.json` toolchain for the Tailwind build and stylelint, so "no node toolchain" no longer holds. Quality-audit finding Q-052.
