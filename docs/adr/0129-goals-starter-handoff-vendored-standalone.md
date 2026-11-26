# ADR-0129: The Goals and Starter Handoff Is Vendored as Its Own Folder, Delivered in One Drop

- **Status**: Accepted
- **Date**: 2026-11-19
- **Amends**: [ADR-0126](0126-gamification-design-handoff.md) §1, §6, §7
- **Relates to**: [ADR-0107](0107-sourdough-redesign-from-designer-handoff.md) (handoff-only UI, vendored byte-identical), [ADR-0113](0113-csp-compatible-frontend.md) (vendored assets, no inline style or script), [ADR-0123](0123-frontend-stays-server-rendered-no-spa-framework.md), [ADR-0124](0124-savings-goals-envelopes-and-net-worth.md), [ADR-0125](0125-sourdough-starter-rules.md), [ADR-0106](0106-ui-behaviour-test-harness.md), requirements §12

## Context

- ADR-0126 expected two drops (goals, then starter) that extend `docs/design/rising-dough-frontend/` in its own layout (`static/css/components/*`, `pages/plan/*`, `pages/overlays/*`).
- The designer delivered **one** handoff on 2026-11-19 covering both releases: *Rising Dough · goals & starter handoff* (95 files, 70 HTML, about 3.1 MB). Design canvas: *Rising Dough · Goals & Starter*.
- The delivery is a **standalone** static site, not an overlay: its own `css/base.css` that mirrors the app chrome so pages stand alone, `tokens.css` at the root, flat `pages/*.html` with `.light.html` twins, `js/app.js` for prototype settings, `assets/starter/*.svg` and `assets/shelf/*.svg`, `MOTION-SPEC.md`, `COPY-DECK.md`. Its root folder is also named `rising-dough-frontend/`, and four of its paths (`index.html`, `components.html`, `pages/today.html`, `pages/accounts.html`) collide with different files in the redesign handoff.
- It loads fonts from Google Fonts. The redesign handoff vendors them.

## Decision

1. **Own folder.** The delivery is vendored byte-identical at `docs/design/rising-dough-goals-starter/`, with its checksum manifest `docs/design/rising-dough-goals-starter.sha256`, under the same rules as the redesign handoff (`docs/design/README.md`: never edited, a new delivery replaces the folder in its own commit). It is not merged into `docs/design/rising-dough-frontend/`, which stays the redesign's fixed revision.
2. **Source precedence.** For goals and starter screens this folder is the UI source (ADR-0126 §1). For anything it shares with the app chrome (`css/base.css`, header, tabs, dialogs, buttons, fields, toast) the redesign handoff and the shipped app win, as the delivery's own notes say. Its `tokens.css` "goals & starter" block is merged into the app's tokens; `css/guide.css`, the guide pages (`index`, `components`, `motion`, `copy`) and `js/app.js` are reference only and are not shipped.
3. **One drop.** Drop 1 and drop 2 (ADR-0126 §6) arrived together. Acceptance is still per release: T-GS00 records drop 1 accepted for the goals pages, T-GS16 records drop 2 accepted for the starter, shelf, motion and copy. Acceptance = the HTML validator and axe clean on the pages of that release, both themes (the designer did not run them). Gaps found at acceptance go back to the designer or are recorded as deviations in `docs/plans/ui-redesign/derived.md`.
4. **Fonts.** The Google Fonts links are a prototype convenience. The app keeps the vendored fonts (ADR-0113); no external font origin is added to the CSP.
5. **Handoff details the plan adopts**: default starter name **Levi**; starter detail is a **drawer** (`pages/starter-drawer.html`), renaming lives in Preferences; the badge sits in the **header** (desktop: left of `[ new entry ]`; phone: top header, left of settings) instead of the rail; the starter SVG layer names in the handoff (`starter`, `jar`, `jar-glass`, `lid`, `dough`, `dough-surface`, `flow`, `trails`, `pops`, `face`, `sleep-bubble`, `bubbles`) replace the list in ADR-0126 §2; idle motion is opacity-only cell blinking per `MOTION-SPEC.md`; loaf shape = `crc32("rd:" + goal.id) % 4` over boule, batard, baguette, tin.
6. **Afford-warning figure: the requirement wins** (operator decision, 2026-11-19). The handoff's afford warning uses "free money" = cash accounts (bank, savings, cash) after planned payments, minus what goals hold, excluding investments and liabilities. That figure is **not adopted**: the warning stays as ADR-0124 and G1.10 define it, over the total free balance of asset accounts in base currency. The handoff's screens (`pages/today-afford-goals`) are reused with that figure, and their explanatory copy is adjusted to match; the deviation is recorded in `docs/plans/ui-redesign/derived.md` at T-GS08.

## Rationale

- Merging into the redesign folder would overwrite four redesign files and mix two layouts, and the redesign's checksum manifest and harness mockup target would no longer describe one delivery.
- A separate, byte-identical folder keeps both deliveries verifiable and replaceable on their own.
- Acceptance per release keeps ADR-0126's gating: goals UI does not wait for starter fixes, and vice versa.

## Consequences

- UI-map modules for goals and starter (ADR-0106) point `--target=mockup` at `docs/design/rising-dough-goals-starter/pages/*`. The harness may need a second mockup root.
- Task references in `docs/plans/gamification/tasks.md` use the delivery's file names (`plan-goals*`, `goal-*`, `accounts-over-allocated`, `today-*`, `starter-drawer`, `goals-loaf-baked`, `settings-preferences*`).
- Requirement S1.8 says "header badge" and S1.9 names the default "Levi".

## Alternatives considered

- **Merge into `rising-dough-frontend/`.** Rejected: path collisions, two layouts in one folder, a broken redesign manifest.
- **Ask the designer to re-cut it as an overlay first.** Rejected: costs a round trip for a layout change only; porting maps the markup onto Jinja partials either way.

## Amendment 2026-11-25 (ADR-0154)

New feature packages are `kind = "extension"` packages: they link the base package's `static/` by relative path instead of copying its chrome, and never redefine a base token ([ADR-0154](0154-designer-skill-handoff-builder-and-package-template.md) §3, §5). `rising-dough-goals-starter/` stays standalone as delivered.
