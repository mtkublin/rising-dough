# T-UR15d: old CSS, fonts and toolchain removed (audit record)

Scope: deletion only. No file that `layouts/base.html` or `layouts/auth.html` loads changed (they load `rd/css/app.bundle.css`, `rd/js/*`, `rd/img/favicon.svg`, `vendor/htmx-2.0.11.min.js`). Deleted: `static/{app,auth,fonts,rising-dough,tailwind,tailwind.src,tokens}.css`, `static/fonts/`, `static/favicon.svg`, old `csrf.js`, `htmx-csrf.js`, `js/passkeys.js`, two `.gitkeep`.

Evidence by reading (not a browser run): `rg` over `src`, `tests`, `terraform`, `deploy` finds no loader of a deleted path; `app.bundle.css` is byte-identical (`css-bundle-check` passes); the only tests that fetched a deleted path were repointed to `rd/` paths.

Browser sweep: delegated to the orchestrator's `visual-auditor` after this item. Routes to check: `/today`, `/ledger`, `/plan`, `/accounts`, `/settings`, `/auth/login` at 1440, 1024 and 375.

| Signal | Result |
|---|---|
| horizontalScroll | pending visual-auditor |
| overflowingElements | pending visual-auditor |
| duplicateIds | pending visual-auditor |
| consoleErrors | pending visual-auditor (watch for 404s on deleted assets) |
| requestFailures | pending visual-auditor (watch for 404s on deleted assets) |

screenshot: pending visual-auditor (not produced by the implementer).
