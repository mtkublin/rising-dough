# ADR-0050: v2 Rising Dough — Product Rename and Visual Direction

- **Status**: Accepted (2026-11-21; implemented, was Proposed)
- **Date**: 2026-10-28
- **Related**: ADR-0023 (prior UX redesign — IA consolidation + interaction model), ADR-0027 (frontend toolchain), ADR-0048 (category color coding)
- **Supersedes (visual direction only)**: ADR-0023 "Design direction" subsection — ADR-0050 replaces the editorial/Swiss tokens defined there with the explicit Rising Dough palette, typography, and elevation rules from `docs/application_redesign_handoff/tokens.css`.
- **Amends**: ADR-0048 (category colour override) — the per-category hue override continues to apply; direction defaults change to the ADR-0050 palette (expense H28, income H155, transit H230, adjust H75).

## Context

Phase-11 shipped a competent but generic editorial Swiss look. The user commissioned a dedicated design pass (handoff at `docs/application_redesign_handoff/`) that:

- Renames the product **Budget Planner → Rising Dough** (wordmark only; package name, repo, DB name unchanged).
- Tightens the editorial/Swiss base from ADR-0023: hierarchy comes from type-scale and whitespace, colour is reserved for meaning, elevation is hairline-first.
- Codifies a palette (OKLCH warm neutrals, hue 60–85, chroma ≤ 0.012), one accent (indigo H265), four directional hues with a soft tint each.
- Pins three typefaces (Newsreader display, Hanken Grotesk body, IBM Plex Mono numerals) with explicit scales and OpenType features.

Without this ADR, the token values live only in the handoff folder and risk drifting from any future implementation.

## Decision

### 1. Product name

- Wordmark displayed in the header and `<title>` becomes **Rising Dough** in plain Newsreader text (no logo mark, no "local-first" tagline).
- Internal identifiers stay unchanged: Python package `budget_planner`, SQLite file name, repo name, env prefix `BUDGET_PLANNER_*`, Docker image name.
- The CLAUDE.md "project title" line is updated to "Rising Dough — Budget planning and fortune tracking web app".
- The README gets a one-line "formerly Budget Planner" note at the top; nothing else cross-references the old name.

### 2. Palette (authoritative — `docs/application_redesign_handoff/tokens.css`)

Served from `src/budget_planner/web/static/tokens.css` (new file, verbatim copy from handoff) and consumed by Tailwind v4 `@theme` (ADR-0052). Values:

| Role | Token | Value |
|---|---|---|
| Page | `--paper` | `oklch(0.985 0.004 85)` |
| Cards / inputs | `--surface` | `oklch(0.997 0.002 85)` |
| Wells / active nav | `--sunk` | `oklch(0.962 0.006 85)` |
| Hairlines | `--line` | `oklch(0.9 0.008 85)` |
| Primary text | `--ink` | `oklch(0.21 0.01 60)` |
| Secondary text | `--mute` | `oklch(0.5 0.01 70)` (5.2:1 on paper) |
| Accent | `--accent` / `--accent-soft` | `oklch(0.45 0.14 265)` / `oklch(0.95 0.03 265)` |
| Expense | `--expense` / `--expense-soft` | `oklch(0.5 0.15 28)` / `oklch(0.955 0.035 28)` |
| Income | `--income` / `--income-soft` | `oklch(0.45 0.11 155)` / `oklch(0.95 0.04 155)` |
| Transit | `--transit` / `--transit-soft` | `oklch(0.45 0.09 230)` / `oklch(0.95 0.03 230)` |
| Adjust | `--adjust` / `--adjust-soft` | `oklch(0.48 0.1 75)` / `oklch(0.95 0.05 85)` |

Category pills: background `oklch(0.94 0.045 H)`, text `oklch(0.4 0.13 H)` where H is the per-category override hue (ADR-0048) or the direction default (expense 28, income 155, transit 230).

### 3. Typography

Three families, self-hosted as variable `woff2`:

- **Newsreader** 400/500 — page titles, section titles, the hero figure, account names. Add `font-feature-settings: 'lnum','tnum'` on figures.
- **Hanken Grotesk** 400/500/600 — body, labels, buttons. Eyebrow label: `11px / 600 / letter-spacing +0.13em / uppercase`.
- **IBM Plex Mono** 400/500/600 — every amount, date, and keyboard hint. `font-variant-numeric: tabular-nums`. Currency code is a muted 0.72em suffix.

Scale: hero 96 (desktop) / 76 (mobile) · H1 40 · H2 22 · body 14 · small 12–12.5 · eyebrow 11.

Serve the three faces via a dedicated preload chain. Only load the critical weight/style per family (per `coding-style.md`).

### 4. Elevation and shape

- Hairlines over shadows. Cards 10 px radius, controls 6 px, pills round.
- One shadow only, for overlays: `--shadow-overlay: 0 12px 40px rgb(30 20 10 / .14)`.
- Focus ring: 2 px accent with 2 px paper offset.

### 5. Motion

- 120–180 ms ease-out (`--ease: cubic-bezier(.2,.7,.2,1)`, `--dur: 140ms`).
- State changes only: promoted row collapses and its amount flies into "spent"; hero number counts to its new value; overlays rise 8 px and fade.
- Disable all motion under `prefers-reduced-motion`.

### 6. Contrast and non-colour cues

- Body text contrast 15:1 on paper; `--mute` 5.2:1; category pills ≥ 4.8:1.
- No colour-only state. Direction = colour + glyph + label (`↓ Expense`, `↑ Income`, `⇄ Transit`, `± Adjust`). Overdue = colour + "late" text + "!" glyph.

## Consequences

### Positive

- The product gets an opinionated, recognisable visual identity that is not interchangeable with a shadcn template.
- All numeric columns align via `tabular-nums`; hero figures count smoothly during state changes.
- Palette values ride in CSS variables, not hard-coded Tailwind utilities; theming headroom exists if a dark mode is added later (deferred).

### Negative / costs

- Three self-hosted font families add ~200 kB over the previous system-font stack. Only the critical weight is preloaded; other weights lazy-load via `font-display: swap`.
- Tokens must stay in sync between `static/tokens.css` and the Tailwind `@theme` block (ADR-0052).
- Every manual CSS reference to a specific colour must migrate from the pre-ADR hex / previous OKLCH values to the new tokens. Covered by a `stylelint` custom rule in Phase 1 of the v2 plan.

## Alternatives Considered

- Keep ADR-0023's palette and only rename the product — rejected; the whole point of the design brief is to tighten hierarchy and contrast beyond what Phase-11 shipped.
- Introduce a dark theme now — deferred (see v2 non-goals in `docs/requirements.md` §5.6); light is the intended primary surface.
- Add a logo mark — rejected; the wordmark alone is the identity, matching the editorial direction.
