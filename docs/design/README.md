# Design handoffs

Designer deliveries, vendored **byte-identical** so tests and agents can reference them at a fixed revision (ADR-0106 §5, ADR-0107 §1). Do not edit files in a handoff folder; record deviations in the plan that consumes it (for the Sourdough redesign: `docs/plans/ui-redesign/derived.md`). A new delivery replaces the folder in its own commit, with a new checksum manifest.

Packages made from the repo ([ADR-0154](../adr/0154-designer-skill-handoff-builder-and-package-template.md)) follow [`handoff-template.md`](handoff-template.md), are built by the `handoff-builder` agent from a canvas and a spec (`specs/`), and are regenerated whole, never hand-edited: byte-identical to the builder's last passing `just check-handoff` run, with a new checksum manifest. The two packages below predate the template and stay as delivered. The design system is [`system/`](system/README.md); scope proposals are change requests in [`requests/`](requests/README.md).

Pre-commit fixers (`trailing-whitespace`, `end-of-file-fixer`, `mixed-line-ending`) and `djlint` exclude `docs/design/`. `detect-secrets` still scans it.

## `rising-dough-frontend/`

| Field | Value |
|---|---|
| What | "Rising Dough · Sourdough redesign" static frontend: every page, overlay and state, components, chart examples, CSS, JS, fonts, icons |
| Source canvases | *Rising Dough · Sourdough redesign* (dark page + light page); *Rising Dough Frontend Handoff Spec* |
| Delivered | 2026-11-21 (updated package answering change request T-UT06; first delivery 2026-11-14); same day a delta package for ST17, Edit user (`CHANGES-edit-user.md`) |
| Vendored | 2026-11-16, T-UT01, copied unchanged from the untracked `data/rising-dough-frontend/`; re-vendored 2026-11-21 (T-UT06-HANDOFF) unchanged from `data/rising-dough-frontend.zip`, which answers change request T-UT06 (see its README, "What changed in this update") |
| Contents | 173 files, 114 HTML, about 3.4 MB (re-vendor: 15 files added, 85 changed, 1 removed: `pages/overlays/edit-user.html`; edit-user delta: `pages/overlays/edit-user.html` and `CHANGES-edit-user.md` added, 13 files changed) |
| Checksums | [`rising-dough-frontend.sha256`](rising-dough-frontend.sha256), verify with `cd docs/design/rising-dough-frontend && shasum -a 256 -c ../rising-dough-frontend.sha256` |
| Entry point | `rising-dough-frontend/index.html` (opens from disk, no server); handoff notes in `rising-dough-frontend/README.md` |
| Consumed by | `docs/plans/ui-test-harness/` (T-UT05, T-UT09, T-UT10), `docs/plans/ui-redesign/` |

Check at vendoring: Playwright Chromium opened all 99 HTML files from `file://` with 0 console errors, 0 failed requests and 0 requests outside the folder.

**Operator:** after this is merged, delete the untracked copy `data/rising-dough-frontend/` from the main checkout. This folder is the only copy to use from now on.

## `rising-dough-goals-starter/`

| Field | Value |
|---|---|
| What | "Rising Dough · goals & starter handoff": savings goals (release 1) and Levi the starter + bakery shelf (release 2). 31 pages × dark and light, components, motion, copy deck, starter and loaf SVGs, tokens, CSS |
| Source canvas | *Rising Dough · Goals & Starter* |
| Brief | [`gamification-brief.md`](gamification-brief.md) |
| Delivered | 2026-11-19 (one drop for both releases, ADR-0129) |
| Vendored | 2026-11-19, copied unchanged from the untracked `data/rising-dough-goals-starter/docs/design/rising-dough-frontend/` (`.DS_Store` dropped) |
| Contents | 95 files, 70 HTML, about 3.1 MB |
| Checksums | [`rising-dough-goals-starter.sha256`](rising-dough-goals-starter.sha256), verify with `cd docs/design/rising-dough-goals-starter && shasum -a 256 -c ../rising-dough-goals-starter.sha256` |
| Entry point | `rising-dough-goals-starter/index.html` (opens from disk, no server); handoff notes are in that page; `MOTION-SPEC.md`, `COPY-DECK.md` |
| Status | Delivered, **not yet accepted**: validator + axe run at T-GS00 (goals pages) and T-GS16 (starter pages) |
| Consumed by | `docs/plans/gamification/` (T-GS06..T-GS08, T-GS16..T-GS19) |

A standalone site, not an overlay on `rising-dough-frontend/` (ADR-0129): its `css/base.css` mirrors the app chrome so pages stand alone, and the redesign handoff wins where they overlap. `css/guide.css`, the guide pages and `js/app.js` are reference only. Pages link Google Fonts; the app keeps its vendored fonts (ADR-0113).

Check at vendoring: Playwright Chromium opened all 70 HTML files from `file://` with 0 console errors and 0 failed requests; the only requests outside the folder are to `fonts.googleapis.com` / `fonts.gstatic.com`.

**Operator:** after this is merged, delete the untracked copy `data/rising-dough-goals-starter/` from the main checkout.
