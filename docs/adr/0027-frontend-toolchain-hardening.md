# ADR-0027: Frontend Toolchain Hardening — Local Tailwind Build, Stylelint, Partial Extraction, Visual Regression

- **Status**: Accepted
- **Date**: 2026-10-27
- **Related**: ADR-0002 (web stack), ADR-0017 (pre-commit stack), ADR-0018 (CI matrix), ADR-0023 (UX redesign)
- **Supersedes**: nothing. **Amends**: ADR-0002 (adds a local build step for CSS; the "JS build step can be added later" clause in ADR-0002 is now exercised for CSS only).

## Context

Phase 6–8 shipped the editorial/Swiss UX redesign on the ADR-0002 stack (FastAPI + Jinja2 + HTMX + Tailwind via CDN + Plotly). The redesign is in place but the frontend tooling that supports it has not kept up with the surface area it has to cover. Recurring symptoms observed across Phase 8 and the ongoing phase-9 worktree:

- Styling regressions found only by human-in-the-loop screenshot inspection or by the user noticing the broken page.
- Agents iterating blind on `app.css` / Jinja templates because Tailwind-CDN provides no build-time validation of utility classes.
- Duplicate markup clusters (card, segmented control, chip, slide-over header, overdue row) drifting across templates. A styling fix on one page silently misses two others.
- `djlint` catches template syntax, but there is no linter watching `app.css`.
- No automated signal that a layout bug has been introduced — the first signal is the next user interaction.

The project already has an auditing skill (`.claude/skills/frontend-visual-audit/SKILL.md`, now mandated by `CLAUDE.md` for all frontend-touching tasks). The skill validates a *running* app via headless Playwright. This ADR hardens the toolchain the skill validates against, so bugs are shorter-lived and more are caught before the skill runs.

The alternative — rewriting the UI in a mature JS framework (Next.js / SvelteKit / Astro) — was considered and rejected. See *Alternatives Considered*.

## Decision

### 1. Replace Tailwind CDN with a local Tailwind build

- Tailwind compiled from source via the `tailwindcss` standalone CLI (or `pnpm tailwindcss` if the Node toolchain is already present). No PostCSS plugin chain, no autoprefixer step beyond what Tailwind provides.
- Content globs: `src/budget_planner/web/templates/**/*.html` and `src/budget_planner/web/static/js/**/*.js`.
- Output: `src/budget_planner/web/static/tailwind.css` (checked in; hash-busted via existing `?v=…` query string pattern — see `app.css` link).
- `just css` builds once; `just css-watch` runs the Tailwind CLI in watch mode alongside `just dev`.
- Pre-commit hook `tailwind-check` fails the commit if the generated CSS is stale relative to the content globs and the current `tailwind.config.js`.
- `base.html` loses the CDN `<script src="https://cdn.tailwindcss.com">`. The CSP in production (future) is simpler for it.

### 2. Add `stylelint` to the pre-commit stack

- Config: `stylelint-config-standard` + a small project overrides file.
- Scope: `src/budget_planner/web/static/*.css` only. Does **not** lint the Tailwind-generated `tailwind.css`.
- Hook runs via `pnpm exec stylelint` (or `npx stylelint`, local only, no remote fetches).
- Rationale: catches typos, invalid properties, duplicate selectors, and misordered declarations that currently reach runtime.

### 3. Extract repeated Jinja markup into named partials

- New directory: `src/budget_planner/web/templates/_partials/`.
- One `{% macro %}` per partial. Inputs documented in a leading `{# #}` comment: name, type, nullable, default.
- Initial extraction targets (identified from Phase 6–8 duplication):
  - `card.html` — surface wrapper with header slot + body slot.
  - `segmented.html` — the Overview range control and the Ledger view control share shape; one macro parameterised by `items`, `active`, and `hx_target`.
  - `chip.html` — status pill (overdue, upcoming, soft-limit warning).
  - `slide_over_header.html` — title + close button cluster.
  - `overdue_row.html` — muted + italic row with `overdue` chip, reused in Overview upcoming + Planned ledger.
- `djlint` already lints templates; macros do not change that.
- Services and routers do **not** change. Pure template refactor.

### 4. Visual regression tests via Playwright

- New directory: `tests/visual/`.
- Test file `tests/visual/test_snapshots.py` (pytest + `pytest-playwright`) screenshots the 4 top-level routes (`/`, `/ledger`, `/accounts`, `/budget`) at viewports `1440×900`, `1024×768`, and `375×812`.
- Baselines live under `tests/visual/baselines/<route>__<viewport>.png`, committed to git-LFS-free regular git (PNG files are small for the single-user app).
- Diff tolerance: ≤ 0.1 pixel ratio (`pixelmatch` threshold), configurable per test.
- Runs under `just test-visual`; **not** part of `just ci` by default (opt-in via `CI_VISUAL=1`). Rationale: baselines drift with intentional design changes, failing CI by default would create a treadmill. The `frontend-visual-audit` skill remains the mandated verification step; visual regression is a secondary net.
- `just test-visual-update` regenerates baselines deliberately.
- Baselines refreshed only alongside a documented design change in the same commit.

