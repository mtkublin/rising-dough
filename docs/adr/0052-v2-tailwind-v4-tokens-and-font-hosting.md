# ADR-0052: v2 Rising Dough — Tailwind v4 Migration, `@theme` Tokens, and Self-Hosted Fonts

- **Status**: Superseded by ADR-0107 (2026-11-25, T-UR15: Tailwind and the old fonts are removed)
- **Date**: 2026-10-28
- **Related**: ADR-0027 (frontend toolchain hardening), ADR-0050 (visual direction)

## Context

ADR-0027 pinned Tailwind v3 compiled via `npx tailwindcss` to `static/tailwind.css`. The Rising Dough tokens (ADR-0050) are OKLCH values that need to live in CSS variables so dynamic colour (category hue override, heatmap intensity) can consume them at render time. Tailwind v4 natively consumes `@theme` with CSS variables and removes the JS-config boilerplate; v3 does not.

Fonts: v1 uses system fonts. The design calls for three families (Newsreader, Hanken Grotesk, IBM Plex Mono) with explicit weights. CDN delivery was ruled out (ADR-0005 principle of local-first; v3 remote deployment still prefers self-hosting to avoid a third-party dependency on the critical path).

## Decision

### 1. Upgrade Tailwind v3 → v4

- `package.json` dev dependency `tailwindcss` → `^4.0`.
- Config moves from `tailwind.config.ts` to a single `src/budget_planner/web/static/css/app.css` that `@import`s `tokens.css` and uses `@theme` to expose the OKLCH tokens to Tailwind utilities:
  ```css
  @import "tailwindcss";
  @import "./tokens.css";

  @theme {
    --color-paper: var(--paper);
    --color-surface: var(--surface);
    --color-sunk: var(--sunk);
    --color-line: var(--line);
    --color-ink: var(--ink);
    --color-mute: var(--mute);
    --color-accent: var(--accent);
    --color-accent-soft: var(--accent-soft);
    --color-income: var(--income);
    --color-income-soft: var(--income-soft);
    --color-expense: var(--expense);
    --color-expense-soft: var(--expense-soft);
    --color-transit: var(--transit);
    --color-transit-soft: var(--transit-soft);
    --color-adjust: var(--adjust);
    --color-adjust-soft: var(--adjust-soft);

    --font-display: var(--font-display);
    --font-sans: var(--font-body);
    --font-mono: var(--font-mono);

    --radius-card: var(--radius-card);
    --radius-control: var(--radius-control);
    --radius-pill: var(--radius-pill);

    --shadow-overlay: var(--shadow-overlay);
    --ease-rise: var(--ease);
  }
  ```
- The existing `just css` + `just css-watch` recipes keep their names; the invoked binary becomes the Tailwind v4 CLI.
- `tailwind-check` pre-commit hook (ADR-0027) continues to verify `static/tailwind.css` is up-to-date vs content globs. Globs are unchanged — v4 scans the same `templates/**/*.html` + `static/js/**/*.js` set.

### 2. Design tokens: `tokens.css` is the single source

- `src/budget_planner/web/static/tokens.css` is copied verbatim from `docs/application_redesign_handoff/tokens.css` on Phase 1 of the v2 plan.
- Any token value change requires editing both files in the same commit; a Phase 1 pre-commit hook (new) diffs them and fails if they drift.
- The handoff folder stays as the authoritative design reference; the project copy is the runtime consumer.

### 3. Self-hosted fonts

- `src/budget_planner/web/static/fonts/` grows three variable `woff2` files:
  - `newsreader.var.woff2` (400 / 500, latin + latin-ext subset).
  - `hanken-grotesk.var.woff2` (400 / 500 / 600).
  - `ibm-plex-mono.var.woff2` (400 / 500 / 600).
- `@font-face` declarations live in `static/css/fonts.css`, imported by `app.css` before `@theme`.
- Loading strategy per `web/performance.md`:
  - Preload only the critical weight per family (`<link rel="preload" as="font" ... crossorigin>` on `base.html`).
  - `font-display: swap` for all three.
  - Non-critical weights lazy-load via a `@font-face` with `font-display: swap`.
- Caddy (v3 remote deployment, ADR-0036) serves `/static/fonts/*.woff2` with `Cache-Control: public, max-age=31536000, immutable` and `Content-Type: font/woff2`.

### 4. Charts render on-brand

Charts move from Plotly to Jinja-rendered SVG per ADR-0054. The Tailwind theme exposes stroke colours (income, expense, accent) that SVG consumes via `currentColor` or `fill="var(--income)"`.

## Consequences

### Positive

- One tokens file drives Tailwind utilities, hand-authored CSS, and dynamic server-rendered style attributes. No duplication.
- Fonts self-hosted → no third-party request on the critical render path; works offline (v1 principle) and privately (v3 principle).
- Tailwind v4 drops the JS config file; the whole theme fits in one CSS file.
- Future dark mode (deferred) can swap the token values in a `[data-theme="dark"]` block without touching utilities.

### Negative / costs

- Tailwind v4 is new; its upgrade is irreversible without pinning v3. Phase 1 of the v2 plan dedicates a task to the upgrade with a rollback plan (keep the v3 branch for one release).
- Variable woff2 files add ~180 kB (preloaded weight only, other weights lazy-load).
- CI job time rises slightly (`just css` scans the same globs but v4's engine is Rust-based so often faster; measure in Phase 1).

## Alternatives Considered

- Stay on Tailwind v3 and hand-roll `@theme` via `theme.extend` in `tailwind.config.ts` — works but duplicates every token in two syntaxes; defeats the "tokens.css is the source" rule.
- Use CDN fonts (Google Fonts) — rejected (third-party request on the critical path; ADR-0005 principle for v1 and privacy posture for v3).
- Ship static font files but gate them behind a conditional `@font-face` for reduced-motion — rejected; fonts are a visual identity concern, not a motion concern.

## Addendum 2026-11-21: Tailwind version

The Decision to move to Tailwind v4 with `@theme` was not implemented: `package.json` pins `tailwindcss` 3.4.14 and compiles `static/tailwind.src.css` to `static/tailwind.css` (`just css`). Tokens are plain CSS variables. The redesign direction is owned by ADR-0107 (implementation pending). Quality-audit finding Q-052.
