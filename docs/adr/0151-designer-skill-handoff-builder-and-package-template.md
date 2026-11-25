# ADR-0151: Design Work From the Repo: a Designer Skill, a Handoff Builder and One Package Template

- **Status**: Accepted
- **Date**: 2026-11-25
- **Amends**: [ADR-0107](0107-sourdough-redesign-from-designer-handoff.md) §1 (who produces a handoff and the "byte-identical" rule, for new packages only); [ADR-0129](0129-goals-starter-handoff-vendored-standalone.md) (new feature packages extend the base package instead of standing alone)
- **Related**: [ADR-0106](0106-ui-behaviour-test-harness.md), [ADR-0113](0113-csp-compatible-frontend.md), [ADR-0123](0123-frontend-stays-server-rendered-no-spa-framework.md), [ADR-0147](0147-handoff-parity-ci-rendered-references-and-data-overlay.md), [ADR-0150](0150-orchestrator-role-agents-executable-dod-and-wave-testing.md)
- **Tasks**: T-DW01 to T-DW08 (`docs/plans/design-workflow/tasks.md`)

## Context

Until now design work happened outside the repo. A designer session on claude.ai drew a canvas (Rising Dough · Sourdough redesign, Rising Dough · Goals & Starter) and delivered a zip of static HTML, which was vendored byte-identical under `docs/design/` (ADR-0107 §1, ADR-0129). The operator wants the same work done from Claude Code: a designer that knows the current app, uses the project's design system, proposes changes on a Canvas, and writes the handoff; and a second role that turns the canvas and handoff into the static package that implementation is built against.

The two packages delivered so far show why a fixed format is needed. They differ in almost every structural choice:

| | `rising-dough-frontend` | `rising-dough-goals-starter` |
|---|---|---|
| Themes | one markup per page, light and dark from tokens | every page twice (`.html` + `.light.html`) |
| Fonts | vendored | Google Fonts (the app cannot use them, ADR-0113) |
| Layout | `static/{css,js,fonts,icons,img}` | `css/`, `js/`, root `tokens.css` |
| Chrome | its own | `base.css` copies the base chrome, so the two drift |
| Notes | README with "what changed" and numbered deviations | in `index.html`, plus `MOTION-SPEC.md`, `COPY-DECK.md` |

