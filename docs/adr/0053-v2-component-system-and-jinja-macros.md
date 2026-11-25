# ADR-0053: v2 Rising Dough — Component System and Jinja Macro Inventory

- **Status**: Superseded by ADR-0107 (2026-11-25, T-UR15: the old macro inventory is deleted)
- **Date**: 2026-10-28
- **Related**: ADR-0030 (shared form interaction primitives), ADR-0050 (visual direction), ADR-0051 (IA)

## Context

Phase 11 introduced four partials (`_partials/combobox.html`, `_slideover.html`, …). The Rising Dough handoff lists ~15 reusable primitives (`docs/application_redesign_handoff/docs/04-components.md`): amount, category pill, direction badge, pace tag, overdue chip, buttons (primary / default / ghost / small), segmented control, filter chip row, table row, overlays (slide-over / modal / popover / palette), form controls, heatmap cell, progress bar (incl. segmented hatched), top-bar add button.

Without a canonical inventory per primitive, templates will reinvent the shape. The handoff explicitly recommends a hidden `/dev/components` page that renders every macro — this ADR codifies that pattern and names each primitive.

## Decision

### 1. One macro per primitive, one directory

New folder `src/budget_planner/web/templates/_partials/components/` with one file per primitive:

| Macro | File | Signature |
|---|---|---|
| `amount(minor, currency, direction=None, formula=False, fx_hint=None, size="base")` | `_amount.html` | Renders Plex Mono tabular number with sign + currency suffix + ƒ chip + FX "≈ 412.10 PLN · 1 EUR = 4.2936 (28 Oct)" tooltip. |
| `category_pill(category, size="base")` | `_pill.html` | Uppercase 10.5 px / 600 round pill with per-category hue (ADR-0048) or direction default. |
| `direction_badge(direction, with_label=True)` | `_direction_badge.html` | Glyph + label: ↓ Expense, ↑ Income, ⇄ Transit, ± Adjust. 4 px radius. |
| `pace_tag(pace)` | `_pace_tag.html` | `● On track` (green) / `▲ Tight` (amber) / `! N overdue` (solid red, white text). |
| `overdue_chip(days_late)` | `_overdue_chip.html` | Solid red "N days late"; row that hosts it gets `.row--overdue` (expense-soft background). |
| `button(label, variant="default", kind=None, shortcut=None, size="base")` | `_button.html` | `variant ∈ {primary, default, ghost}`; `shortcut` renders a `<kbd>`. |
| `segmented(options, selected, name, hx_get=None)` | `_segmented.html` | Tabs / switches; active = ink fill. Supports HTMX `hx-get`. |
| `filter_chip_row(filters)` | `_filter_chips.html` | Date range · category · account · direction · search (with `/` hint). |
| `table_row(cells, actions=None, overdue=False)` | `_table_row.html` | Grid row with hairline divider; actions right-aligned, visible on focus/hover, always visible on touch (`@media (hover: none)`). |
| `heatmap_cell(value, max_value, tier)` | `_heatmap_cell.html` | 34 px tall; colour scaled by `sqrt(value / max)` capped at 1,600 (per handoff); tier marker: `one_off` bold+outline, `recurring` italic+hatch, `default` plain, `unset` em-dash. |
| `progress_bar(spent, committed, left, total)` | `_progress_bar.html` | 6–10 px bar with segmented spent / committed (diagonal hatch) / left variant. |
| `top_bar_add(variants)` | `_top_bar_add.html` | Desktop top-bar `+ Add` button opening a context-aware form (planned / recurring / actual). |
| `period_header(window, days_total, days_elapsed)` | `_period_header.html` | Paycheck window one-liner "Period 15 Oct → 7 Nov · day 14 of 24"; shared by Today + Plan tabs. |

### 2. `/dev/components` reference page

- New route `GET /dev/components`, gated by `settings.env != "production"` (always open in local; hidden on v3 prod).
- Renders every macro with representative inputs (OK state, overdue, formula, over-budget, dim muted). Used as the visual-regression baseline source — Playwright screenshots this one page before any screen screenshot (fast fail on primitive drift).

### 3. Dynamic colour wiring

Per ADR-0050, category pill hue and heatmap cell intensity are runtime values. Tailwind cannot generate utilities for arbitrary runtime hues; the macros emit inline `style` or CSS custom properties:

```html
<span class="pill" style="--pill-h: 265;">…</span>
```

The ADR-0048 category hue override continues to be `color.hue` (int 0–360) stored on `categories.color_hue`. The macro reads `category.color_hue` or falls back to the direction default from ADR-0050.

### 4. Phase 11 primitives subsumed

Phase 11's shared form primitives (ADR-0030) stay in `_partials/` (combobox, slide-over header, numeric input). The new `_partials/components/` directory is for render-side primitives (display) rather than form primitives (interaction). No overlap — the two sets compose.

### 5. Macro-level visual regression

The `frontend-visual-audit` skill run against `/dev/components` is the first assertion in every v2 Phase 1 task touching a primitive. A delta there fails the task before per-screen rebuilds inherit the regression.

## Consequences

### Positive

- One canonical home per primitive. A rebuild of Ledger · Actual pulls the amount macro, not a bespoke `<span>`.
- `/dev/components` doubles as a design review surface and a visual-regression source.
- The ADR-0048 category hue override continues to work unchanged; the macro is where the fallback-to-direction-default logic lives.

### Negative / costs

- 13 macros + one dev route to maintain. Rebuilt once; afterwards, screen rebuilds are compositional.
- The dev route must be gated behind env so prod does not expose it. Enforcement: `/dev/*` returns 404 unless `settings.env in {"local", "dev", "test"}`.

## Alternatives Considered

- Inline the primitives per template — rejected; each primitive is used on 3–7 screens, inlining recreates the "every table reinvents its row" problem.
- Build the primitives in JS components (Alpine, Lit) — rejected; the handoff explicitly chooses Jinja macros to keep the no-SPA posture. Alpine remains available for popover state only (ADR-0056).
