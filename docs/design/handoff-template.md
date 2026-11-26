# Handoff package template (v1)

Every package made under [ADR-0154](../adr/0154-designer-skill-handoff-builder-and-package-template.md) has this shape. The `handoff-builder` agent writes it; `just check-handoff docs/design/<name> --render --parity <refs> --write-manifest` is its Definition of Done. Each rule names the check that enforces it (`scripts/ci/check_handoff.py`), or "reviewer" when no script can.

`rising-dough-frontend/` and `rising-dough-goals-starter/` predate this template and are not checked against it (ADR-0154 §5).

## 1. Manifest: `handoff.toml` (check `manifest`)

```toml
name = "goals"                                  # the folder name under docs/design/
kind = "extension"                              # "base" (the app chrome) or "extension" (a feature on top of it)
base = "rising-dough-frontend"                  # extension only: the sibling base package
canvas = "https://claude.ai/artifact/<id>"      # the Design canvas the package follows
spec = "docs/design/specs/goals.md"             # the designer's handoff spec
delivered = "2026-12-01"

[[board]]                                       # one row per canvas artboard
artboard = "Goals-desktop-light.dc.html"        # path under the canvas's project/
page = "pages/goals/goals.html"                 # the package page that draws it
viewport = 1440                                 # the artboard width in px
theme = "light"                                 # light | dark

[[deviation]]                                   # numbered, same as README "Deviations"
id = 1
page = "pages/goals/goals.html"
reason = "Canvas draws the phone tab bar overlapping the toast; the package stacks them."
ratio = 0.01                                    # optional: parity tolerance for this page instead of 0.1 %
```

## 2. Layout (checks `layout`, `reachable`)

```
docs/design/<name>/
├── handoff.toml
├── README.md
├── index.html          links every page, overlay and state; theme switch (system · light · dark)
├── components.html     every component, variant and state on one page
├── pages/<area>/<screen>[--<state>].html
├── static/css/         <feature>.css, tokens.css (extension: only new tokens)
├── static/js/          behaviour, one file per concern
├── static/{fonts,icons,img}/   base only; an extension uses the base's
├── COPY-DECK.md        optional: every string, when copy is part of the design
└── MOTION-SPEC.md      optional: durations, easing, reduced-motion frame
docs/design/<name>.sha256        written by --write-manifest (check `checksums`)
```

- Every HTML page is reachable from `index.html` by links (`reachable`).
- State pages are named `<screen>--<state>.html` (`--empty`, `--error`, `--loading`, `--over-limit`), as in the base package (reviewer).
- An extension links the base package's `static/` by relative path, `../../../rising-dough-frontend/static/css/main.css` from `pages/<area>/`; it never copies a base file (`links`, reviewer).

## 3. One markup per page, two themes (checks `theme-copies`, `themes`, `coverage`)

- One HTML file per page or state. Light and dark come from tokens and the base theme switch (`<html data-theme>`, `prefers-color-scheme`, `?theme=` for review). No `.light.html` / `.dark.html` copies.
- Every page has a light and a dark `[[board]]` row (`coverage`), and renders differently in dark than in light (`themes`).

## 4. Tokens only (checks `colours`, `base-tokens`)

- No colour literal (`#hex`, `rgb()`, `hsl()`, `oklch()` …) anywhere except a file whose name ends in `tokens.css` (`tokens.css`, or a data palette such as `category-tokens.css`): not in feature CSS, inline `style`, `<style>` blocks or SVG `fill` / `stroke`. Use `var(--color-…)` or `currentColor`.
- Token names are the design system's (`docs/design/system/project/tokens.json`), which are the base `tokens.css` names.
- An extension's `static/css/tokens.css` adds new tokens with a light value in `:root` and a dark value in both dark selectors, like the base file. It never redefines a base token (`base-tokens`); a base token change is a base re-delivery.

## 5. Self-contained (checks `outside-urls`, `links`, `render`)

- No URL outside the package and, for an extension, the base package's `static/`: no CDNs, no Google Fonts, no analytics (`outside-urls`).
- Every relative `href`, `src`, `srcset`, CSS `url()` and `@import` resolves to a file (`links`).
- Every page opens from `file://` with 0 console errors, 0 failed requests and no horizontal scroll at each of its board viewports, in light and dark (`render`).

## 6. Wired (check `wiring`, reviewer)

Every designed element works as the canvas shows it:

- Links go to the page or state they lead to on the canvas; overlays, menus, sheets, popovers and tabs open and close; forms show their error state on submit; the theme switch switches.
- A control the canvas draws as inert (a sample, a disabled look) carries `data-handoff-inert="<reason>"`. On `components.html` the specimens are samples: wrap each specimen group in `data-handoff-inert="specimen"` unless it is meant to work there.
- Custom checkboxes and radios that are visually hidden under their label are clicked through the element itself, so they count as wired when they toggle.
- `wiring` clicks every visible button, `[role=button|tab|menuitem|switch|option]`, `summary`, `#`-link, checkbox and radio on load and fails one that neither navigates, changes the hash nor changes the DOM. Whether it does the *right* thing is the parity of its target state plus the reviewer.
- Controls that only appear after another click (inside a menu) are checked on the state page that shows them open (`<screen>--menu-open.html`), so draw that state.

## 7. Visually 1-to-1 (check `parity`)

- Every artboard has a `[[board]]` row; every page has at least one light and one dark row (`coverage`).
- `--parity <refs>` screenshots each row's page at the row's width and theme (full page, device scale 1, reduced motion) and compares it with `<refs>/<artboard stem>.png`: at most 0.1 % of pixels may differ (ADR-0147 §2), or the row's `[[deviation]]` ratio. Different sizes always fail. The cluster cap joins when it lands on `main` (T-DW08).
- References are renders of the artboards, made in the same run's scratch directory and not committed. How they are made: `.claude/agents/handoff-builder.md` (T-DW07 proves local rendering; the fallback is an operator export from the canvas).

## 8. README (check `readme`)

Sections, in this order:

1. `## Source`: canvas URL, spec path, design system, delivery date.
2. `## What changed`: per surface, what is new or different from the app or the previous delivery.
3. `## Deviations`: numbered, each with its `[[deviation]]` row and why the package differs from the canvas.
4. `## Not in this package`: what the canvas or spec mentions that is delivered elsewhere or later.
