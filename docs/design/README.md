# Design handoffs

Designer deliveries, vendored **byte-identical** so tests and agents can reference them at a fixed revision (ADR-0106 §5, ADR-0107 §1). Do not edit files in a handoff folder; record deviations in the plan that consumes it (for the Sourdough redesign: `docs/plans/ui-redesign/derived.md`). A new delivery replaces the folder in its own commit, with a new checksum manifest.

Pre-commit fixers (`trailing-whitespace`, `end-of-file-fixer`, `mixed-line-ending`) and `djlint` exclude `docs/design/`. `detect-secrets` still scans it.

## `rising-dough-frontend/`

| Field | Value |
|---|---|
| What | "Rising Dough · Sourdough redesign" static frontend: every page, overlay and state, components, chart examples, CSS, JS, fonts, icons |
| Source canvases | *Rising Dough · Sourdough redesign* (dark page + light page); *Rising Dough Frontend Handoff Spec* |
| Delivered | 2026-11-14 (file dates of the delivery) |
| Vendored | 2026-11-16, T-UT01, copied unchanged from the untracked `data/rising-dough-frontend/` |
| Contents | 157 files, 99 HTML, about 3.1 MB |
| Checksums | [`rising-dough-frontend.sha256`](rising-dough-frontend.sha256), verify with `cd docs/design/rising-dough-frontend && shasum -a 256 -c ../rising-dough-frontend.sha256` |
| Entry point | `rising-dough-frontend/index.html` (opens from disk, no server); handoff notes in `rising-dough-frontend/README.md` |
| Consumed by | `docs/plans/ui-test-harness/` (T-UT05, T-UT09, T-UT10), `docs/plans/ui-redesign/` |

Check at vendoring: Playwright Chromium opened all 99 HTML files from `file://` with 0 console errors, 0 failed requests and 0 requests outside the folder.

**Operator:** after this is merged, delete the untracked copy `data/rising-dough-frontend/` from the main checkout. This folder is the only copy to use from now on.
