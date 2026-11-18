# ADR-0126: Goals and Starter UI Built From a Designer Handoff Extending the Redesign

- **Status**: Accepted
- **Date**: 2026-11-18
- **Relates to**: [ADR-0107](0107-sourdough-redesign-from-designer-handoff.md) (handoff-only UI, extended here), [ADR-0123](0123-frontend-stays-server-rendered-no-spa-framework.md) (no SPA, animation via CSS/SVG/WAAPI), [ADR-0113](0113-csp-compatible-frontend.md) (no inline style or script), [ADR-0106](0106-ui-behaviour-test-harness.md) (harness, `--target=mockup`), [ADR-0124](0124-savings-goals-envelopes-and-net-worth.md), [ADR-0125](0125-sourdough-starter-rules.md), requirements §10.2, §12

## Context

- The redesign (§10, ADR-0107) builds every screen only from the designer's static handoff (`docs/design/rising-dough-frontend/`). The handoff has nothing for goals or a mascot.
- The starter needs character art, five states, idle and feedback motion, and a shelf of loaves. Goals need a new Plan tab, dialogs and additions to Accounts and Today.
- ADR-0123 left Lottie/Rive open behind a per-page budget exception, to be settled in the starter's ADR.

## Decision

1. **Same process as the redesign.** Goals and starter UI is built **only** from a designer handoff that extends `docs/design/rising-dough-frontend/` with the same conventions: static HTML per page and state, `components.html`, `tokens.css`, `@layer` CSS, BEM `rd-*`, fragment boundary comments, overlays as page files, light and dark, 320–1920 px. The brief is [`docs/design/gamification-brief.md`](../design/gamification-brief.md).
2. **Character**: a jar with a subtle face. Five states (dormant, sleepy, bubbly, rising, overflowing) as **layered inline SVG** with named groups (`jar`, `jar-glass`, `lid`, `dough`, `dough-surface`, `bubbles`, `face`, `eyes`, `eyelids`, `mouth`), plus a simplified badge glyph at 24 and 32 px. Loaves come in 3–4 shapes, tinted via the category colour presets (`--cat`, `--cat-edge`).
3. **Motion**: the designer delivers a motion spec (layer, property, keyframes, duration, easing, loop), preferably as CSS `@keyframes`. We implement it with CSS and, where sequencing needs it, a small Web Animations API module. Only `transform` and `opacity`. Under `prefers-reduced-motion: reduce`, loops and bounces are off.
4. **No Lottie, Rive, GIF or video.** This closes ADR-0123 Decision §3 for this feature: no per-page JS budget exception is taken.
5. **Copy**: the brief supplies functional draft copy. The designer proposes the voice, the final strings and the starter's default name, delivered in the handoff.
6. **Two handoff drops**, matching the releases: drop 1 (goals) before goals UI work starts; drop 2 (starter, shelf, motion, copy) before starter UI work starts. An early character-direction sketch round is requested before drop 2 production.
7. **Gating**: backend tasks (schema, services, scoring, routes with contract tests) are **not** gated on the handoff. Template, CSS and motion tasks are gated on the relevant drop being accepted (checked into `docs/design/rising-dough-frontend/`, validator and axe clean).
8. **Per-surface loop**: the redesign's test-first loop applies (`docs/plans/ui-redesign/README.md`): UI-map module against the handoff, confirmed with `--target=mockup`, then red, green, visual diff, `frontend-visual-audit` at 1440 / 1024 / 375.

## Rationale

- One design system and one handoff format keep goals and starter screens consistent with the redesign and reuse its tooling (harness mockup target, visual diff).
- Layered SVG with server-set `data-state` fits the server-rendered stack and CSP. It costs no runtime, and reduced motion degrades to stills.
- Not gating the backend on art lets the domain work start right after the redesign ships.

## Consequences

- The handoff folder grows: `pages/plan/goals*`, goal overlays, a Today starter card, the starter detail overlay, Accounts allocation states, a Preferences addition, components for the starter, the badge and the shelf.
- Every new screen gets UI-map modules and visual baselines, as in the redesign.
- If the designer later proposes a richer animation that CSS/SVG cannot express, it needs a new ADR (ADR-0123 Decision §3 path).

## Alternatives considered

- **Build on the design system, designer polishes later.** Rejected: contradicts ADR-0107's handoff-only rule and invites drift.
- **Figma-only delivery.** Rejected: devs would translate it, and drift follows.
- **Lottie with a lazy runtime.** Rejected: about 60 kB gzipped against a 30 kB app budget, for a mascot that CSS/SVG covers.
- **Rive.** Rejected: a WASM runtime, CSP changes (`wasm-unsafe-eval`), same budget problem.
