# Handoff specs

One file per design job, `<slug>.md`, written by the `/designer` skill when the canvas is agreed ([ADR-0151](../../adr/0151-designer-skill-handoff-builder-and-package-template.md) §2). The `handoff-builder` agent builds the package from the canvas and this spec; where they disagree, the canvas wins and the builder records a deviation.

## Template

```markdown
# <Feature> — handoff spec

- Canvas: https://claude.ai/artifact/<id>
- Design system: Rising Dough — Sourdough (docs/design/system/)
- Package: docs/design/<name>/ (kind: extension, base: rising-dough-frontend)
- Requirements: docs/requirements.md §<n> / change request docs/design/requests/<file>
- Agreed with the operator: <date>

## Screens and states
| Page (package path) | Artboards (light, dark) | Viewports | Notes |
|---|---|---|---|

## Components
New or changed components, their variants and states, and where they live on the canvas.

## Behaviour (wiring)
Per control: what it opens, where it navigates, which state it shows (the builder wires exactly this).

## Copy
Strings that are part of the design (or "see COPY-DECK.md").

## Motion
Durations, easing, the reduced-motion frame (or "none").

## Tokens
New tokens with light and dark values and their usage. Base token changes are not allowed here (base re-delivery).

## Data the app must provide
Values the screens show that the app does not have yet (input for requirements, not for the package).

## Open questions
```
