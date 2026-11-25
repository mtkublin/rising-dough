# Rising Dough — Sourdough design system (repo copy)

The one design system for Rising Dough design work ([ADR-0151](../../adr/0151-designer-skill-handoff-builder-and-package-template.md) §1): light and dark themes, in the claude.ai Design System file layout.

| Field | Value |
|---|---|
| Published as | *Rising Dough — Sourdough*: https://claude.ai/artifact/Q9n5eDZg4KWdFKCb5WAYWy (created 2026-11-25, private to the operator until shared) |
| Source of values | `docs/design/rising-dough-frontend/static/css/tokens.css` (what the app ships) |
| Files | `project/README.md` (brand book), `project/tokens.json` (generated), `project/design-system.json` (index), `project/components/Cover/preview.html` (the cover) |
| Usage notes | `usage.toml` (words only; values always come from `tokens.css`) |
| Fonts | published from the base package's `static/fonts/` (Unbounded 700, Geist Mono) |
| Replaces | the remote *Rising Dough - Sourdough (dark)* and *(light)* systems for new work; those stay as they are |

## Rules

- `project/tokens.json` is generated: never edit it. `just design-system` regenerates it, `just design-system --check` fails when it is stale (also a unit test).
- Token names are the CSS custom property names without `--` (`color-now-fill` is `var(--color-now-fill)`).
- A value change is a base package change (`tokens.css`), then `just design-system`, then a republish. The brand book (`project/README.md`) and `usage.toml` are edited here.
- Edits made on claude.ai do not flow back. The `/designer` skill compares the remote `tokens.json` with this one before each job.

## Publishing (republish after any change)

With the Artifact tool, to the URL above (never to the older remote systems):

1. `read` the published `project/design-system.json` (the page may have added keys).
2. Publish with `root` = this folder's parent (`docs/design/system`), `file_path` = `project/design-system.json` (its `lastChange` updated, keys from step 1 kept), and `files`: `project/README.md`, `project/tokens.json`, `project/components/Cover/preview.html`, and `project/fonts/<file>` → `docs/design/rising-dough-frontend/static/fonts/<file>` for the three font files.