There are also two claude.ai design systems for one product, *Rising Dough - Sourdough (dark)* and *Rising Dough - Sourdough (light)*. Their values disagree with each other (the dark system's light theme is a lime-on-off-white palette; the light system is white and apricot) and with what ships: the base handoff's `static/css/tokens.css`, which the app copies, carries the light system's colours in light and the dark system's in dark.

A canvas made from the claude.ai Design type is a set of `.dc.html` artboards under `project/` that Claude Code can read and publish through the Artifact tool, and comments on it reach the session. A subagent, however, runs one task and reports back: it cannot hold the propose, comment, revise loop with the operator.

## Decision

### 1. One combined design system, kept in the repo

- `docs/design/system/` holds **Rising Dough — Sourdough**, one design system with two themes (light, dark), in the claude.ai Design System file layout (`project/README.md`, `project/tokens.json`, `project/design-system.json`).
- `tokens.json` is **generated** from the base package's `static/css/tokens.css` by `scripts/design_system.py` (`just design-system`). That file is what the app ships, so the design system, the canvas and the app read the same values. Token names are the CSS custom property names without `--` (`color-ground`, `space-4`, `radius-lg`), so a value seen on the canvas is found in CSS by name.
- The README is a brand book merged from the two remote systems, with the light theme described as it ships.
- The repo is the source. The system is published to claude.ai as a **new** Design System artifact; its URL is recorded in `docs/design/system/README.md`. The five existing systems are left untouched (operator lock, 2026-11-25). Edits made on claude.ai do not flow back: the designer skill compares the remote `tokens.json` with the generated one before work starts and stops on a difference.
- A token change is a base-package change (§5): a new base delivery regenerates `tokens.css`, then `just design-system` regenerates `tokens.json`, then the remote system is republished.

### 2. The designer is a skill, not a subagent

`.claude/skills/designer/SKILL.md` (`/designer`) runs in the operator's main session, because design is a conversation:

1. Learn the current UI from the running app (`just dev-demo`, screenshots through the `frontend-visual-audit` tooling), the base package and the templates, not from text baked into the skill.
2. Open a Canvas from the Design type with the repo design system installed. Every designed screen, component or state gets a **light and a dark artboard**, side by side, at the template's viewports (§3).
3. Discuss through canvas comments; edits saved by another agent on the same canvas URL reach the session as republish notices and are re-read.
4. Write the handoff spec (`docs/design/specs/<slug>.md`, template in §3) and, for anything that changes scope, a **designer change request** (`docs/design/requests/<date>-<slug>.md`). Requirements and ADRs are updated from a change request before any code (CLAUDE.md change policy); the designer proposes, the operator decides.

### 3. One handoff package template

`docs/design/handoff-template.md` defines the package. Summary:

- **Manifest** `handoff.toml`: `name`, `kind` (`base` or `extension`), `base` (extension only), `canvas` URL, `spec` path, `delivered` date, and one `[[board]]` row per canvas artboard: `artboard` path, `page` path in the package, `viewport`, `theme`, optional `state`.
- **Layout**: `README.md`, `index.html` (links every page, overlay and state; theme switch), `components.html`, `pages/<area>/<screen>[--<state>].html`, `static/{css,js,fonts,icons,img}`. Optional `COPY-DECK.md`, `MOTION-SPEC.md`.
- **One markup per page.** Light and dark come from tokens only; no `.light.html` or `.dark.html` copies.
- **Tokens only.** No colour literal outside a `tokens.css`. An extension adds tokens in its own `static/css/tokens.css` and never redefines a base token.
- **Self-contained.** Every page opens from disk with no request outside the package (and, for an extension, the base package). Fonts are vendored.
- **Wired.** Every designed control does what the canvas shows: links navigate to the page or state, buttons open the overlay, menu, sheet, tab or state they lead to, forms show their error state, the theme switch switches. A control the canvas draws as inert carries `data-handoff-inert="<reason>"`.
- **Visually 1-to-1.** Every artboard maps to a package page at the artboard's width and theme (`[[board]]` rows), and every page in the package maps to at least one artboard. The rendered page matches the rendered artboard within the ADR-0147 tolerance (0.1 % of pixels; the cluster cap once `tests/visual/handoff.py` on `main` carries it, T-DW08).
- **README sections**: Source, What changed, Deviations (numbered; each one also an exception the parity check reads from `handoff.toml`), Not in this package.

### 4. A handoff builder agent and an executable check

- `.claude/agents/handoff-builder.md` (model `sonnet`, full tools, its own worktree): reads the canvas and the spec, writes the package under `docs/design/<name>/`, and finishes only when the check passes. It writes no app code; package-to-Jinja stays with `implementer` + `visual-auditor` (ADR-0150).
- `scripts/ci/check_handoff.py` (`just check-handoff <dir>`) is the builder's Definition of Done. Static checks: manifest and layout, no theme copies, no colour literals outside `tokens.css`, no base-token redefinition, no outside URLs, every relative link resolves, every page reachable from `index.html`, every page covered by a `[[board]]` row, README sections present. With `--render` (Playwright Chromium, already a dev dependency): every page at its viewports in light and dark with 0 console errors, 0 failed requests, 0 requests outside the allowed roots, no horizontal scroll, dark differs from light, and every visible control is wired (a click navigates, changes the URL hash or changes the DOM; `data-handoff-inert` exempts). With `--parity <refs>`: each `[[board]]` page against its artboard reference PNG. `--write-manifest` writes `docs/design/<name>.sha256`.
- **Artboard references.** The builder renders each artboard to `<page>.<viewport>.<theme>.png` in a scratch directory and passes it to `--parity`. Rendering artboards locally (the `.dc.html` source with the Design type's runtime) is proven on the first real canvas (T-DW07); until then, and as the fallback, the operator exports the artboards from the canvas. References are not committed (as ADR-0147 §1 for the app references).

### 5. Vendoring and the existing packages

- A package produced under this ADR is **regenerated whole** by the builder in its own commit, never hand-edited, with a new checksum manifest. "Byte-identical to the designer's zip" (ADR-0107 §1) becomes "byte-identical to the builder's last passing run".
- New feature packages are `kind = "extension"`: they link the base package's `static/` by relative path (`../rising-dough-frontend/static/...`) instead of copying its chrome (amends ADR-0129 for future packages). A base re-delivery can break an extension; `just check-handoff` on every extension is part of the base re-delivery.
- `rising-dough-frontend/` and `rising-dough-goals-starter/` stay as delivered. They are not checked against the template, and the in-flight migration on `ui/sourdough` keeps consuming `rising-dough-frontend/` unchanged. A future base re-delivery through the builder brings `rising-dough-frontend/` under the template; it waits until the `ui/sourdough` migration is merged.

### 6. Design gate: every UI-facing change goes through the designer

Operator decision (2026-11-25). A **UI-facing change** is any change a user can see or interact with: templates, CSS, static JS, user-visible copy, icons and images, layout and breakpoints, HTMX swap targets and what they render, a new screen, state, dialog, flow or interaction.

- Every UI-facing change has a **design reference**: an agreed handoff package page or state (`docs/design/<name>/…`) or an agreed spec (`docs/design/specs/<slug>.md`), named in the task, the brief and the PR. It is produced through the `/designer` skill (canvas with light and dark artboards, the operator agrees, spec, package by the `handoff-builder`).
- The implementation **complies with the design system** (`docs/design/system/`, tokens only, both themes) **and with the existing app design** (the base package's chrome, components and patterns). A new component or pattern exists only if the design reference introduces it.
- A change that only makes the UI match an already agreed reference (a parity fix, a bug that breaks the agreed design, implementing a delivered package such as the `ui/sourdough` migration of `rising-dough-frontend/`) cites that reference and needs no new design round. Everything else needs one first, however small: a new label, a moved button, a new empty state.
- No reference, no UI change: an agent that finds a UI-facing change without one stops and reports it (`implementer` `BLOCKED`, `reviewer` `RETURN`).
- Enforcement is by review and the agent definitions now; a guard that fails a template, CSS or static-JS change whose task cites no design reference is T-DW10.

## Consequences

- Design runs from the repo with the same two-theme system the app ships; the remote design systems stop being a second source of colour values.
- Every new package has one shape, so the parity harness, the implementer and the reviewer read every package the same way.
- "Wired" and "1-to-1" are exit codes, not review opinions. The wiring check proves a control does something, not that it does the right thing; the right target is checked by the parity of the target state and by the reviewer.
- The skill and the agent are prompts and drift when repo rules change; they link CLAUDE.md and this ADR rather than restating them.
- Local artboard rendering is an open risk until T-DW07; the operator-export fallback keeps the check usable.

## Alternatives considered

- **A designer subagent.** Rejected: one-shot, no conversation with the operator, and the comment loop on the canvas would have no owner.
- **A builder that writes Jinja directly.** Rejected: duplicates `implementer` + `visual-auditor`, and loses the reviewed static package the parity harness compares against (ADR-0106, ADR-0147).
- **Keep the two remote design systems as the source.** Rejected: their values disagree with each other and with the shipped `tokens.css`.
- **Standalone feature packages (ADR-0129 as is).** Rejected for new packages: the copied chrome already drifts in `rising-dough-goals-starter/`.
- **Template enforced by the agent prompt only.** Rejected: prose rules drift (ADR-0150 context); the check script is the contract.
