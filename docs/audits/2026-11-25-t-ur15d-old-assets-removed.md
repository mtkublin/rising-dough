# T-UR15d: old CSS, fonts and toolchain removed (audit record)

Scope: deletion only. No file that `layouts/base.html` or `layouts/auth.html` loads changed (they load `rd/css/app.bundle.css`, `rd/js/*`, `rd/img/favicon.svg`, `vendor/htmx-2.0.11.min.js`). Deleted: `static/{app,auth,fonts,rising-dough,tailwind,tailwind.src,tokens}.css`, `static/fonts/`, `static/favicon.svg`, old `csrf.js`, `htmx-csrf.js`, `js/passkeys.js`, two `.gitkeep`.

Evidence by reading (not a browser run): `rg` over `src`, `tests`, `terraform`, `deploy` finds no loader of a deleted path; `app.bundle.css` is byte-identical (`css-bundle-check` passes); the only tests that fetched a deleted path were repointed to `rd/` paths.

## Browser sweep (frontend-visual-audit, regression mode)

Branch `wi/ui/sourdough/UR15d` at 11ac7212 (own server, port 8102, scratch copy of `data/demo.sqlite`, migrated, admin password set via `set_password`) against MAIN `ui/sourdough` at 6eab98c6 (second server, port 8101, its own scratch copy). Chromium via Playwright, viewports 1440x900, 1024x768, 375x812. Screenshots (scratch, not committed): `.../scratchpad/br/<width>_<route>.png` (branch) and `.../scratchpad/main/...` (MAIN); I viewed the post-save and 500 screenshots and the crops of the differing pixels.

Routes x viewports (every route at 1440, 1024 and 375, 60 captures per server): unauthenticated `/auth/login`, `/setup` (redirects to the login page on this DB, setup is closed), `/invite/badtoken`, `/no-such-page-404` (unauthenticated: redirect to login, 200); authenticated `/today`, `/ledger`, `/ledger?view=planned`, `/ledger?view=recurring`, `/ledger/recently-deleted`, `/plan?tab=budget|year|forecast|analytics`, `/accounts`, `/settings?tab=categories|fx|prefs`, `/settings/security`, `/settings/users`, `/dev/components`; authenticated 404 page rendered once (title "404 · Not found · Rising Dough", shell intact).

| Signal | Result (branch, all 60 captures) |
|---|---|
| horizontalScroll | 0 (false everywhere) |
| overflowingElements | 0 blocking: horizontalScroll is false everywhere; a non-empty list (scroll containers at 1024/375: ledger planned/recurring, plan year/forecast, settings tabs, dev/components) is identical in count to MAIN on every row, so not caused by this change |
| duplicateIds | 0 |
| consoleErrors | 0 (including pageerror) |
| requestFailures | 0 failed requests, 0 responses with status >= 400 on any page load; no request to a removed `/static/...` path |

Regression comparison against MAIN:
- Static requests: the set of `/static/...` URLs fetched is identical on branch and MAIN (only `rd/css/app.bundle.css`, `rd/fonts/*.woff2`, `rd/icons/sprite.svg`, `rd/img/favicon.svg`, `rd/js/*`, `vendor/htmx-2.0.11.min.js`), so the deleted files were already unreferenced. Login page loads `rd/js/passkeys.js`, `rd/js/csrf.js`, `rd/js/theme.js`, `rd/img/favicon.svg` (200).
- Fonts: `document.fonts` loaded `Geist Mono 400 500` and `Unbounded 700` on every page, no font in error state; computed `font-family` of body and first heading identical to MAIN on every row; favicon link is `/static/rd/img/favicon.svg` (the only DOM difference vs MAIN is the port).
- Pixel diff (Pillow, full-page screenshots, branch vs MAIN): 54 of 60 identical (diff ratio 0). 6 differ by 5e-5 to 1.4e-3: `settings/security` and `settings/users` at the three widths, only the session "last seen" minute (15:58 vs 15:59, the two logins were a minute apart); viewed the crops. No layout or font difference.
- hx-target check: every `hx-target` selector on every page matches exactly one element (0 violations).
- Old `app.css` URL: 404 on the branch, 200 on MAIN, as intended; nothing requests it.

Step 3b:
- Templates changed by the slice: only `templates/.gitkeep` deleted; no template edited, so no new arithmetic/`float`/`/ 100` (`rg` over templates: none). `templating.py` lost the `aria_current_date`, `dt_local`, `direction_badge`, `category_label`, `category_label_parts` and `Direction` registrations; `rg` finds no template using any of them, and all 60 pages render 200 (no Jinja undefined-filter error).
- Form POST (CSRF + HTMX): created an account through the UI dialog (name, JPY, opening balance 1500): `POST /accounts` 200, dialog closed, so csrf.js and htmx-csrf.js attach the token. JPY zero-decimal: `0.00` is rejected with a visible "invalid number" hero error and a "1 field needs attention" summary (same on MAIN).
- Failing save: forced `POST /accounts` 500 via `page.route`: dialog stays open with a visible "Something went wrong on our side. Try again." (twice, summary + field). Forced 422 (real) shows the field error. Behaviour identical on MAIN.
- Side observation (scratch data, identical on MAIN, not a finding): after creating the JPY account the next `/accounts` GET returns the styled 503 page because the scratch DB has no cached JPY->PLN rate.
- Rendered-number equality not re-checked: no number-producing code or template changed.

Findings: none.
