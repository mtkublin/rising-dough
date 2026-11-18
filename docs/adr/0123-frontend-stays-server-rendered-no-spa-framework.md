# ADR-0123: Frontend Stays Server-Rendered (Jinja + HTMX); No SPA Framework; Animation via CSS and Web APIs

- **Status**: Accepted
- **Date**: 2026-11-17
- **Renumbered**: 2026-11-18, from ADR-0112 (number collided with main's ADR-0112 when the branch was merged).
- **Relates to**: [ADR-0107](0107-sourdough-redesign-from-designer-handoff.md) (the redesign builds on this stack), [ADR-0027](0027-frontend-toolchain-hardening.md) (frontend toolchain), [ADR-0080](0080-v4-envelope-encryption-key-hierarchy-and-sessions.md), [ADR-0081](0081-v4-field-level-encryption-scope-and-query-model.md) (server-side decryption), requirements §10.2 (budgets), §12 (savings goals + sourdough starter idea)

## Context

- The frontend is server-rendered: FastAPI + Jinja templates, HTMX for partial swaps, small single-purpose JS modules, no bundler (ADR-0107).
- The sourdough redesign (§10, ADR-0107) will replace the whole presentation layer from the designer's handoff, which is static HTML, plain CSS in `@layer`s and presentational JS. ADR-0107 records "no bundler" but does not explicitly weigh a JS framework.
- The savings goals + sourdough starter idea (§12, `docs/plans/gamification/`) needs basic character animation: state changes (dormant, bubbly, rising, overflowing), small idle motion, and feedback when the starter is fed.
- The question came up whether such features justify moving to a "modern" JS framework (React, Next.js, Vue) and, if so, that the switch should happen before the redesign rather than after it.

## Decision

1. **The frontend stays server-rendered with Jinja + HTMX** for the redesign and after it. React, Next.js, Vue and similar SPA/meta-frameworks are not adopted.
2. **Animation uses platform features**, in order of preference:
   - CSS transitions and keyframes on state classes rendered by the server (e.g. `starter--dormant`);
   - HTMX swap/settle classes (`htmx-added`, `htmx-settling`) and the View Transitions API for state changes after a swap;
   - inline SVG animated via CSS or the Web Animations API, in small single-purpose ES modules like the existing ones.
   All motion animates `transform` / `opacity` only and respects `prefers-reduced-motion` (§10.2).
3. **Designer-authored animation files** (Lottie, Rive) are allowed only if the designer delivers them. Their runtime is lazy-loaded on the pages that use it, and that page gets an explicit, documented exception to the §10.2 JS budget, recorded in the feature's ADR.
4. **Isolated interactive islands.** If one widget ever needs rich client-side state, it is built as a self-contained island on that page (a web component, or a micro-library such as Alpine or petite-vue) under the same CSP and budget rules. Adopting an island library needs its own ADR. This is not a path to a rewrite.
5. **Revisit triggers.** This decision is re-opened only by a requirement for substantial client-side state that server rendering cannot serve well: offline-first use, real-time collaboration, drag-and-drop planning editors, or complex in-browser editors. A new ADR supersedes this one in that case.

## Rationale

- **The animation needs are small.** State-driven CSS, SVG and the Web Animations API cover a mascot with a handful of states. The state is derived server-side anyway (§12), so the server renders the class and the browser animates it.
- **The redesign handoff fits the current stack.** It is HTML, CSS and presentational JS that maps directly onto Jinja partials. A component framework would mean rewriting every screen into components instead of porting markup.
- **Architecture cost.** Next.js needs a Node server, or the app splits into a JSON API plus a separately deployed client. Either way, authentication, CSRF, the CSP nonce, passkey handling and the deploy pipeline (ADR-0099, ADR-0111) would all be reworked.
- **v4 data protection.** Decryption happens server-side during a live session (ADR-0080, ADR-0081), and pages render only what they show. An SPA tends to pull larger decrypted datasets into the browser, which widens exposure.
- **Budgets.** §10.2 caps JS at 30 kB gzipped plus htmx. React + ReactDOM alone take more than that before any app code.
- **Sunk investment kept.** The §9 UI behaviour test harness, the HTMX contract tests, the routers and the view-model code all keep working.

## Consequences

- The redesign (§10) proceeds on the current stack with no framework spike.
- Starter animation work (§12) is CSS/SVG/WAAPI by default. Choosing Lottie or Rive needs a per-page budget exception recorded in the starter ADR.
- Frontend contributors work in Jinja, HTMX, plain CSS and small ES modules. There is no client-side component model or state store.
- Highly interactive features cost more to build than they would with a framework. This is accepted until a revisit trigger (Decision §5) occurs.

## Alternatives considered

- **React / Next.js.** Rejected: full rewrite of the redesign, a Node runtime or an API split, auth/CSRF/CSP rework, it exceeds the JS budget, and it pulls more decrypted data into the browser.
- **Vue / Nuxt.** Same trade-offs as React / Next.js. Vue without a build step is lighter, but it still means moving rendering to the client.
- **Svelte / SvelteKit.** Smaller runtime, but it needs a compiler and bundler (against ADR-0107's "no bundler") and has the same architecture split as Next.js.
- **Alpine.js / petite-vue globally.** Not needed for the current scope. Kept as the island option (Decision §4), behind its own ADR.