### 5. Node toolchain is minimal, pinned, and dev-only

- `package.json` committed at repo root with exactly: `tailwindcss`, `stylelint`, `stylelint-config-standard`, `pixelmatch`, and `pngjs` for the diff helper. Playwright is pulled through the Python `pytest-playwright` package rather than through npm.
- `npm` is the package manager. Node + npm already ship on macOS via Homebrew and on `ubuntu-latest` via `actions/setup-node@v4`; corepack-based `pnpm` enablement needs root on Homebrew's prefix, so the extra hop is not worth it for a five-dependency dev-only toolchain. The pre-commit hooks call the binaries directly out of `node_modules/.bin`, not through `npm run`.
- Pinned versions in `package.json`; `package-lock.json` committed.
- `just install` runs `uv sync` **and** `npm ci` (equivalent to `--frozen-lockfile`).
- CI gets `actions/setup-node@v4` + an `npm ci` step before `just ci`.

### 6. `frontend-visual-audit` skill status

The skill (added 2026-10-27, mandated in `CLAUDE.md`) is unchanged by this ADR. This ADR formalises the toolchain it validates. The skill continues to be the **primary** verification tool; the pre-commit layer + visual regression are the **secondary** nets.

## Consequences

### Pros

- Styling bugs become compile-time or lint-time failures instead of runtime surprises.
- Agents editing CSS get deterministic feedback within the pre-commit loop; fewer "styled it, now re-read the template to guess if it worked" cycles.
- Partials collapse duplication; a fix lands in one place.
- Visual regression gives an objective diff for layout changes without needing a human screenshot pass.
- Tailwind-local produces a tiny purge-trimmed CSS file; the CDN script tag's cold-start cost disappears.
- CSP posture improves (one fewer third-party origin for scripts).

### Cons / costs

- `node` is now a dev dependency. The project is no longer "pure Python toolchain" (ADR-0002 called this out as a potential future cost; now realised).
- `pnpm install` added to local setup and CI. ~15s on a cold runner.
- Pre-commit stack grows; typical commit time increases by ~1–3s on the warm path.
- Visual-regression baselines must be refreshed deliberately on intentional design changes. Mitigated by `just test-visual-update` and by keeping visual tests out of `just ci` by default.
- One-time refactor to extract partials — estimated 1–2 days of focused template work in Phase 10.

### Explicit non-goals

- **No** Next.js / SvelteKit / Astro / React / Vue migration. HTMX + Jinja remain the application shell.
- **No** TypeScript. Vanilla JS (per ADR-0023, ≤ ~150 lines across palette + shortcuts + overlay stack) remains.
- **No** JS bundler. Scripts stay as plain `<script>` tags.
- **No** component framework (shadcn, Radix). Partials + CSS tokens only.
- **No** change to the ADR-0021 functional style on the Python side.
- **No** change to the service / repository / router layering.

## Alternatives Considered

- **Rewrite UI in Next.js / SvelteKit / Astro.** Rejected. The app is single-user, local-first, Python-centric. Dual-stack (FastAPI JSON + Node frontend) doubles the tooling surface, introduces hydration + routing complexity, and violates the "simplest thing that works" posture called out in ADR-0002. The frontend pain is real but tractable with the hardening in this ADR; a full rewrite is disproportionate to the problem.
- **Keep Tailwind CDN, add stylelint only.** Rejected. The CDN JIT does not purge, has no build-time class validation, and depends on a third-party origin at page load. The hardening is only partial without the local build.
- **Keep CDN, add visual regression only.** Rejected. Visual regression catches outcomes, not causes; without the build + lint layer, the regression tests become noisy and the root cause is still untyped.
- **Adopt a component framework (shadcn, Radix via a Jinja port).** Rejected. No mature Jinja port exists; cost of maintaining one exceeds the duplication cost it would remove.
- **Make visual-regression tests part of `just ci` by default.** Deferred. Treadmill risk outweighs the signal at this stage; revisit after Phase 10 lands and baselines stabilise.

## Amendment 2026-11-22 (operator decision; T-Q251)

The visual regression suite is a required check on pull requests that change templates or CSS, and also runs on a weekly schedule and `workflow_dispatch`. It runs in a pinned (digest) Playwright container image; baselines are regenerated inside that container (Linux), never locally. A missing baseline fails in CI.
